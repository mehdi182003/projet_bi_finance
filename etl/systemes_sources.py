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
S'y ajoutent les défauts courants des extractions bancaires réelles :
  - dérive de format : migration SAB (dates ISO à partir de juillet 2024), nouvelle colonne NORDIC (2025) ;
  - export retouché sous Excel (SAB) : séparateur de milliers en espace insécable ;
  - montants au format comptable (AMERICORE) : « (1,234.56) » et « $1,234.56 » ;
  - pré-autorisations carte en attente (NORDIC, statut PENDING) à côté de l'opération comptabilisée ;
  - vérifications de carte à 0,00 (SAB, DELTA) ;
  - données tardives (AMERICORE) : opérations du dernier jour après la clôture dans le fichier suivant ;
  - fichiers mensuels renvoyés une seconde fois (« _v2 ») ;
  - valeurs nulles codées de plusieurs façons (NULL, N/A, ?, 0000000) ;
  - codes entité en casse ou avec espaces variables (NORDIC, AMERICORE) ;
  - encodage cassé (UTF-8 relu en cp1252) dans les libellés DELTA, en-tête répété en milieu de fichier.
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
    "client_valeur_nulle": 0.004, "montant_nul": 0.0005, "autorisation": 0.02, "montant_comptable": 0.03,
    "symbole_devise": 0.02, "entite_variante": 0.02, "ref_espaces": 0.01, "libelle_mojibake": 0.03,
}
TAUX_FICHIER = {"renvoye": 0.03, "excel": 0.15}   # proportion de fichiers mensuels touchés
VALEURS_NULLES = ["NULL", "N/A", "?", "0000000"]
MIGRATION_SAB = pd.Period("2024-07", "M")          # nouveau format de date (AAAA-MM-JJ) après migration
NOUVELLE_COLONNE_NORDIC = pd.Period("2025-01", "M")  # ajout de la colonne « channel »
HEURE_CLOTURE_AMERICORE = 18                       # au-delà, le dernier jour part dans le fichier suivant
LIGNES_PAR_PAGE_DELTA = 5_000                      # l'état DELTA répète son en-tête à chaque « page »
CANAUX_NORDIC = {"CASH_IN": "BRANCH", "VIREMENT_RECU": "BATCH", "CASH_OUT": "ATM", "PAYMENT": "CARD",
                 "DEBIT": "BATCH", "TRANSFER": "ONLINE"}
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
    nulle = rng.random(len(sortie)) < TAUX["client_valeur_nulle"]      # NULL, N/A, ?, 0000000 selon l'agence
    sortie[nulle] = rng.choice(VALEURS_NULLES, nulle.sum())
    return sortie


def _entite(rng, code: str, n: int) -> np.ndarray:
    """Code entité saisi avec une casse ou des espaces variables sur une partie des lignes."""
    sortie = np.full(n, code, dtype=object)
    touche = rng.random(n) < TAUX["entite_variante"]
    sortie[touche] = rng.choice([code.lower(), f" {code}", f"{code} "], touche.sum())
    return sortie


def _ajouter_doublons(rng, df: pd.DataFrame) -> pd.DataFrame:
    n = int(len(df) * TAUX["doublon"])
    if n == 0:
        return df
    return pd.concat([df, df.sample(n, random_state=int(rng.integers(1e9)))]).sort_values("_ordre", kind="stable")


def _verifications_carte(rng, lot: pd.DataFrame, suffixe: str = "V") -> pd.DataFrame:
    """Vérifications de carte à 0,00 (contrôle de validité au TPE) : lignes en plus, sans effet comptable."""
    cartes = lot[lot.code_type == "PAYMENT"]
    n = int(len(cartes) * TAUX["montant_nul"])
    if n == 0:
        return lot
    zero = cartes.sample(n, random_state=int(rng.integers(1e9))).copy()
    zero["ref_operation"] = zero.ref_operation + suffixe
    zero["montant_devise"] = 0.0
    zero["poids"] = 1
    zero["horodatage"] = zero.horodatage - pd.Timedelta(seconds=40)
    return pd.concat([lot, zero]).sort_values("horodatage", kind="stable")


def _ecrire(df: pd.DataFrame, chemin: Path, sep: str, encodage: str, preambule: str = "", pied: str = "",
            rng=None, entete_par_page: int | None = None) -> int:
    """Écrit un fichier mensuel ; renvoie le nombre de lignes de données écrites (renvoi éventuel compris)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    corps = df.drop(columns=[c for c in df.columns if c.startswith("_")]).to_csv(index=False, sep=sep, lineterminator="\r\n")
    if entete_par_page:                                   # état « imprimé » : en-tête répété à chaque page
        lignes = corps.split("\r\n")
        entete, donnees = lignes[0], lignes[1:]
        pages = [donnees[i:i + entete_par_page] for i in range(0, len(donnees), entete_par_page)]
        corps = "\r\n".join([entete] + [l for k, p in enumerate(pages) for l in ([entete] if k else []) + p])
    contenu = preambule + corps + pied
    if encodage == "utf-8-sig":
        octets = b"\xef\xbb\xbf" + contenu.encode("utf-8", errors="replace")
    else:
        octets = contenu.encode(encodage, errors="replace")
    cibles = [chemin]
    if rng is not None and rng.random() < TAUX_FICHIER["renvoye"]:   # la filiale renvoie le même fichier
        cibles.append(chemin.with_name(chemin.name.replace(".csv.gz", "_v2.csv.gz")))
    for cible in cibles:
        # mtime=0 : compression déterministe => une régénération à l'identique donne exactement les mêmes octets
        with open(cible, "wb") as brut, gzip.GzipFile(filename="", mode="wb", fileobj=brut, compresslevel=9, mtime=0) as f:
            f.write(octets)
    return len(df) * len(cibles)


def _fichiers_mensuels(v: pd.DataFrame, chevauchement: bool, heure_cloture: int | None = None):
    """Découpe par mois ; avec chevauchement, chaque fichier reprend le dernier jour du mois précédent ;
    avec heure de clôture, les opérations du dernier jour passées cette heure partent dans le fichier suivant."""
    mois_fichier = v.horodatage.dt.to_period("M")
    if heure_cloture is not None:
        tardive = v.horodatage.dt.is_month_end & (v.horodatage.dt.hour >= heure_cloture)
        mois_fichier = mois_fichier.where(~tardive, mois_fichier + 1)
    v = v.assign(_mois=mois_fichier)
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
        lot = _verifications_carte(rng, lot)
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        refs = lot.ref_operation.values.astype(object)
        espaces = rng.random(len(refs)) < TAUX["ref_espaces"]                   # saisie avec espaces de bord
        refs[espaces] = [f" {r}  " for r in refs[espaces]]
        format_date = "%Y-%m-%d" if m >= MIGRATION_SAB else "%d/%m/%Y"        # migration du système
        if rng.random() < TAUX_FICHIER["excel"]:                              # fichier retouché sous Excel
            montants = [f"{x:,.2f}".replace(",", "\xa0").replace(".", ",") for x in lot.montant_devise]
        else:
            montants = [f"{x:.2f}".replace(".", ",") for x in lot.montant_devise]
        sortie = pd.DataFrame({
            "REF_OPE": refs,
            "CODE_ETAB": f.code_entite_source,
            "DATE_OPE": lot.horodatage.dt.strftime(format_date).values,
            "HEURE_OPE": lot.horodatage.dt.strftime("%H:%M:%S").values,
            "NUM_CLIENT": _client(rng, lot.id_client.reset_index(drop=True), f.code_filiale).values,
            "LIBELLE_OPE": _variante(rng, lot.code_type.reset_index(drop=True), LIBELLES["SAB"], TAUX["libelle_variante"]).values,
            "NB_OPE": lot.poids.values,
            "MONTANT": montants,
            "SENS": np.where(lot.code_type.map(SENS) > 0, "C", "D"),
            "DEVISE": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, TAUX["devise_variante"]).values,
            "IND_FRAUDE": np.where(lot.est_fraude == 1, "O", "N"),
            "STATUT": lot._statut.values,
        })
        lignes += _ecrire(sortie, racine / f"SAB_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ";", "cp1252",
                          rng=rng)
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
        # pré-autorisations carte : ligne PENDING (montant estimé) avant l'opération comptabilisée
        cartes = lot[lot.code_type == "PAYMENT"]
        attente = cartes.sample(int(len(cartes) * TAUX["autorisation"]), random_state=int(rng.integers(1e9))).copy()
        attente["txn_id"] = attente.ref_operation + "P"
        attente["montant_signe"] = (attente.montant_signe * rng.uniform(1.0, 1.3, len(attente))).round(2)
        attente["statut"] = "PENDING"
        attente["horodatage"] = attente.horodatage - pd.Timedelta(minutes=3)
        lot = pd.concat([lot, erreurs, extournes, attente]).sort_values("horodatage")
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        # le système stocke en UTC : l'heure en double du passage à l'heure d'hiver est rattachée à l'heure d'été
        # (avec ambiguous="NaT", les opérations entre 2 h et 3 h ce jour-là sortaient sans horodatage)
        utc = lot.horodatage.dt.tz_localize(f.fuseau_horaire, ambiguous=np.ones(len(lot), dtype=bool),
                                            nonexistent="shift_forward").dt.tz_convert("UTC")
        montant = lot.montant_signe * (100 if mineures else 1)
        sortie = pd.DataFrame({
            "txn_id": lot.txn_id.values,
            "entity": _entite(rng, f.code_entite_source, len(lot)),
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
        if m >= NOUVELLE_COLONNE_NORDIC:                                      # évolution du format d'export
            sortie.insert(5, "channel", lot.code_type.map(CANAUX_NORDIC).values)
        lignes += _ecrire(sortie, racine / f"NCB_{f.code_entite_source}_{m.strftime('%Y-%m')}.csv.gz", ",", "utf-8-sig",
                          rng=rng)
    return lignes


def export_americore(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    for m, lot in _fichiers_mensuels(v, chevauchement=False, heure_cloture=HEURE_CLOTURE_AMERICORE):
        tests = lot.sample(max(int(len(lot) * TAUX["test"]), 1), random_state=int(rng.integers(1e9))).copy()
        tests["ref_operation"] = "T" + tests.ref_operation
        tests["id_client"] = "TEST-" + tests.id_client.str.split("-").str[1]
        lot = pd.concat([lot, tests]).sort_values("horodatage")
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        code = lot.code_type.map(CODES_AMERICORE)
        credit = (lot.code_type.map(SENS) > 0).values
        montants = np.array([f"{x:,.2f}" for x in lot.montant_devise], dtype=object)   # séparateur de milliers
        comptable = ~credit & (rng.random(len(lot)) < TAUX["montant_comptable"])        # débit noté « (1,234.56) »
        montants[comptable] = [f"({x})" for x in montants[comptable]]
        symbole = "US$" if f.code_devise == "USD" else "C$"
        avec_symbole = ~comptable & (rng.random(len(lot)) < TAUX["symbole_devise"])
        montants[avec_symbole] = [symbole + x for x in montants[avec_symbole]]
        comptes = _client(rng, lot.id_client.reset_index(drop=True).where(~lot.id_client.str.startswith("TEST").values,
                                                                           "X-0"), f.code_filiale + "-", sans_zeros=True)
        comptes[lot.id_client.str.startswith("TEST").values] = lot.id_client[lot.id_client.str.startswith("TEST")].values
        sortie = pd.DataFrame({
            "TxnRef": lot.ref_operation.values,
            "Entity": _entite(rng, f.code_entite_source, len(lot)),
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
        lignes += _ecrire(sortie, racine / f"AMC_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ",", "utf-8",
                          rng=rng)
    return lignes


def _mojibake(texte: str) -> str:
    """Libellé UTF-8 relu en cp1252 par un maillon de la chaîne (« DÉPÔT » -> « DÃ‰PÃ”T »)."""
    return texte.encode("utf-8").decode("cp1252", errors="replace")


def export_delta(rng, v: pd.DataFrame, f: pd.Series, racine: Path) -> int:
    lignes = 0
    for m, lot in _fichiers_mensuels(v, chevauchement=False):
        lot = _verifications_carte(rng, lot)
        lot = lot.assign(_ordre=np.arange(len(lot)))
        lot = _ajouter_doublons(rng, lot)
        suspicion = np.where(lot.est_fraude == 1, "1", "0").astype(object)
        suspicion[rng.random(len(lot)) < TAUX["suspicion_vide"]] = ""
        nature = np.array(_variante(rng, lot.code_type.reset_index(drop=True), LIBELLES["DELTA"], 0.15), dtype=object)
        casse = (rng.random(len(nature)) < TAUX["libelle_mojibake"]) & np.array([not x.isascii() for x in nature])
        nature[casse] = [_mojibake(x) for x in nature[casse]]
        sortie = pd.DataFrame({
            "NUMOPE": lot.ref_operation.values,
            "DATEOPE": lot.horodatage.dt.strftime("%Y%m%d").values,
            "HEUREOPE": lot.horodatage.dt.strftime("%H%M%S").values,
            "CLIENT": _client(rng, lot.id_client.reset_index(drop=True), f.code_filiale).values,
            "NATURE": nature,
            "NBOPE": lot.poids.values,
            "MONTANT": [f"{x:.0f}" for x in lot.montant_devise],
            "DEVISE": _variante(rng, pd.Series([f.code_devise] * len(lot)), DEVISES, 0.05).values,
            "SUSPICION": suspicion,
        })
        preambule = (f"EXTRACTION DELTA - {f.code_entite_source} - {f.nom_filiale.upper()} - PERIODE {m.strftime('%m/%Y')}"
                     f" - EDITEE LE {(m.to_timestamp(how='end') + pd.Timedelta(days=3)).strftime('%d/%m/%Y')}\r\n")
        pied = f"TOTAL;{len(sortie)};{int(lot.montant_devise.round().sum())}\r\n"
        lignes += _ecrire(sortie, racine / f"DELTA_{f.code_entite_source}_{m.strftime('%Y%m')}.csv.gz", ";", "cp1252",
                          preambule, pied, rng=rng, entete_par_page=LIGNES_PAR_PAGE_DELTA)
    return lignes


EXPORTS = {"SAB": export_sab, "NORDIC": export_nordic, "AMERICORE": export_americore, "DELTA": export_delta}


def exporter_filiale(rng, v: pd.DataFrame, f: pd.Series, dossier: Path) -> int:
    """Écrit les exports mensuels bruts d'une filiale dans le format de son système."""
    racine = dossier / f.systeme_source.lower() / f.code_filiale
    for ancien in racine.glob("*.csv.gz"):          # y compris les anciens renvois « _v2 »
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
