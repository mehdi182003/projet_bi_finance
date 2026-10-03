"""Étape EXTRACT (1/2) : récupération du dataset PaySim depuis Kaggle.

Deux modes :
  1. Automatique via l'API Kaggle (variables KAGGLE_USERNAME / KAGGLE_KEY
     ou fichier ~/.kaggle/kaggle.json).
  2. Manuel : télécharger l'archive sur https://www.kaggle.com/datasets/ealaxi/paysim1
     et déposer le CSV dans data/raw/. Le script le détecte et ne retélécharge pas.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .config import DATASET_KAGGLE, DOSSIER_RAW, NOM_FICHIER_PAYSIM

log = logging.getLogger(__name__)


def trouver_fichier_paysim(dossier: Path = DOSSIER_RAW) -> Path | None:
    """Renvoie le CSV PaySim présent dans le dossier, quel que soit son nom exact."""
    attendu = dossier / NOM_FICHIER_PAYSIM
    if attendu.exists():
        return attendu
    candidats = sorted(dossier.glob("PS_*.csv")) + sorted(dossier.glob("*paysim*.csv"))
    return candidats[0] if candidats else None


def extraire_paysim() -> Path:
    fichier = trouver_fichier_paysim()
    if fichier:
        log.info("PaySim déjà présent : %s (%.0f Mo)", fichier, fichier.stat().st_size / 1e6)
        return fichier

    log.info("Téléchargement de %s via l'API Kaggle (~180 Mo compressé, ~470 Mo décompressé)...", DATASET_KAGGLE)
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Le paquet 'kaggle' n'est pas installé : pip install kaggle") from exc

    api = KaggleApi()
    try:
        api.authenticate()
    except Exception as exc:
        raise SystemExit(
            "Authentification Kaggle impossible. Soit renseigner KAGGLE_USERNAME/KAGGLE_KEY "
            "dans .env, soit télécharger le CSV à la main dans data/raw/ "
            "(https://www.kaggle.com/datasets/ealaxi/paysim1)."
        ) from exc

    DOSSIER_RAW.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files(DATASET_KAGGLE, path=str(DOSSIER_RAW), unzip=True, quiet=False)
    fichier = trouver_fichier_paysim()
    if not fichier:
        raise SystemExit(f"Téléchargement terminé mais aucun CSV PaySim trouvé dans {DOSSIER_RAW}")
    log.info("PaySim téléchargé : %s", fichier)
    return fichier
