"""Étape ANALYSE PRÉDICTIVE : prévision des flux de trésorerie et des taux de change.

1) Flux de trésorerie (par filiale, séries horaires en devise locale lues dans
   marts.fct_flux_tresorerie_horaire)
   a. Deux modèles candidats sont mis en concurrence (approche champion / challenger) :
        - « naïf saisonnier » : pour chaque heure de la journée, moyenne des 7 derniers jours
          (référence minimale qu'un modèle doit battre) ;
        - « Holt-Winters » : lissage exponentiel avec saisonnalité journalière (24 h)
          MULTIPLICATIVE (le profil horaire est proportionnel au niveau d'activité ; une
          saisonnalité additive diverge quand le volume chute brutalement, comme dans PaySim).
   b. Backtest : chaque modèle est réentraîné sans les 3 derniers jours complets puis
      comparé au réalisé (WAPE sur les totaux journaliers). Le meilleur devient le
      « champion » de la filiale, pour chaque série (encaissements / décaissements).
   c. SIMULATION Monte-Carlo (simulation historique) : chaque trajectoire future est
      construite en tirant au hasard des journées réellement observées (entrées ET
      sorties du même jour, pour garder leur corrélation), remises à l'échelle du
      niveau prévu par le champion. On cumule à partir de la dernière position
      connue et on lit les quantiles P5 / P50 / P95 => « cône » de prévision et
      probabilité de passer sous le besoin de liquidité.

2) Taux de change (devises flottantes)
   - Mouvement brownien géométrique calibré sur la volatilité des 250 dernières
     cotations (un taux de change se prévoit mal mieux qu'une marche aléatoire :
     résultat classique de Meese & Rogoff, 1983) => on prévoit une FOURCHETTE,
     utile pour dimensionner la couverture, plutôt qu'un point.
"""
from __future__ import annotations

import logging
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .config import (
    GRAINE_ALEATOIRE,
    PREVISION_CHANGE_HORIZON_JOURS,
    PREVISION_HORIZON_JOURS,
    PREVISION_JOURS_BACKTEST,
    PREVISION_NB_SIMULATIONS,
)
from .db import moteur

log = logging.getLogger(__name__)
SAISON = 24                # saisonnalité journalière sur données horaires
JOURS_REFERENCE = 7        # fenêtre du modèle naïf et de la simulation historique
QUANTILES = {"p05": 0.05, "p50": 0.50, "p95": 0.95}


# --------------------------------------------------------------------- modèles
def prevoir_naif(y: np.ndarray, horizon_h: int) -> np.ndarray:
    """Moyenne, heure par heure, des JOURS_REFERENCE derniers jours (y commence à 0 h)."""
    profil = y[-JOURS_REFERENCE * SAISON:].reshape(-1, SAISON).mean(axis=0)
    return np.resize(profil, horizon_h)


def prevoir_holt_winters(y: np.ndarray, horizon_h: int) -> np.ndarray:
    # +1 : la saisonnalité multiplicative exige des valeurs strictement positives
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ajuste = ExponentialSmoothing(
            y + 1.0, trend=None, seasonal="mul", seasonal_periods=SAISON, initialization_method="estimated"
        ).fit()
    return np.clip(ajuste.forecast(horizon_h) - 1.0, 0, None)


MODELES = {"naif_saisonnier": prevoir_naif, "holt_winters": prevoir_holt_winters}


def wape(reel: np.ndarray, prevu: np.ndarray) -> float:
    return float(np.abs(reel - prevu).sum() / max(reel.sum(), 1e-9))


# ----------------------------------------------------------------------- flux
def charger_series_horaires(engine) -> pd.DataFrame:
    requete = """
        select horodatage, code_filiale, code_devise,
               sum(encaissements_devise) as encaissements,
               sum(decaissements_devise) as decaissements
        from marts.fct_flux_tresorerie_horaire
        group by horodatage, code_filiale, code_devise
    """
    df = pd.read_sql(requete, engine, parse_dates=["horodatage"])
    if df.empty:
        raise SystemExit("marts.fct_flux_tresorerie_horaire est vide : lancer dbt avant la prévision.")
    return df


def grille_jours_complets(flux: pd.DataFrame) -> pd.DatetimeIndex:
    """Index horaire de minuit du 1er jour à 23 h du dernier jour COMPLET (24 heures)."""
    premier = flux.horodatage.min().normalize()
    dernier = flux.horodatage.max()
    fin = dernier.normalize() + pd.Timedelta(hours=23)
    if dernier < fin:  # dernier jour incomplet (cas de PaySim : step 743 = 22 h)
        fin -= pd.Timedelta(days=1)
    return pd.date_range(premier, fin, freq="h")


def serie_complete(df: pd.DataFrame, colonne: str, index: pd.DatetimeIndex) -> np.ndarray:
    """Série horaire sans trou (heures sans transaction = 0)."""
    return df.set_index("horodatage")[colonne].astype(float).reindex(index, fill_value=0.0).to_numpy()


def par_jour(valeurs: np.ndarray) -> np.ndarray:
    return valeurs.reshape(-1, SAISON).sum(axis=1)


def backtester(y: np.ndarray, jours_test: int) -> tuple[pd.DataFrame, str]:
    """Évalue chaque modèle sur les derniers jours ; renvoie le détail et le champion."""
    h = jours_test * SAISON
    entrainement, reel = y[:-h], par_jour(y[-h:])
    lignes, scores = [], {}
    for nom, modele in MODELES.items():
        prevu = par_jour(modele(entrainement, h))
        scores[nom] = wape(reel, prevu)
        lignes.append(pd.DataFrame({"modele": nom, "jour_test": range(1, jours_test + 1), "reel": reel, "prevu": prevu}))
    return pd.concat(lignes, ignore_index=True), min(scores, key=scores.get)


def simuler_trajectoires(enc: np.ndarray, dec: np.ndarray, niveau_enc: np.ndarray, niveau_dec: np.ndarray,
                         nb_sim: int, rng: np.random.Generator) -> np.ndarray:
    """Simulation historique : (jours x simulations) de flux nets journaliers."""
    enc_j, dec_j = par_jour(enc)[-JOURS_REFERENCE:], par_jour(dec)[-JOURS_REFERENCE:]
    tirages = rng.integers(0, JOURS_REFERENCE, size=(len(niveau_enc), nb_sim))
    # mise à l'échelle : le jour tiré est ramené au niveau prévu par le champion
    echelle_enc = niveau_enc / max(enc_j.mean(), 1e-9)
    echelle_dec = niveau_dec / max(dec_j.mean(), 1e-9)
    return enc_j[tirages] * echelle_enc[:, None] - dec_j[tirages] * echelle_dec[:, None]


def prevoir_tresorerie(engine, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    flux = charger_series_horaires(engine)
    situation = pd.read_sql(
        """
        select p.code_filiale, p.code_devise, p.date_position, p.position_cloture_devise, p.taux_eur_jour,
               l.besoin_liquidite_30j_eur
        from marts.fct_position_tresorerie_quotidienne p
        join marts.mart_liquidite_placement l using (date_position, code_filiale)
        where p.date_position = (select max(date_position) from marts.fct_position_tresorerie_quotidienne)
        """,
        engine,
    ).set_index("code_filiale")
    index = grille_jours_complets(flux)
    date_arrete = situation.date_position.iloc[0]
    horizon_h = PREVISION_HORIZON_JOURS * SAISON
    dates_futures = pd.date_range(pd.Timestamp(date_arrete) + pd.Timedelta(days=1), periods=PREVISION_HORIZON_JOURS)
    debut_test = index[-PREVISION_JOURS_BACKTEST * SAISON].normalize()

    previsions, backtests = [], []
    for filiale, groupe in flux.groupby("code_filiale"):
        s = situation.loc[filiale]
        series = {nom: serie_complete(groupe, nom, index) for nom in ("encaissements", "decaissements")}

        niveaux, champions = {}, {}
        for nom, y in series.items():
            detail, champion = backtester(y, PREVISION_JOURS_BACKTEST)
            detail["date_jour"] = [debut_test + pd.Timedelta(days=j - 1) for j in detail.jour_test]
            detail.insert(0, "code_filiale", filiale)
            detail.insert(1, "serie", nom)
            detail["est_champion"] = detail.modele == champion
            backtests.append(detail.drop(columns="jour_test"))
            champions[nom] = champion
            niveaux[nom] = par_jour(MODELES[champion](y, horizon_h))  # réentraîné sur tout l'historique

        net = simuler_trajectoires(series["encaissements"], series["decaissements"],
                                   niveaux["encaissements"], niveaux["decaissements"],
                                   PREVISION_NB_SIMULATIONS, rng)
        position = s.position_cloture_devise + net.cumsum(axis=0)
        seuil_devise = s.besoin_liquidite_30j_eur * s.taux_eur_jour

        resultat = pd.DataFrame({"date_prevision": dates_futures.date, "code_filiale": filiale,
                                 "code_devise": s.code_devise})
        for nom, q in QUANTILES.items():
            resultat[f"flux_net_{nom}_devise"] = np.quantile(net, q, axis=1)
            resultat[f"position_{nom}_devise"] = np.quantile(position, q, axis=1)
        resultat["proba_sous_besoin_liquidite"] = (position < seuil_devise).mean(axis=1)
        resultat["modele_encaissements"] = champions["encaissements"]
        resultat["modele_decaissements"] = champions["decaissements"]
        previsions.append(resultat)
        log.info("  %-3s : champions %s / %s ; position P50 à J+%d = %s %s", filiale,
                 champions["encaissements"], champions["decaissements"], PREVISION_HORIZON_JOURS,
                 f"{resultat.position_p50_devise.iloc[-1]:,.0f}".replace(",", " "), s.code_devise)

    prev = pd.concat(previsions, ignore_index=True)
    prev["date_arrete"] = date_arrete
    prev["methode_simulation"] = f"Simulation historique ({JOURS_REFERENCE} derniers jours), {PREVISION_NB_SIMULATIONS} trajectoires"
    bt = pd.concat(backtests, ignore_index=True)
    bt["date_jour"] = pd.to_datetime(bt["date_jour"]).dt.date
    return prev, bt


# ------------------------------------------------------------------------ change
def prevoir_change(engine, rng: np.random.Generator) -> pd.DataFrame:
    date_arrete = pd.read_sql(
        "select max(date_position) as d from marts.fct_position_tresorerie_quotidienne", engine
    ).d.iloc[0]
    cours = pd.read_sql(
        """
        select code_devise, date_cours, taux_eur
        from marts.fct_taux_change
        where regime_change = 'flottant' and est_taux_publie and date_cours <= %(d)s
        order by code_devise, date_cours
        """,
        engine, params={"d": date_arrete}, parse_dates=["date_cours"],
    )
    horizon = PREVISION_CHANGE_HORIZON_JOURS
    nb_sim = max(PREVISION_NB_SIMULATIONS, 2000)
    sorties = []
    for devise, g in cours.groupby("code_devise"):
        derniere = g.date_cours.max()
        if (pd.Timestamp(date_arrete) - derniere).days > 7:
            log.warning("  %s : dernière cotation le %s => rupture de série, pas de prévision", devise, derniere.date())
            continue
        rendements = np.diff(np.log(g.taux_eur.to_numpy()))[-250:]
        vol_jour_calendaire = rendements.std(ddof=1) * np.sqrt(252 / 365)
        depart = g.taux_eur.iloc[-1]
        chocs = rng.normal(-0.5 * vol_jour_calendaire**2, vol_jour_calendaire, size=(horizon, nb_sim))
        trajectoires = depart * np.exp(np.cumsum(chocs, axis=0))
        dates = pd.date_range(pd.Timestamp(date_arrete) + pd.Timedelta(days=1), periods=horizon, freq="D")
        df = pd.DataFrame({"date_prevision": dates.date, "code_devise": devise})
        for nom, q in QUANTILES.items():
            df[f"taux_{nom}"] = np.quantile(trajectoires, q, axis=1)
        df["taux_depart"] = depart
        df["volatilite_annuelle_pct"] = 100 * rendements.std(ddof=1) * np.sqrt(252)
        sorties.append(df)
        log.info("  %s : 1 EUR = %.4f aujourd'hui ; fourchette 90 %% à %d j : [%.4f ; %.4f]",
                 devise, depart, horizon, df.taux_p05.iloc[-1], df.taux_p95.iloc[-1])
    resultat = pd.concat(sorties, ignore_index=True)
    resultat["date_arrete"] = date_arrete
    resultat["methode"] = f"Mouvement brownien géométrique, vol. 250 j, {nb_sim} trajectoires"
    return resultat


def lancer_previsions() -> None:
    engine = moteur()
    rng = np.random.default_rng(GRAINE_ALEATOIRE)
    horodatage_calcul = datetime.now()

    log.info("Prévision des flux de trésorerie par filiale...")
    prev, bt = prevoir_tresorerie(engine, rng)
    log.info("Prévision des taux de change...")
    chg = prevoir_change(engine, rng)

    for nom, df in (("prevision_tresorerie_quotidienne", prev), ("backtest_prevision", bt), ("prevision_change", chg)):
        df["date_calcul"] = horodatage_calcul
        df.to_sql(nom, engine, schema="ml", if_exists="replace", index=False)
        log.info("ml.%s : %d lignes écrites", nom, len(df))
