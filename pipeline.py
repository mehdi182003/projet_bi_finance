"""Orchestrateur du POC Crésus : python pipeline.py [--demo] [--etapes ...]

Étapes (dans l'ordre) :
  extract   : récupère PaySim (Kaggle) et les taux BCE dans data/raw/
  load      : crée le schéma raw et charge les fichiers dans PostgreSQL (COPY)
  dbt       : référentiels (seeds) + modèles staging/intermediate/marts + tests
  prevision : modèles prédictifs Python (Holt-Winters + Monte-Carlo) -> schéma ml
  dbt_prev  : marts de prévision (dbt) qui exploitent les sorties du schéma ml + tests

Exemples :
  python pipeline.py                  # tout, avec les vraies données
  python pipeline.py --demo           # transactions synthétiques + vrais taux Webstat (test rapide)
  python pipeline.py --etapes dbt prevision dbt_prev
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import time

from etl.config import DOSSIER_DBT

ETAPES = ["extract", "load", "dbt", "prevision", "dbt_prev"]
log = logging.getLogger("cresus")


def executer_dbt(*arguments: str) -> None:
    executable = shutil.which("dbt")
    if not executable:
        raise SystemExit("dbt introuvable : pip install -r requirements.txt")
    commande = [executable, *arguments, "--profiles-dir", str(DOSSIER_DBT), "--project-dir", str(DOSSIER_DBT)]
    log.info("$ dbt %s", " ".join(arguments))
    if subprocess.run(commande, cwd=DOSSIER_DBT).returncode != 0:
        raise SystemExit(f"Échec de 'dbt {' '.join(arguments)}' (voir le détail ci-dessus)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="transactions synthétiques au format PaySim (les taux restent réels)")
    parser.add_argument("--demo-lignes", type=int, default=200_000, help="taille du jeu synthétique")
    parser.add_argument("--etapes", nargs="+", choices=ETAPES, default=ETAPES)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    debut = time.time()

    fichier_paysim = fichier_taux = None
    if "extract" in args.etapes:
        log.info("=== 1. EXTRACT ===")
        from etl.extraction_bce import extraire_taux_bce
        if args.demo:
            from etl.donnees_demo import generer_jeu_demo
            fichier_paysim = generer_jeu_demo(args.demo_lignes)
        else:
            from etl.extraction_paysim import extraire_paysim
            fichier_paysim = extraire_paysim()
        fichier_taux = extraire_taux_bce()

    if "load" in args.etapes:
        log.info("=== 2. LOAD (PostgreSQL, schéma raw) ===")
        from etl.chargement_raw import charger_paysim, charger_taux_bce, creer_schema_raw
        if fichier_paysim is None:  # étape extract sautée : on reprend les fichiers existants
            from etl.config import DOSSIER_DEMO
            from etl.extraction_bce import FICHIER_SORTIE
            from etl.extraction_paysim import trouver_fichier_paysim
            fichier_paysim = DOSSIER_DEMO / "paysim_demo.csv" if args.demo else trouver_fichier_paysim()
            fichier_taux = FICHIER_SORTIE
        creer_schema_raw()
        charger_paysim(fichier_paysim)
        charger_taux_bce(fichier_taux)

    if "dbt" in args.etapes:
        log.info("=== 3. TRANSFORM (dbt : seeds, modèles, tests) ===")
        executer_dbt("build", "--exclude", "tag:prevision")

    if "prevision" in args.etapes:
        log.info("=== 4. ANALYSE PRÉDICTIVE (Python) ===")
        from etl.prevision import lancer_previsions
        lancer_previsions()

    if "dbt_prev" in args.etapes:
        log.info("=== 5. MARTS DE PRÉVISION (dbt) ===")
        executer_dbt("build", "--select", "tag:prevision")

    log.info("Pipeline terminé en %.1f min. Ouvrir Power BI et se connecter au schéma 'marts'.", (time.time() - debut) / 60)


if __name__ == "__main__":
    sys.exit(main())
