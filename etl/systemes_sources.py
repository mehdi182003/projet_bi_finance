"""Exports BRUTS des systèmes bancaires des filiales (données « sales » à nettoyer dans l'ETL).

Dans un groupe bancaire multi-pays, chaque filiale exporte ses opérations depuis son propre
système (core banking), avec son format et ses défauts. On simule ici 4 systèmes réalistes à partir
de la « vérité » produite par etl/generateur_flux.py :

  SAB        France, Benelux, Finlande  ; CSV « ; », cp1252, virgule décimale, dates jj/mm/aaaa,
             montant positif + sens D/C, libellés français
  NORDIC     Suède, Danemark, Norvège   ; CSV « , », UTF-8 avec BOM, horodatage ISO en UTC,
             montant signé, Suède en unités mineures (öre), codes anglais, extournes
  AMERICORE  Canada, États-Unis         ; CSV « , », dates MM/JJ/AAAA + heure AM/PM, colonnes
             débit / crédit séparées, séparateur de milliers, codes numériques, comptes de test
  DELTA      Côte d'Ivoire, Cameroun    ; CSV « ; », cp1252, ligne de titre + ligne de total de
             contrôle, dates aaaammjj, montants entiers, libellés sans norme (accents, abréviations)

Défauts injectés (taux paramétrés ci-dessous, graine fixe => reproductible) : doublons, fichiers
mensuels qui se chevauchent, opérations annulées, écritures erronées puis extournées, comptes de test,
libellés et codes devise non normalisés, identifiants clients manquants ou mal formés.
Tous sont récupérables : après nettoyage, on doit retrouver exactement la vérité (vérifié par le
rapprochement avec les soldes comptables journaliers, également exportés ici).

Sorties (compressées) :
  <dossier>/<systeme>/<filiale>/<fichier mensuel>.csv.gz
  <dossier>/comptabilite/soldes_comptables_journaliers.csv
  avec <dossier> = data/sources_internes (lots de 100, versionné dans Git) ou data/generees/lot_<n>
  (autres tailles de lot, générées en local et ignorées par Git : plusieurs Go).
"""
from __future__ import annotations

import gzip
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .config import DOSSIER_DATA

log = logging.getLogger(__name__)
DOSSIER_SOURCES_INTERNES = DOSSIER_DATA / "sources_internes"
FICHIER_SOLDES = DOSSIER_SOURCES_INTERNES / "comptabilite" / "soldes_comptables_journaliers.csv"
GRAINE_DEFAUTS = 2024

TAUX = {   # proportion de lignes touchées par chaque défaut
    "doublon": 0.004, "annulee": 0.002, "extourne": 0.001, "test": 0.0005,
    "libelle_variante": 0.04, "devise_variante": 0.02, "client_manquant": 0.003,
    "client_sans_zeros": 0.01, "suspicion_vide": 0.10,
}
SENS = {"CASH_IN": 1, "VIREMENT_RECU": 1, "CASH_OUT": -1, "PAYMENT": -1, "DEBIT": -1, "TRANSFER": -1}

LIBELLES = {
    "SAB": {"CASH_IN": ["VERSEMENT ESPECES", "Versement espèces", "VERSEMENT ESPÈCES "],
            "VIREMENT_RECU": ["VIREMENT RECU SEPA", "Virement reçu SEPA", "VIR RECU SEPA"],
            "CASH_OUT": ["RETRAIT DAB", "Retrait DAB ", "RETRAIT  DAB"],
            "PAYMENT": ["PAIEMENT CB", "Paiement CB", "PAIEMENT CARTE"],
            "DEBIT": ["PRELEVEMENT SEPA", "Prélèvement SEPA", "PRLV SEPA"],
            "TRANSFER": ["VIREMENT EMIS SEPA", "Virement émis SEPA", "VIR EMIS SEPA"]},
    "NORDIC": {"CASH_IN": ["CASH_DEPOSIT", "cash_deposit"], "VIREMENT_RECU": ["INCOMING_TRANSFER", "incoming_transfer"],
               "CASH_OUT": ["ATM_WITHDRAWAL", "atm_withdrawal"], "PAYMENT": ["CARD_PAYMENT", "card_payment"],
               "DEBIT": ["DIRECT_DEBIT", "direct_debit"], "TRANSFER": ["OUTGOING_TRANSFER", "outgoing_transfer"]},
    "DELTA": {"CASH_IN": ["DEPOT ESPECES", "DÉPÔT ESPÈCES", "Depot especes", "DEP ESP"],
              "VIREMENT_RECU": ["VIREMENT RECU", "VIR RECU", "Virement reçu", "VIREMENT REÇU"],
              "CASH_OUT": ["RETRAIT GAB", "RET GAB", "Retrait gab ", "RETRAIT GUICHET"],
              "PAYMENT": ["PAIEMENT TPE", "PAIEMENT CARTE", "Paiement TPE", "PAIEMT TPE"],
              "DEBIT": ["PRELEVEMENT", "PRÉLÈVEMENT", "PRLV"],
              "TRANSFER": ["VIREMENT EMIS", "VIR EMIS", "Virement émis", "VIREMENT ÉMIS"]},
}
CODES_AMERICORE = {"CASH_IN": "100", "VIREMENT_RECU": "110", "CASH_OUT": "200", "PAYMENT": "210",
                   "DEBIT": "220", "TRANSFER": "230"}
DESCRIPTIONS_AMERICORE = {"100": "CASH DEPOSIT", "110": "ACH CREDIT PAYROLL", "200": "ATM WITHDRAWAL",
                          "210": "POS PURCHASE", "220": "ACH DEBIT", "230": "WIRE OUT"}
DEVISES = {"EUR": ["EUR", "€", "eur", " EUR"], "SEK": ["SEK", "sek"], "DKK": ["DKK", "dkk"], "NOK": ["NOK", "nok"],
           "USD": ["USD", "US$", "usd"], "CAD": ["CAD", "C$", "cad"], "XOF": ["XOF", "FCFA", "F CFA"],
           "XAF": ["XAF", "FCFA", "F.CFA"]}


# ----------------------------------------------------------------------- outils
def _variante(rng, valeurs_std: pd.Series, variantes: dict, taux: float) -> pd.Series:
    """Remplace une partie des valeurs standard par une variante non normalisée."""
    sortie = valeurs_std.map(lambda v: variantes[v][0]).astype(object)
    touche = rng.random(len(sortie)) < taux
    if touche.any():
        sortie[touche] = [variantes[v][rng.integers(1, len(variantes[v]))] if len(variantes[v]) > 1
                          else variantes[v][0] for v in valeurs_std[touche]]
    return sortie


def _client(rng, ids: pd.Series, prefixe: str, sans_zeros: bool = False) -> pd.Series:
    num = ids.str.split("-").str[1]
    sortie = (prefixe + num).astype(object)
    if sans_zeros:
        z = rng.random(len(sortie)) < TAUX["client_sans_zeros"]
        sortie[z] = [prefixe + str(int(n)) for n in num[z]]
    sortie[rng.random(len(sortie)) < TAUX["client_manquant"]] = ""
    return sortie


def _ajouter_doublons(rng, df: pd.DataFrame) -> pd.DataFrame:
    n = int(len(df) * TAUX["doublon"])
    if n == 0:
        return df
    return pd.concat([df, df.sample(n, random_state=int(rng.integers(1e9)))]).sort_values("_ordre", kind="stable")


def _ecrire(df: pd.DataFrame, chemin: Path, sep: str, encodage: str, preambule: str = "", pied: str = "") -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    corps = df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(index=False, sep=sep, lineterminator="\r\n")
    # mtime=0 : compression déterministe => une régénération à l'identique donne exactement les mêmes octets
    with open(chemin, "wb") as brut, gzip.GzipFile(filename="", mode="wb", fileobj=brut, compresslevel=9, mtime=0) as f:
        if encodage == "utf-8-sig":
            f.write(b"\xef\xbb\xbf")
            encodage = "utf-8"
        f.write((preambule + corps + pied).encode(encodage, errors="replace"))


def _fichiers_mensuels(v: pd.DataFrame, chevauchement: bool):
    """Découpe par mois ; avec chevauchement, chaque fichier reprend le dernier jour du mois précédent."""
    v = v.assign(_mois=v.horodatage.dt.to_period("M"))
    mois = sorted(v._mois.unique())
    for i, m in enumerate(mois):
        lot = v[v._mois == m]
        if chevauchement and i > 0:
            veille = v[(v._mois == mois[i - 1]) & (v.horodatage.dt.date == (m.to_timestamp() - pd.Timedelta(days=1)).date())]
            lot = pd.concat([veille, lot])
        yield m, lot


# --------------------------------------------------------------------- systèmes
def export_sab(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    for m, lot in _fichiers_mensuels(v, chevauchement=True):
        annulees = lot.sample(int(len(lot) * TAUX["annulee"]), random_state=int(rng.integers(1e9))).copy()
        annulees["ref_operation"] = annulees.ref_operation + "A"
        annulees["_statut"] = "ANNULE"
        lot = pd.concat([lot.assign(_statut="VALIDE"), annulees])
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        sortie = pd.DataFrame({
            "REF_OPE": lot.ref_operation.values,
            "CODE_ETAB": f.code_entite_source,
            "DATE_OPE": lot.horodatage.dt.strftime("%d/%m/%Y").values,
            "HEURE_OPE": lot.horodatage.dt.strftime("%H:%M:%S").values,
            "NUM_CLIENT": _client(rng, lot.id_client.reset_index(drop=True), f.code_filiale).values,
            "LIBELLE_OPE": _variante(rng, lot.code_type.reset_index(drop=True), LIBELLES["SAB"], TAUX["libelle_variante"]).values,
            "NB_OPE": lot.poids.values,
            "MONTANT": [f"{x:.2f}".replace(".", ",") for x in lot.montant_devise],
            "SENS": np.where(lot.code_type.map(SENS) > 0, "C", "D"),
            "DEVISE": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, TAUX["devise_variante"]).values,
            "IND_FRAUDE": np.where(lot.est_fraude == 1, "O", "N"),
            "STATUT": lot._statut.values,
        })
        _ecrire(sortie, racine / f"SAB_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ";", "cp1252")
        lignes += len(sortie)
    return lignes


def export_nordic(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    mineures = f.code_devise == "SEK"                         # la Suède exporte en öre
    for m, lot in _fichiers_mensuels(v, chevauchement=False):
        lot = lot.copy()
        lot["txn_id"] = lot.ref_operation
        lot["montant_signe"] = lot.code_type.map(SENS) * lot.montant_devise
        lot["statut"], lot["origine"] = "BOOKED", ""
        # écritures erronées (montant x10) puis extournées : 2 lignes de plus pour chaque cas
        erreurs = lot.sample(int(len(lot) * TAUX["extourne"]), random_state=int(rng.integers(1e9))).copy()
        erreurs["txn_id"] = erreurs.ref_operation + "E"
        erreurs["montant_signe"] = erreurs.montant_signe * 10
        extournes = erreurs.copy()
        extournes["txn_id"] = erreurs.ref_operation + "R"
        extournes["montant_signe"] = -erreurs.montant_signe
        extournes["statut"], extournes["origine"] = "REVERSAL", erreurs.txn_id
        extournes["horodatage"] = extournes.horodatage + pd.Timedelta(minutes=47)
        lot = pd.concat([lot, erreurs, extournes]).sort_values("horodatage")
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        utc = lot.horodatage.dt.tz_localize(f.fuseau_horaire, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
        montant = lot.montant_signe * (100 if mineures else 1)
        sortie = pd.DataFrame({
            "txn_id": lot.txn_id.values,
            "entity": f.code_entite_source,
            "booking_ts": utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ").values,
            "customer_ref": _client(rng, lot.id_client.reset_index(drop=True), f.code_filiale + "-").values,
            "txn_type": _variante(rng, lot.code_type.reset_index(drop=True), LIBELLES["NORDIC"], TAUX["libelle_variante"]).values,
            "txn_count": lot.poids.values,
            "amount": [f"{x:.0f}" if mineures else f"{x:.2f}" for x in montant],
            "amount_unit": "MINOR" if mineures else "MAJOR",
            "currency_code": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, TAUX["devise_variante"]).values,
            "fraud_flag": np.where(lot.est_fraude == 1, "true", "false"),
            "record_status": lot.statut.values,
            "reversal_of": lot.origine.values,
        })
        _ecrire(sortie, racine / f"NCB_{f.code_entite_source}_{m.strftime('%Y-%m')}.csv.gz", ",", "utf-8-sig")
        lignes += len(sortie)
    return lignes


def export_americore(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    for m, lot in _fichiers_mensuels(v, chevauchement=False):
        tests = lot.sample(max(int(len(lot) * TAUX["test"]), 1), random_state=int(rng.integers(1e9))).copy()
        tests["ref_operation"] = "T" + tests.ref_operation
        tests["id_client"] = "TEST-" + tests.id_client.str.split("-").str[1]
        lot = pd.concat([lot, tests]).sort_values("horodatage")
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        code = lot.code_type.map(CODES_AMERICORE)
        credit = lot.code_type.map(SENS) > 0
        montants = [f"{x:,.2f}" for x in lot.montant_devise]           # séparateur de milliers
        comptes = _client(rng, lot.id_client.reset_index(drop=True).where(~lot.id_client.str.startswith("TEST").values,
                                                                           "X-0"), f.code_filiale + "-", sans_zeros=True)
        comptes[lot.id_client.str.startswith("TEST").values] = lot.id_client[lot.id_client.str.startswith("TEST")].values
        sortie = pd.DataFrame({
            "TxnRef": lot.ref_operation.values,
            "Entity": f.code_entite_source,
            "TxnDate": lot.horodatage.dt.strftime("%m/%d/%Y").values,
            "TxnTime": lot.horodatage.dt.strftime("%I:%M:%S %p").values,
            "AccountNo": comptes.values,
            "TxnCode": code.values,
            "Description": code.map(DESCRIPTIONS_AMERICORE).values,
            "ItemCount": lot.poids.values,
            "DebitAmount": np.where(~credit, montants, ""),
            "CreditAmount": np.where(credit, montants, ""),
            "Currency": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, TAUX["devise_variante"]).values,
            "FraudFlag": np.where(lot.est_fraude == 1, "Y", "N"),
        })
        _ecrire(sortie, racine / f"AMC_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ",", "utf-8")
        lignes += len(sortie)
    return lignes


def export_delta(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    for m, lot in _fichiers_mensuels(v, chevauchement=False):
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        suspicion = np.where(lot.est_fraude == 1, "1", "0").astype(object)
        suspicion[rng.random(len(lot)) < TAUX["suspicion_vide"]] = ""
        sortie = pd.DataFrame({
            "NUMOPE": lot.ref_operation.values,
            "DATEOPE": lot.horodatage.dt.strftime("%Y%m%d").values,
            "HEUREOPE": lot.horodatage.dt.strftime("%H%M%S").values,
            "CLIENT": _client(rng, lot.id_client.reset_index(drop=True), f.code_filiale).values,
            "NATURE": _variante(rng, lot.code_type.reset_index(drop=True), LIBELLES["DELTA"], 0.15).values,
            "NBOPE": lot.poids.values,
            "MONTANT": [f"{x:.0f}" for x in lot.montant_devise],
            "DEVISE": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, 0.05).values,
            "SUSPICION": suspicion,
        })
        preambule = (f"EXTRACTION DELTA - {f.code_entite_source} - {f.nom_filiale.upper()} - PERIODE {m.strftime('%m/%Y')}"
                     f" - EDITEE LE {(m.to_timestamp(how='end') + pd.Timedelta(days=3)).strftime('%d/%m/%Y')}\r\n")
        pied = f"TOTAL;{len(sortie)};{int(lot.montant_devise.round().sum())}\r\n"
        _ecrire(sortie, racine / f"DELTA_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ";", "cp1252", preambule, pied)
        lignes += len(sortie)
    return lignes


EXPORTS = {"SAB": export_sab, "NORDIC": export_nordic, "AMERICORE": export_americore, "DELTA": export_delta}


def exporter_filiale(rng, v: pd.DataFrame, f: pd.Series, dossier: Path) -> int:
    """Écrit les exports mensuels bruts d'une filiale dans le format de son système."""
    racine = dossier / f.systeme_source.lower() / f.code_filiale
    for ancien in racine.glob("*.csv.gz"):
        ancien.unlink()
    n = EXPORTS[f.systeme_source](rng, v, f, racine)
    log.info("  %-3s : %s lignes brutes exportées (%s), %s opérations réelles",
             f.code_filiale, f"{n:,}".replace(",", " "), f.systeme_source, f"{len(v):,}".replace(",", " "))
    return n


def soldes_filiale(v: pd.DataFrame) -> pd.DataFrame:
    """Soldes comptables journaliers (grand livre) d'une filiale : référence pour le rapprochement."""
    montant = v.montant_devise * v.poids * v.code_type.map(SENS)
    s = pd.DataFrame({"code_filiale": v.code_filiale.values, "date_comptable": v.horodatage.dt.date.values,
                      "total_credits": montant.clip(lower=0).values, "total_debits": (-montant).clip(lower=0).values,
                      "nb_operations": v.poids.values})
    return s.groupby(["code_filiale", "date_comptable"], sort=True).sum().reset_index()


def ecrire_soldes(soldes: list[pd.DataFrame], dossier: Path) -> Path:
    chemin = dossier / "comptabilite" / FICHIER_SOLDES.name
    chemin.parent.mkdir(parents=True, exist_ok=True)
    (pd.concat(soldes, ignore_index=True).sort_values(["code_filiale", "date_comptable"])
       .round(2).to_csv(chemin, index=False))
    log.info("Soldes comptables journaliers -> %s", chemin)
    return chemin
