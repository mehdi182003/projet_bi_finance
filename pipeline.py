"""Orchestrateur du POC Crésus : python pipeline.py [--demo] [--etapes ...]

Étapes (dans l'ordre) :
  extract   : cours BCE (Webstat), séries réelles des banques centrales (cache data/sources/), PaySim si présent
  generer   : OPTIONNELLE (--regenerer) : reconstruit les exports bruts des filiales (data/sources_internes/,
              versionnés dans Git) à partir des dépôts réels et de PaySim
  load      : charge les exports bruts tels quels dans le schéma raw de PostgreSQL (incrémental, idempotent)
  dbt       : référentiels (seeds) + modèles staging/intermediate/marts + tests
  prevision : modèles prédictifs Python (Holt-Winters + Monte-Carlo) -> schéma ml
  dbt_prev  : marts de prévision (dbt) qui exploitent les sorties du schéma ml + tests

Exemples :
  python pipeline.py                  # tout, à partir des fichiers versionnés (PaySim facultatif)
  python pipeline.py --regenerer      # reconstruit aussi les exports bruts (nécessite PaySim)
  python pipeline.py --demo           # texture PaySim synthétique (test hors Kaggle) ; séries réelles conservées
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

ETAPES = ["extract", "generer", "load", "dbt", "prevision", "dbt_prev"]
PAR_DEFAUT = ["extract", "load", "dbt", "prevision", "dbt_prev"]
log = logging.getLogger("cresus")


def executer_dbt(*arguments: str, bloquant: bool = True) -> None:
    executable = shutil.which("dbt")
    if not executable:
        raise SystemExit("dbt introuvable : pip install -r requirements.txt")
    commande = [executable, *arguments, "--profiles-dir", str(DOSSIER_DBT), "--project-dir", str(DOSSIER_DBT)]
    log.info("$ dbt %s", " ".join(arguments))
    if subprocess.run(commande, cwd=DOSSIER_DBT).returncode != 0:
        if bloquant:
            raise SystemExit(f"Échec de 'dbt {' '.join(arguments)}' (voir le détail ci-dessus)")
        log.warning("'dbt %s' signale un problème (non bloquant)", " ".join(arguments))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="transactions synthétiques au format PaySim (les taux restent réels)")
    parser.add_argument("--demo-lignes", type=int, default=200_000, help="taille du jeu synthétique")
    parser.add_argument("--etapes", nargs="+", choices=ETAPES, default=None)
    parser.add_argument("--regenerer", action="store_true", help="reconstruire les exports bruts des filiales")
    args = parser.parse_args()
    if args.etapes is None:
        args.etapes = (["extract", "generer"] + PAR_DEFAUT[1:]) if args.regenerer else PAR_DEFAUT
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    debut = time.time()

    fichier_paysim = fichier_taux = None
    if "extract" in args.etapes:
        log.info("=== 1. EXTRACT ===")
        from etl.extraction_bce import extraire_taux_bce
        if args.demo:
            from etl.donnees_demo import generer_jeu_demo
            fichier_paysim = generer_jeu_demo(args.demo_lignes)
        elif args.regenerer:
            from etl.extraction_paysim import extraire_paysim
            fichier_paysim = extraire_paysim()   # indispensable pour reconstruire les exports
        else:
            from etl.extraction_paysim import trouver_fichier_paysim
            fichier_paysim = trouver_fichier_paysim()   # facultatif : sert à la page Qualité
            if fichier_paysim is None:
                log.info("PaySim absent : facultatif (seule la page « Qualité » sur PaySim restera vide).")
        fichier_taux = extraire_taux_bce()
        from etl.sources_reelles import assurer_cache
        assurer_cache()

    if fichier_paysim is None:  # étape extract sautée : on reprend les fichiers existants
        from etl.config import DOSSIER_DEMO
        from etl.extraction_bce import FICHIER_SORTIE
        from etl.extraction_paysim import trouver_fichier_paysim
        fichier_paysim = DOSSIER_DEMO / "paysim_demo.csv" if args.demo else trouver_fichier_paysim()
        fichier_taux = FICHIER_SORTIE

    if "generer" in args.etapes:
        log.info("=== 2. RECONSTRUCTION DES EXPORTS BRUTS DES FILIALES ===")
        from etl.generateur_flux import generer
        generer(fichier_paysim)

    if "load" in args.etapes:
        log.info("=== 3. LOAD (PostgreSQL, schéma raw) ===")
        from etl.chargement_raw import charger_paysim, charger_taux_bce, creer_schema_raw
        from etl.chargement_sources_internes import charger_exports_bruts
        creer_schema_raw()
        if fichier_paysim is not None and fichier_paysim.exists():
            charger_paysim(fichier_paysim)
        charger_taux_bce(fichier_taux)
        charger_exports_bruts()

    if "dbt" in args.etapes:
        log.info("=== 4. TRANSFORM (dbt : seeds, modèles, tests) ===")
        executer_dbt("source", "freshness", bloquant=False)   # alerte si l'export Webstat est ancien
        executer_dbt("build", "--exclude", "tag:prevision")

    if "prevision" in args.etapes:
        log.info("=== 5. ANALYSE PRÉDICTIVE (Python) ===")
        from etl.prevision import lancer_previsions
        lancer_previsions()
        log.info("Contrôle a posteriori sur les dépôts réels de janvier 2026...")
        try:
            from etl.controle_a_posteriori import controler
            controler()
        except Exception as exc:          # sans Internet : on continue sans ce contrôle
            log.warning("Contrôle a posteriori ignoré : %s", exc)

    if "dbt_prev" in args.etapes:
        log.info("=== 6. MARTS DE PRÉVISION (dbt) ===")
        executer_dbt("build", "--select", "tag:prevision")

    log.info("Pipeline terminé en %.1f min. Ouvrir Power BI et se connecter au schéma 'marts'.", (time.time() - debut) / 60)


if __name__ == "__main__":
    sys.exit(main())
