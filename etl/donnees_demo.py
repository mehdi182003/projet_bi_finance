"""Transactions de DÉMONSTRATION (synthétiques), au format exact du CSV PaySim.

Sert uniquement à tester la chaîne de bout en bout sans Internet ni compte Kaggle
(`python pipeline.py --demo`). Pour la soutenance, utiliser les vraies données.

Le générateur reproduit les caractéristiques connues de PaySim :
  - 743 steps horaires, cycle jour/nuit marqué ;
  - forte activité jusqu'au step ~400 puis chute brutale du volume ;
  - mix de types (CASH_OUT, PAYMENT, CASH_IN, TRANSFER, DEBIT) et montants log-normaux ;
  - ~0,13 % de fraude, concentrée sur TRANSFER et CASH_OUT.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOSSIER_DEMO, GRAINE_ALEATOIRE

log = logging.getLogger(__name__)

TYPES = {  # type: (part des transactions, montant moyen PaySim)
    "CASH_OUT": (0.352, 176_000),
    "PAYMENT": (0.338, 13_000),
    "CASH_IN": (0.220, 168_000),
    "TRANSFER": (0.084, 910_000),
    "DEBIT": (0.006, 5_500),
}


def generer_paysim(nb_lignes: int = 200_000, graine: int = GRAINE_ALEATOIRE) -> pd.DataFrame:
    rng = np.random.default_rng(graine)
    steps = np.arange(1, 744)
    heure = (steps - 1) % 24
    profil_jour = 0.15 + np.exp(-((heure - 13) ** 2) / 30)          # pic vers 13h, creux la nuit
    regime = np.where(steps <= 400, 1.0, 0.04)                      # chute d'activité après ~step 400
    poids = profil_jour * regime
    step = rng.choice(steps, size=nb_lignes, p=poids / poids.sum())

    noms_types = list(TYPES)
    parts = np.array([TYPES[t][0] for t in noms_types])
    type_ = rng.choice(noms_types, size=nb_lignes, p=parts / parts.sum())
    moyenne = np.array([TYPES[t][1] for t in type_])
    sigma = 1.0
    montant = np.round(rng.lognormal(np.log(moyenne) - sigma**2 / 2, sigma), 2)

    # ~30 % des clients ont un solde nul (caractéristique de PaySim)
    solde_avant = np.where(rng.random(nb_lignes) < 0.3, 0.0, np.round(rng.lognormal(np.log(400_000), 1.4, nb_lignes), 2))
    entrant = type_ == "CASH_IN"
    solde_apres = np.where(entrant, solde_avant + montant, np.maximum(solde_avant - montant, 0.0))

    nb_clients = int(nb_lignes * 0.95)                               # quelques clients récurrents
    clients = np.char.add("C", rng.integers(10**8, 10**10, nb_clients).astype(str))
    name_orig = rng.choice(clients, nb_lignes)
    vers_commercant = type_ == "PAYMENT"
    name_dest = np.where(
        vers_commercant,
        np.char.add("M", rng.integers(10**8, 10**10, nb_lignes).astype(str)),
        rng.choice(clients, nb_lignes),
    )
    dest_avant = np.where(vers_commercant, 0.0, np.round(rng.lognormal(np.log(500_000), 1.5, nb_lignes), 2))
    dest_apres = np.where(vers_commercant, 0.0, np.where(entrant, np.maximum(dest_avant - montant, 0), dest_avant + montant))

    fraude_possible = np.isin(type_, ["TRANSFER", "CASH_OUT"])
    is_fraud = (fraude_possible & (rng.random(nb_lignes) < 0.0035)).astype(int)
    is_flagged = (is_fraud.astype(bool) & (type_ == "TRANSFER") & (montant > 200_000) & (rng.random(nb_lignes) < 0.02)).astype(int)

    df = pd.DataFrame({
        "step": step, "type": type_, "amount": montant,
        "nameOrig": name_orig, "oldbalanceOrg": solde_avant, "newbalanceOrig": np.round(solde_apres, 2),
        "nameDest": name_dest, "oldbalanceDest": dest_avant, "newbalanceDest": np.round(dest_apres, 2),
        "isFraud": is_fraud, "isFlaggedFraud": is_flagged,
    })
    return df.sort_values("step", kind="stable").reset_index(drop=True)


def generer_jeu_demo(nb_lignes: int = 200_000) -> Path:
    """Seules les transactions sont synthétiques : les taux de change restent les vrais (Webstat)."""
    DOSSIER_DEMO.mkdir(parents=True, exist_ok=True)
    fichier_paysim = DOSSIER_DEMO / "paysim_demo.csv"
    log.info("Génération de %d transactions synthétiques au format PaySim...", nb_lignes)
    generer_paysim(nb_lignes).to_csv(fichier_paysim, index=False)
    log.info("Jeu de démonstration écrit dans %s", fichier_paysim)
    return fichier_paysim
