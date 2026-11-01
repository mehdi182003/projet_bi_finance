"""Configuration centrale : chemins, connexion PostgreSQL, paramètres."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent
load_dotenv(RACINE / ".env")

DOSSIER_DATA = RACINE / "data"
DOSSIER_RAW = DOSSIER_DATA / "raw"
DOSSIER_DEMO = DOSSIER_DATA / "demo"
DOSSIER_DBT = RACINE / "dbt"

# Fichier PaySim tel que publié sur Kaggle (ealaxi/paysim1)
NOM_FICHIER_PAYSIM = "PS_20174392719_1491204439457_log.csv"
DATASET_KAGGLE = "ealaxi/paysim1"

# Taux de référence BCE. Source privilégiée : export Banque de France Webstat
# (https://webstat.banque-france.fr - série EXR, cours de référence BCE), versionné dans
# data/sources/. À défaut, téléchargement du fichier historique de la BCE.
DOSSIER_SOURCES = DOSSIER_DATA / "sources"
FICHIER_WEBSTAT = DOSSIER_SOURCES / "webstat_taux_change_bce.csv"
URL_BCE_HISTORIQUE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
NOM_FICHIER_BCE = "eurofxref-hist.csv"

# Devises cotées par la BCE que l'on conserve :
#  - USD, CAD      : filiales d'Amérique du Nord
#  - SEK, DKK, NOK : filiales d'Europe du Nord
#  - JPY, RUB      : devises citées par le sujet (surveillance ; RUB = rupture de série 03/2022)
# XAF / XOF ne sont pas cotés : parité fixe 655,957 pour 1 EUR (gérée dans dbt).
DEVISES_BCE = ["USD", "CAD", "SEK", "DKK", "NOK", "JPY", "RUB"]

# Taille de lot du jeu versionné dans Git (data/sources_internes) : dépôt léger, utilisable sans PaySim.
TAILLE_LOT_VERSIONNEE = 500

# Dossier des exports bruts des filiales lu par le pipeline. Par défaut le jeu versionné ; après
# `python pipeline.py --regenerer --taille-lot 50`, le jeu local data/generees/lot_50.
# Un chemin relatif part de la racine du projet, quel que soit le dossier de lancement.
DOSSIER_SOURCES_INTERNES_ACTIF = RACINE / os.getenv("DOSSIER_SOURCES_INTERNES", str(DOSSIER_DATA / "sources_internes"))

PG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    "dbname": os.getenv("POSTGRES_DB", "cresus"),
}

PREVISION_HORIZON_JOURS = int(os.getenv("PREVISION_HORIZON_JOURS", "7"))
PREVISION_NB_SIMULATIONS = int(os.getenv("PREVISION_NB_SIMULATIONS", "500"))
PREVISION_JOURS_BACKTEST = int(os.getenv("PREVISION_JOURS_BACKTEST", "3"))
PREVISION_CHANGE_HORIZON_JOURS = int(os.getenv("PREVISION_CHANGE_HORIZON_JOURS", "30"))
GRAINE_ALEATOIRE = 42
