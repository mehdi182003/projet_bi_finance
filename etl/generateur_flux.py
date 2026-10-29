"""Générateur des flux de trésorerie 2023-2025 de ZF Banque, ANCRÉ sur des séries réelles.

Pourquoi : aucune banque ne publie ses transactions clients (secret bancaire, RGPD). PaySim seul ne
couvre que 31 jours et présente des artefacts (jours « morts », fraude constante, soldes incohérents,
pas de flux entrants interbancaires). On construit donc 3 ans de flux en combinant :

  1. NIVEAU, TENDANCE, CHOCS - RÉELS : encours de dépôts à vue publiés par les banques centrales
     (data/sources/depots_reels_2023_2025.csv), à l'échelle de ZF Banque via une part de marché
     par pays (dbt/seeds/ref_filiales.csv). Les flux nets cumulés retombent EXACTEMENT sur ces
     encours à chaque date publiée (fin de mois ; chaque semaine pour les États-Unis).
  2. CALENDRIER - RÉEL : jours fériés de chaque pays (bibliothèque holidays), pas de virement le
     week-end, salaires en fin de mois (Europe, Afrique) ou deux fois par mois (Amérique du Nord),
     prélèvements et loyers en début de mois. (Hypothèses documentées, paramétrables ci-dessous.)
  3. TEXTURE - RÉELLE : chaque opération est tirée parmi les 4,9 M transactions réelles de PaySim
     (fenêtre stable) : type, montant, heure de la journée, fraude.
  4. CHANGE - RÉEL : cours BCE du jour (Webstat) pour passer des tickets en EUR à la devise locale.

Volume : chaque ligne représente POIDS opérations (échantillon pondéré), ce qui donne ~4 M lignes
pour 3 ans au lieu de ~400 M : le pipeline reste exécutable sur un ordinateur portable.

Sorties : data/raw/transactions_zf_2023_2025.csv et data/raw/ancrages_zf.csv
"""
from __future__ import annotations

import logging
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

from .config import DOSSIER_DBT, DOSSIER_RAW, FICHIER_WEBSTAT, GRAINE_ALEATOIRE
from .extraction_bce import lire_webstat
from .extraction_paysim import trouver_fichier_paysim
from .sources_reelles import FICHIER_DEPOTS

log = logging.getLogger(__name__)

DEBUT, FIN = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31")
DATE_INITIALE = pd.Timestamp("2022-12-31")
POIDS = 100                     # opérations représentées par une ligne
TAUX_ROTATION = 0.008           # décaissements bruts d'un jour ouvré / encours de dépôts (PaySim réel : 0,78 %)
PART_MIN_ENTREES = 0.30         # les encaissements d'une période valent au moins 30 % des décaissements
VALEUR_UNITE_PAYSIM_EUR = 0.01  # 1 unité PaySim = 0,01 EUR (transaction médiane ~750 EUR)
BRUIT_JOUR = 0.15               # écart-type log du bruit quotidien
STEPS_STABLES = (121, 408)      # fenêtre d'activité stable de PaySim (docs/06)
FICHIER_TRANSACTIONS = DOSSIER_RAW / "transactions_zf_2023_2025.csv"
FICHIER_ANCRAGES = DOSSIER_RAW / "ancrages_zf.csv"

TYPES_SORTIE_OUVRE = ["CASH_OUT", "PAYMENT", "DEBIT", "TRANSFER"]
TYPES_SORTIE_WEEKEND = ["CASH_OUT", "PAYMENT"]          # cartes et retraits seulement le week-end
PART_VIREMENTS_RECUS = 0.70                            # jours ouvrés : 70 % virements reçus, 30 % dépôts d'espèces


# ------------------------------------------------------------------ calendrier
def calendrier(code_pays: str, profil_paie: str, rng: np.random.Generator) -> pd.DataFrame:
    jours = pd.date_range(DEBUT, FIN, freq="D")
    feries = holidays.country_holidays(code_pays, years=range(DEBUT.year, FIN.year + 1))
    c = pd.DataFrame({"date": jours})
    c["est_ferie"] = c.date.dt.date.map(lambda d: d in feries)
    c["est_ouvre"] = (c.date.dt.weekday < 5) & ~c.est_ferie
    # rang du jour ouvré dans le mois, en partant du début et de la fin
    c["mois"] = c.date.dt.to_period("M")
    c["rang_ouvre"] = c.groupby("mois").est_ouvre.cumsum().where(c.est_ouvre, 0)
    c["rang_ouvre_fin"] = c[::-1].groupby("mois").est_ouvre.cumsum()[::-1].where(c.est_ouvre, 0)

    # Décaissements : cartes et retraits tous les jours, virements/prélèvements les jours ouvrés,
    # pic en début de mois (loyers, factures, prélèvements).
    w_out = np.where(c.est_ouvre, 1.0, 0.35)
    w_out = w_out * np.where(c.est_ouvre & (c.rang_ouvre <= 3), 1.35, 1.0)
    # Encaissements : salaires en fin de mois (Europe, Afrique) ou le 15 et en fin de mois (Amérique du Nord).
    w_in = np.where(c.est_ouvre, 1.0, 0.20)
    if profil_paie == "bimensuel":
        quinze = c.est_ouvre & (c.date.dt.day >= 13) & (c.date.dt.day <= 15)
        w_in = w_in * np.where(quinze | (c.est_ouvre & (c.rang_ouvre_fin == 1)), 3.0, 1.0)
    else:
        w_in = w_in * np.where(c.est_ouvre & (c.rang_ouvre_fin <= 2), 4.0, 1.0)
    c["w_out"] = w_out * rng.lognormal(0, BRUIT_JOUR, len(c))
    c["w_in"] = w_in * rng.lognormal(0, BRUIT_JOUR, len(c))
    return c


# --------------------------------------------------------------- flux journaliers
def ancrages_filiale(depots: pd.DataFrame, part_pct: float) -> pd.DataFrame:
    """Encours ZF aux dates publiées, avec un point initial au 31/12/2022 (interpolé si besoin)."""
    s = depots.set_index("date_ancrage").encours.sort_index() * part_pct / 100
    if DATE_INITIALE not in s.index:
        s.loc[DATE_INITIALE] = np.nan
        s = s.sort_index().interpolate(method="time")
    s = s[(s.index >= DATE_INITIALE) & (s.index <= FIN)]
    a = s.rename("encours_zf_devise").reset_index()
    a["est_point_initial"] = a.date_ancrage == DATE_INITIALE
    a = a.merge(depots[["date_ancrage", "est_interpole", "source"]], on="date_ancrage", how="left")
    a["est_interpole"] = a.est_interpole.fillna(True).astype(bool)   # point initial interpolé (série hebdo)
    a["source"] = a.source.fillna(depots.source.iloc[0])
    return a


def flux_journaliers(cal: pd.DataFrame, ancrages: pd.DataFrame) -> pd.DataFrame:
    """Encaissements et décaissements quotidiens (devise locale) dont le cumul respecte les ancrages."""
    dates = ancrages.date_ancrage.tolist()
    valeurs = ancrages.encours_zf_devise.tolist()
    # encours « de référence » quotidien (interpolation linéaire entre ancrages) pour dimensionner les volumes
    ref = pd.Series(valeurs, index=dates).reindex(pd.date_range(DATE_INITIALE, FIN)).interpolate()
    c = cal.copy()
    c["encours_ref"] = ref.reindex(c.date).values
    c["sortie_base"] = TAUX_ROTATION * c.encours_ref * c.w_out / c.loc[c.est_ouvre, "w_out"].mean()
    c["periode"] = np.searchsorted(np.array(dates[1:], dtype="datetime64[ns]"), c.date.values, side="left")
    morceaux = []
    for k, g in c.groupby("periode"):
        delta = valeurs[k + 1] - valeurs[k]
        sorties = g.sortie_base.sum()
        entrees = sorties + delta
        if entrees < PART_MIN_ENTREES * sorties:       # forte décollecte : on augmente les sorties
            sorties = -delta / (1 - PART_MIN_ENTREES)
            entrees = PART_MIN_ENTREES * sorties
        g = g.assign(decaissements=sorties * g.w_out / g.w_out.sum(),
                     encaissements=entrees * g.w_in / g.w_in.sum())
        morceaux.append(g)
    return pd.concat(morceaux)[["date", "est_ouvre", "encaissements", "decaissements"]]


# ------------------------------------------------------------------ transactions
def charger_texture(fichier: Path | None = None) -> pd.DataFrame:
    fichier = fichier or trouver_fichier_paysim()
    if fichier is None:
        raise SystemExit("PaySim introuvable dans data/raw/ : lancer d'abord l'extraction (pipeline.py).")
    log.info("Lecture de la texture PaySim (%s)...", fichier.name)
    p = pd.read_csv(fichier, usecols=["step", "type", "amount", "isFraud"])
    p = p[(p.step.between(*STEPS_STABLES)) & (p.amount > 0)]
    p["heure"] = (p.step - 1) % 24
    p["montant_eur"] = p.amount * VALEUR_UNITE_PAYSIM_EUR
    return p[["type", "montant_eur", "heure", "isFraud"]].reset_index(drop=True)


def tirer(pool: pd.DataFrame, cibles_eur: np.ndarray, jours: np.ndarray, rng) -> pd.DataFrame:
    """Tire des opérations réelles pour chaque jour puis ajuste les montants au total cible du jour."""
    ticket_moyen = pool.montant_eur.mean()
    n = np.maximum(np.rint(cibles_eur / (POIDS * ticket_moyen)).astype(int), (cibles_eur > 0).astype(int))
    idx = rng.integers(0, len(pool), n.sum())
    t = pool.iloc[idx].reset_index(drop=True)
    t["jour"] = np.repeat(jours, n)
    somme = np.bincount(np.repeat(np.arange(len(jours)), n), weights=t.montant_eur.values * POIDS,
                        minlength=len(jours))
    facteur = np.divide(cibles_eur, somme, out=np.zeros_like(cibles_eur), where=somme > 0)
    t["montant_eur"] = t.montant_eur.values * np.repeat(facteur, n)
    return t


def transactions_filiale(f: pd.Series, flux: pd.DataFrame, texture: pd.DataFrame, taux: pd.Series,
                         rng: np.random.Generator) -> pd.DataFrame:
    flux = flux.reset_index(drop=True)
    jours = flux.date.values
    taux_jour = taux.reindex(flux.date).ffill().bfill().values         # devise locale pour 1 EUR
    morceaux = []
    for ouvre in (True, False):
        m = flux.est_ouvre.values == ouvre
        types_sortie = TYPES_SORTIE_OUVRE if ouvre else TYPES_SORTIE_WEEKEND
        sorties = tirer(texture[texture.type.isin(types_sortie)], flux.decaissements.values[m] / taux_jour[m],
                        jours[m], rng)
        entrees = tirer(texture[texture.type == "CASH_IN"], flux.encaissements.values[m] / taux_jour[m],
                        jours[m], rng)
        if ouvre:
            entrees.loc[rng.random(len(entrees)) < PART_VIREMENTS_RECUS, "type"] = "VIREMENT_RECU"
        morceaux += [sorties, entrees]
    t = pd.concat(morceaux, ignore_index=True)
    t["taux"] = pd.Series(taux_jour, index=jours).reindex(t.jour).values
    nb_clients = max(int(flux.decaissements.mean() * 120 / 2_000 / taux_jour.mean()), 1_000)
    rang = np.floor(nb_clients * rng.random(len(t)) ** 2.5).astype(int)   # quelques clients très actifs
    return pd.DataFrame({
        "horodatage": pd.to_datetime(t.jour) + pd.to_timedelta(t.heure, unit="h")
                      + pd.to_timedelta(rng.integers(0, 3600, len(t)), unit="s"),
        "code_filiale": f.code_filiale,
        "code_type": t.type.values,
        "montant_devise": np.round(t.montant_eur.values * t.taux.values, 2),
        "poids": POIDS,
        "id_client": [f"{f.code_filiale}-{r:07d}" for r in rang],
        "est_fraude": t.isFraud.values.astype(int),
    })


def generer(fichier_paysim: Path | None = None) -> tuple[Path, Path]:
    rng = np.random.default_rng(GRAINE_ALEATOIRE)
    filiales = pd.read_csv(DOSSIER_DBT / "seeds" / "ref_filiales.csv")
    depots = pd.read_csv(FICHIER_DEPOTS, parse_dates=["date_ancrage"])
    change = lire_webstat(FICHIER_WEBSTAT)
    change["date_cours"] = pd.to_datetime(change.date_cours)
    texture = charger_texture(fichier_paysim)

    tous_ancrages = []
    FICHIER_TRANSACTIONS.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER_TRANSACTIONS, "w", encoding="utf-8", newline="") as sortie:
        entete = True
        for _, f in filiales.iterrows():
            if f.code_devise == "EUR":
                taux = pd.Series(1.0, index=pd.date_range(DATE_INITIALE, FIN))
            elif f.code_devise in ("XOF", "XAF"):
                taux = pd.Series(655.957, index=pd.date_range(DATE_INITIALE, FIN))
            else:
                taux = change[change.code_devise == f.code_devise].set_index("date_cours").taux
            anc = ancrages_filiale(depots[depots.code_filiale == f.code_filiale], f.part_de_marche_depots_pct)
            anc.insert(0, "code_filiale", f.code_filiale)
            tous_ancrages.append(anc)
            cal = calendrier(f.code_calendrier, f.profil_paie, rng)
            flux = flux_journaliers(cal, anc)
            t = transactions_filiale(f, flux, texture, taux, rng)
            t.sort_values("horodatage").to_csv(sortie, index=False, header=entete, date_format="%Y-%m-%d %H:%M:%S")
            entete = False
            log.info("  %-3s : %s lignes (%s opérations), encours %s -> %s %s", f.code_filiale,
                     f"{len(t):,}".replace(",", " "), f"{len(t) * POIDS:,}".replace(",", " "),
                     f"{anc.encours_zf_devise.iloc[0] / 1e9:,.1f} Md", f"{anc.encours_zf_devise.iloc[-1] / 1e9:,.1f} Md",
                     f.code_devise)
    pd.concat(tous_ancrages).to_csv(FICHIER_ANCRAGES, index=False)
    return FICHIER_TRANSACTIONS, FICHIER_ANCRAGES


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    generer()
