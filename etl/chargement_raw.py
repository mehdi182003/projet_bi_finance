"""Étape LOAD : chargement des fichiers bruts dans PostgreSQL (schéma raw).

On utilise la commande COPY de PostgreSQL (chargement en flux) : c'est de loin la
méthode la plus rapide pour les 6,3 millions de lignes de PaySim (~1 à 2 min),
là où un INSERT ligne à ligne prendrait des heures.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .config import RACINE
from .db import connexion

log = logging.getLogger(__name__)
TAILLE_BLOC = 8 * 1024 * 1024

COLONNES_PAYSIM = (
    "step, type, amount, name_orig, old_balance_orig, new_balance_orig, "
    "name_dest, old_balance_dest, new_balance_dest, is_fraud, is_flagged_fraud"
)


def creer_schema_raw() -> None:
    ddl = (RACINE / "etl" / "sql" / "create_raw.sql").read_text(encoding="utf-8")
    with connexion() as cnx:
        cnx.execute(ddl)
    log.info("Schémas raw et ml prêts (tables brutes vidées)")


def _copier(fichier: Path, table: str, colonnes: str) -> int:
    debut = time.time()
    with connexion() as cnx, cnx.cursor() as cur:
        with cur.copy(f"COPY {table} ({colonnes}) FROM STDIN WITH (FORMAT csv, HEADER true)") as copie, \
                open(fichier, "rb") as source:
            while bloc := source.read(TAILLE_BLOC):
                copie.write(bloc)
        nb = cur.execute(f"select count(*) from {table}").fetchone()[0]
        cur.execute(f"analyze {table}")
    log.info("%s : %s lignes chargées en %.1f s", table, f"{nb:,}".replace(",", " "), time.time() - debut)
    return nb


def charger_paysim(fichier: Path) -> int:
    return _copier(fichier, "raw.paysim_transactions", COLONNES_PAYSIM)


def charger_taux_bce(fichier: Path) -> int:
    return _copier(fichier, "raw.bce_taux_change", "date_cours, code_devise, taux, source")


def charger_transactions_zf(fichier: Path) -> int:
    return _copier(fichier, "raw.transactions_zf",
                   "horodatage, code_filiale, code_type, montant_devise, poids, id_client, est_fraude")


def charger_ancrages(fichier: Path) -> int:
    return _copier(fichier, "raw.ancrages_zf",
                   "code_filiale, date_ancrage, encours_zf_devise, est_point_initial, est_interpole, source")
