"""Étape LOAD des exports bruts des filiales vers la zone RAW (bronze) de PostgreSQL.

Principes appliqués :
  - ELT : AUCUNE règle métier ici. Le chargeur ne gère que le format physique de chaque système
    (encodage, séparateur, ligne de titre, ligne de total) et charge toutes les valeurs en TEXTE,
    telles qu'elles sont dans le fichier. Le nettoyage est fait ensuite par dbt (couche staging).
  - Traçabilité : chaque ligne garde le nom du fichier source, son numéro de ligne et la date de chargement.
  - Idempotence + chargement incrémental : un fichier déjà chargé avec la même empreinte MD5 est ignoré ;
    un fichier modifié est rechargé (ses anciennes lignes sont d'abord supprimées) => aucune duplication
    si le pipeline est relancé.
  - Contrôle de complétude : le journal raw.journal_chargement garde, par fichier, le nombre de lignes
    lues et, quand le système le fournit (DELTA), le nombre de lignes et le total annoncés en pied de fichier.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import logging
from pathlib import Path

import pandas as pd

from .config import DOSSIER_SOURCES
from .db import connexion
from .systemes_sources import DOSSIER_SOURCES_INTERNES, FICHIER_SOLDES

log = logging.getLogger(__name__)

FORMATS = {   # systeme : (sous-dossier, encodage, séparateur, ligne de titre, ligne de total)
    "SAB": ("sab", "cp1252", ";", False, False),
    "NORDIC": ("nordic", "utf-8-sig", ",", False, False),
    "AMERICORE": ("americore", "utf-8", ",", False, False),
    "DELTA": ("delta", "cp1252", ";", True, True),
}

DDL_JOURNAL = """
create schema if not exists raw;
create table if not exists raw.journal_chargement (
    systeme_source        text,
    nom_fichier           text primary key,
    empreinte_md5         text,
    nb_lignes_lues        integer,
    nb_lignes_annoncees   integer,
    total_annonce         numeric(24, 2),
    ligne_titre           text,
    date_chargement       timestamp default now()
);
create table if not exists raw.soldes_comptables (
    code_filiale      text,
    date_comptable    date,
    total_credits     numeric(24, 2),
    total_debits      numeric(24, 2),
    nb_operations     bigint,
    _date_chargement  timestamp default now()
);
"""


def _lire(chemin: Path, encodage: str, sep: str, titre: bool, total: bool) -> tuple[pd.DataFrame, dict]:
    with gzip.open(chemin, "rb") as f:
        texte = f.read().decode(encodage)
    lignes = texte.splitlines()
    meta = {"ligne_titre": None, "nb_lignes_annoncees": None, "total_annonce": None}
    if titre:
        meta["ligne_titre"], lignes = lignes[0], lignes[1:]
    if total and lignes and lignes[-1].startswith("TOTAL"):
        _, nb, montant = lignes[-1].split(sep)[:3]
        meta["nb_lignes_annoncees"], meta["total_annonce"] = int(nb), float(montant)
        lignes = lignes[:-1]
    df = pd.read_csv(io.StringIO("\n".join(lignes)), sep=sep, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    return df, meta


def _creer_table(cur, table: str, colonnes: list[str]) -> None:
    defs = ", ".join(f'"{c}" text' for c in colonnes)
    cur.execute(f"create table if not exists {table} ({defs}, _fichier text, _ligne integer, "
                f"_date_chargement timestamp default now())")


def charger_exports_bruts() -> dict[str, int]:
    """Charge les fichiers nouveaux ou modifiés ; renvoie le nombre de lignes chargées par système."""
    bilan = {}
    with connexion() as cnx, cnx.cursor() as cur:
        cur.execute(DDL_JOURNAL)
        deja = dict(cur.execute("select nom_fichier, empreinte_md5 from raw.journal_chargement").fetchall())
        for systeme, (dossier, encodage, sep, titre, total) in FORMATS.items():
            table = f"raw.src_{systeme.lower()}"
            fichiers = sorted((DOSSIER_SOURCES_INTERNES / dossier).rglob("*.csv.gz"))
            charges = ignores = 0
            for chemin in fichiers:
                empreinte = hashlib.md5(chemin.read_bytes()).hexdigest()
                if deja.get(chemin.name) == empreinte:
                    ignores += 1
                    continue
                df, meta = _lire(chemin, encodage, sep, titre, total)
                _creer_table(cur, table, list(df.columns))
                cur.execute(f"delete from {table} where _fichier = %s", (chemin.name,))
                df["_fichier"], df["_ligne"] = chemin.name, range(1, len(df) + 1)
                tampon = io.StringIO()
                df.to_csv(tampon, index=False, header=False)
                colonnes = ", ".join(f'"{c}"' for c in df.columns)
                with cur.copy(f"copy {table} ({colonnes}) from stdin with (format csv)") as copie:
                    copie.write(tampon.getvalue())
                cur.execute("""insert into raw.journal_chargement (systeme_source, nom_fichier, empreinte_md5,
                                   nb_lignes_lues, nb_lignes_annoncees, total_annonce, ligne_titre)
                               values (%s, %s, %s, %s, %s, %s, %s)
                               on conflict (nom_fichier) do update set empreinte_md5 = excluded.empreinte_md5,
                                   nb_lignes_lues = excluded.nb_lignes_lues, nb_lignes_annoncees = excluded.nb_lignes_annoncees,
                                   total_annonce = excluded.total_annonce, ligne_titre = excluded.ligne_titre,
                                   date_chargement = now()""",
                            (systeme, chemin.name, empreinte, len(df), meta["nb_lignes_annoncees"],
                             meta["total_annonce"], meta["ligne_titre"]))
                charges += len(df)
            bilan[systeme] = charges
            log.info("  %-9s : %d fichiers (%d déjà à jour), %s lignes chargées dans %s", systeme, len(fichiers),
                     ignores, f"{charges:,}".replace(",", " "), table)
        # référentiels comptables et ancrages : rechargés en entier (petits)
        cur.execute("truncate raw.soldes_comptables")
        with cur.copy("copy raw.soldes_comptables (code_filiale, date_comptable, total_credits, total_debits, "
                      "nb_operations) from stdin with (format csv, header true)") as copie:
            copie.write(FICHIER_SOLDES.read_text(encoding="utf-8"))
        cur.execute("truncate raw.ancrages_zf")
        with cur.copy("copy raw.ancrages_zf (code_filiale, date_ancrage, encours_zf_devise, est_point_initial, "
                      "est_interpole, source) from stdin with (format csv, header true)") as copie:
            copie.write((DOSSIER_SOURCES / "ancrages_zf.csv").read_text(encoding="utf-8"))
        for t in ("raw.src_sab", "raw.src_nordic", "raw.src_americore", "raw.src_delta", "raw.soldes_comptables"):
            cur.execute(f"analyze {t}")
    return bilan
