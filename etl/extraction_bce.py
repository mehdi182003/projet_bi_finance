"""Étape EXTRACT (2/2) : taux de change de référence BCE.

Source 1 (privilégiée) : export Webstat de la Banque de France (data/sources/),
    séries EXR.D.<devise>.EUR.SP00.A = cours de référence quotidiens de la BCE.
    Format : 6 lignes d'en-tête (titre, code série, unité...), séparateur « ; »,
    virgule décimale, « - » les jours sans cotation (week-ends, jours fériés).
Source 2 (secours) : fichier historique eurofxref-hist.zip téléchargé sur le site de la BCE.

Dans les deux cas le fichier est « large » (une colonne par devise) : on le passe au
format « long » (date, devise, taux), plus adapté à une base de données.
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

from .config import DEVISES_BCE, DOSSIER_RAW, FICHIER_WEBSTAT, NOM_FICHIER_BCE, URL_BCE_HISTORIQUE

log = logging.getLogger(__name__)
FICHIER_SORTIE = DOSSIER_RAW / "bce_taux_change_long.csv"


def telecharger_historique_bce() -> Path:
    cible = DOSSIER_RAW / NOM_FICHIER_BCE
    if cible.exists():
        log.info("Historique BCE déjà présent : %s", cible)
        return cible
    log.info("Téléchargement de %s", URL_BCE_HISTORIQUE)
    reponse = requests.get(URL_BCE_HISTORIQUE, timeout=60)
    reponse.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(reponse.content)) as archive:
        nom = next(n for n in archive.namelist() if n.endswith(".csv"))
        DOSSIER_RAW.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(archive.read(nom))
    return cible


def transformer_format_long(fichier_large: Path) -> pd.DataFrame:
    large = pd.read_csv(fichier_large, na_values=["N/A", ""])
    large = large.loc[:, ~large.columns.str.startswith("Unnamed")]  # colonne vide finale
    large.columns = [c.strip() for c in large.columns]
    manquantes = [d for d in DEVISES_BCE if d not in large.columns]
    if manquantes:
        raise ValueError(f"Devises absentes du fichier BCE : {manquantes}")
    long = (
        large[["Date", *DEVISES_BCE]]
        .melt(id_vars="Date", var_name="code_devise", value_name="taux")
        .dropna(subset=["taux"])
        .rename(columns={"Date": "date_cours"})
    )
    long["date_cours"] = pd.to_datetime(long["date_cours"]).dt.date
    long["source"] = "BCE - eurofxref-hist"
    return long.sort_values(["code_devise", "date_cours"]).reset_index(drop=True)


def lire_webstat(fichier: Path) -> pd.DataFrame:
    """Lit un export Webstat et le renvoie au format long (date_cours, code_devise, taux, source)."""
    entete = pd.read_csv(fichier, sep=";", encoding="utf-8-sig", header=None, nrows=6, dtype=str)
    codes_series = entete.iloc[1, 1:]                         # ex. EXR.D.USD.EUR.SP00.A
    devises = [c.split(".")[2] for c in codes_series]
    donnees = pd.read_csv(fichier, sep=";", encoding="utf-8-sig", header=None, skiprows=6,
                          dtype=str, na_values=["-", ""], keep_default_na=False)
    donnees.columns = ["date_cours", *devises]
    manquantes = [d for d in DEVISES_BCE if d not in devises]
    if manquantes:
        raise ValueError(f"Devises absentes de l'export Webstat : {manquantes}")
    long = donnees[["date_cours", *DEVISES_BCE]].melt(id_vars="date_cours", var_name="code_devise", value_name="taux")
    long = long.dropna(subset=["taux"])
    long["taux"] = long["taux"].str.replace(",", ".", regex=False).astype(float)
    long["date_cours"] = pd.to_datetime(long["date_cours"], format="%Y-%m-%d").dt.date
    long["source"] = "Banque de France Webstat - cours de référence BCE"
    return long.sort_values(["code_devise", "date_cours"]).reset_index(drop=True)


def extraire_taux_bce(fichier_local: Path | None = None) -> Path:
    """Produit data/raw/bce_taux_change_long.csv prêt à être chargé."""
    if fichier_local is None and FICHIER_WEBSTAT.exists():
        log.info("Lecture de l'export Webstat : %s", FICHIER_WEBSTAT)
        long = lire_webstat(FICHIER_WEBSTAT)
    else:
        long = transformer_format_long(fichier_local or telecharger_historique_bce())
    DOSSIER_RAW.mkdir(parents=True, exist_ok=True)
    long.to_csv(FICHIER_SORTIE, index=False)
    for devise, g in long.groupby("code_devise"):
        log.info("  %s : %d cotations du %s au %s", devise, len(g), g.date_cours.min(), g.date_cours.max())
    return FICHIER_SORTIE
