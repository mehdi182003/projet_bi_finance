"""Étape ANALYSE PRÉDICTIVE : prévision des flux de trésorerie et des taux de change.

1) Flux de trésorerie (par filiale, au pas QUOTIDIEN, 3 ans d'historique 2023-2025)
   a. Trois modèles candidats (approche champion / challenger) :
        - « naïf hebdomadaire » : moyenne du même jour de la semaine sur les 4 dernières semaines
          (référence minimale qu'un modèle doit battre) ;
        - « Holt-Winters » : lissage exponentiel, tendance amortie, saisonnalité hebdomadaire ;
        - « régression calendaire » : moindres carrés sur des variables de calendrier connues à l'avance
          (jour de la semaine, jour ouvré ou férié, 3 premiers jours ouvrés, 2 derniers jours ouvrés,
          mi-mois, MOIS DE L'ANNÉE, tendance), apprise sur tout l'historique (3 ans). L'effet « mois »
          capte la saisonnalité réelle des dépôts (hausse en décembre, baisse en janvier).
   b. Backtest sur 3 origines (fin septembre, octobre, novembre 2025), horizon d'un mois complet :
      le WAPE (erreur absolue pondérée) désigne le champion de chaque série.
   c. SIMULATION Monte-Carlo : les erreurs relatives du champion observées au backtest sont rééchantillonnées
      par blocs de 7 jours (mêmes jours pour encaissements et décaissements => corrélation conservée),
      auxquelles s'ajoute un choc MENSUEL sur le flux net, d'écart-type estimé sur les résidus mensuels
      du modèle (corrigés des degrés de liberté) : l'incertitude sur le niveau du mois n'est pas sous-estimée.
      On en déduit, pour janvier 2026 : le cône P5/P50/P95 de la position, la probabilité de passer sous
      le besoin de liquidité Bâle III, et la RÉSERVE REQUISE pour ne pas passer sous 100 % dans 99 % des cas.
   d. Valeur de la prévision : réserve actuelle (politique fixe) - réserve requise (prévision)
      = liquidité libérable, valorisée au taux directeur réel en vigueur.

2) Taux de change (devises flottantes)
   - Mouvement brownien géométrique calibré sur la volatilité des 250 dernières cotations (un taux de
     change se prévoit mal mieux qu'une marche aléatoire : Meese & Rogoff, 1983) => FOURCHETTE à 30 jours.
"""
from __future__ import annotations

import logging
import warnings
from datetime import datetime

import holidays
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .config import (
    GRAINE_ALEATOIRE,
    PREVISION_CHANGE_HORIZON_JOURS,
    PREVISION_NB_SIMULATIONS,
)
from .db import moteur

log = logging.getLogger(__name__)
QUANTILES = {"p05": 0.05, "p50": 0.50, "p95": 0.95}
ORIGINES_BACKTEST = ["2025-09-30", "2025-10-31", "2025-11-30"]
FENETRE_APPRENTISSAGE = 365
TAUX_FUITE_LCR = 0.10
CONFIANCE_RESERVE = 0.99
NB_SIM_FLUX = max(PREVISION_NB_SIMULATIONS, 1000)


# ------------------------------------------------------------------- calendrier
def variables_calendrier(dates: pd.DatetimeIndex, code_pays: str, debut_tendance: pd.Timestamp) -> np.ndarray:
    """Variables connues à l'avance : jours ouvrés/fériés, début/fin de mois, mi-mois, mois, jour, tendance."""
    feries = holidays.country_holidays(code_pays, years=range(dates.min().year, dates.max().year + 1))
    c = pd.DataFrame({"date": dates})
    c["ferie"] = c.date.dt.date.map(lambda d: d in feries).astype(float)
    c["ouvre"] = ((c.date.dt.weekday < 5) & (c.ferie == 0)).astype(float)
    mois = c.date.dt.to_period("M")
    c["rang"] = c.groupby(mois).ouvre.cumsum() * c.ouvre
    c["rang_fin"] = c[::-1].groupby(mois[::-1]).ouvre.cumsum()[::-1] * c.ouvre
    colonnes = [np.ones(len(c)), c.ouvre, c.ferie,
                ((c.rang >= 1) & (c.rang <= 3)).astype(float),
                ((c.rang_fin >= 1) & (c.rang_fin <= 2)).astype(float),
                (c.ouvre * c.date.dt.day.between(13, 15)).astype(float),
                (c.date - debut_tendance).dt.days.astype(float) / 365]
    colonnes += [(c.date.dt.weekday == j).astype(float) for j in range(1, 7)]
    colonnes += [(c.date.dt.month == m).astype(float) for m in range(2, 13)]
    return np.column_stack(colonnes)


# --------------------------------------------------------------------- modèles
def prevoir_naif(y: pd.Series, futur: pd.DatetimeIndex, code_pays: str) -> np.ndarray:
    recent = y.iloc[-28:]
    profil = recent.groupby(recent.index.weekday).mean()
    return profil.reindex(futur.weekday).to_numpy()


def prevoir_holt_winters(y: pd.Series, futur: pd.DatetimeIndex, code_pays: str) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ajuste = ExponentialSmoothing(
            y.iloc[-FENETRE_APPRENTISSAGE:].to_numpy() + 1.0, trend="add", damped_trend=True,
            seasonal="mul", seasonal_periods=7, initialization_method="estimated").fit()
    return np.clip(ajuste.forecast(len(futur)) - 1.0, 0, None)


def ajuster_regression(y: pd.Series, code_pays: str) -> tuple[np.ndarray, pd.Timestamp]:
    origine = y.index.min()
    coef, *_ = np.linalg.lstsq(variables_calendrier(y.index, code_pays, origine), y.to_numpy(), rcond=None)
    return coef, origine


def prevoir_regression(y: pd.Series, futur: pd.DatetimeIndex, code_pays: str) -> np.ndarray:
    coef, origine = ajuster_regression(y, code_pays)
    return np.clip(variables_calendrier(futur, code_pays, origine) @ coef, 0, None)


def ecart_type_mensuel(g: pd.DataFrame, code_pays: str) -> float:
    """Incertitude sur le flux net d'un mois : écart-type des résidus mensuels de la régression,
    corrigé des degrés de liberté (mois de l'année + tendance estimés sur le même historique)."""
    net_prevu = 0
    for serie, signe in (("encaissements", 1), ("decaissements", -1)):
        y = g[f"{serie}_devise"]
        coef, origine = ajuster_regression(y, code_pays)
        net_prevu = net_prevu + signe * (variables_calendrier(y.index, code_pays, origine) @ coef)
    residus = (g.encaissements_devise - g.decaissements_devise - net_prevu).groupby(g.index.to_period("M")).sum()
    n, p = len(residus), 13
    return float(residus.std(ddof=1) * np.sqrt(n / max(n - p, 1)))


MODELES = {"naif_hebdomadaire": prevoir_naif, "holt_winters": prevoir_holt_winters,
           "regression_calendaire": prevoir_regression}


def wape(reel: np.ndarray, prevu: np.ndarray) -> float:
    return float(np.abs(reel - prevu).sum() / max(reel.sum(), 1e-9))


def est_divergent(y: pd.Series, prevu: np.ndarray) -> bool:
    return not np.all(np.isfinite(prevu)) or prevu.max() > 3 * max(y.max(), 1.0)


def backtester(y: pd.Series, code_pays: str) -> tuple[pd.DataFrame, str, dict]:
    """Backtest multi-origines ; renvoie le détail, le champion et ses erreurs relatives quotidiennes."""
    lignes, erreurs, scores = [], {m: [] for m in MODELES}, {m: [] for m in MODELES}
    for origine in pd.to_datetime(ORIGINES_BACKTEST):
        fin = origine + pd.offsets.MonthEnd(1)
        apprentissage, test = y[y.index <= origine], y[(y.index > origine) & (y.index <= fin)]
        for nom, modele in MODELES.items():
            prevu = modele(apprentissage, test.index, code_pays)
            if est_divergent(apprentissage, prevu):
                prevu = np.full(len(test), np.nan)
                scores[nom].append(np.inf)
            else:
                scores[nom].append(wape(test.to_numpy(), prevu))
                erreurs[nom].append(np.divide(test.to_numpy(), prevu, out=np.ones(len(test)), where=prevu > 0) - 1)
            lignes.append(pd.DataFrame({"modele": nom, "origine": origine.date(), "date_jour": test.index.date,
                                        "reel": test.to_numpy(), "prevu": prevu}))
    moyenne = {m: float(np.mean(v)) for m, v in scores.items()}
    champion = min(moyenne, key=moyenne.get)
    return pd.concat(lignes, ignore_index=True), champion, np.concatenate(erreurs[champion])


# ----------------------------------------------------------------------- flux
def charger_donnees(engine) -> tuple[pd.DataFrame, pd.DataFrame]:
    pos = pd.read_sql(
        """select date_position, code_filiale, code_devise, encaissements_devise, decaissements_devise,
                  encours_depots_devise, position_cloture_devise, taux_eur_jour
           from marts.fct_position_tresorerie_quotidienne order by code_filiale, date_position""",
        engine, parse_dates=["date_position"])
    if pos.empty:
        raise SystemExit("marts.fct_position_tresorerie_quotidienne est vide : lancer dbt avant la prévision.")
    filiales = pd.read_sql(
        """select f.code_filiale, f.code_calendrier, f.taux_reserve_liquidite_pct,
                  (select r.taux_directeur_pct from referentiel.ref_taux_directeurs r
                    where r.code_devise = f.code_devise and r.date_effet <= %(d)s
                    order by r.date_effet desc limit 1) as taux_directeur_pct
           from referentiel.ref_filiales f""",
        engine, params={"d": pos.date_position.max().date()}).set_index("code_filiale")
    return pos, filiales


def blocs_erreurs(erreurs: np.ndarray, horizon: int, nb_sim: int, rng: np.random.Generator) -> np.ndarray:
    """Rééchantillonnage par blocs de 7 jours des erreurs relatives : matrice (horizon x nb_sim)."""
    bloc = 7
    nb_blocs = int(np.ceil(horizon / bloc))
    debuts = rng.integers(0, max(len(erreurs) - bloc, 1), size=(nb_blocs, nb_sim))
    idx = (debuts[:, None, :] + np.arange(bloc)[None, :, None]).reshape(nb_blocs * bloc, nb_sim)[:horizon]
    return np.clip(erreurs[np.minimum(idx, len(erreurs) - 1)], -0.95, 5)


def prevoir_tresorerie(engine, rng: np.random.Generator):
    pos, filiales = charger_donnees(engine)
    date_arrete = pos.date_position.max()
    futur = pd.date_range(date_arrete + pd.Timedelta(days=1), date_arrete + pd.offsets.MonthEnd(1), freq="D")
    previsions, backtests, reserves = [], [], []
    for filiale, g in pos.groupby("code_filiale"):
        f = filiales.loc[filiale]
        g = g.set_index("date_position")
        niveaux, champions, erreurs_relatives = {}, {}, {}
        for serie in ("encaissements", "decaissements"):
            y = g[f"{serie}_devise"]
            detail, champion, err = backtester(y, f.code_calendrier)
            detail.insert(0, "code_filiale", filiale)
            detail.insert(1, "serie", serie)
            detail["est_champion"] = detail.modele == champion
            backtests.append(detail)
            champions[serie], erreurs_relatives[serie] = champion, err
            niveaux[serie] = MODELES[champion](y, futur, f.code_calendrier)

        # Monte-Carlo : mêmes tirages d'erreurs (indices) pour les deux séries
        n = min(len(erreurs_relatives["encaissements"]), len(erreurs_relatives["decaissements"]))
        etat = rng.bit_generator.state
        e_enc = blocs_erreurs(erreurs_relatives["encaissements"][:n], len(futur), NB_SIM_FLUX, rng)
        rng.bit_generator.state = etat
        e_dec = blocs_erreurs(erreurs_relatives["decaissements"][:n], len(futur), NB_SIM_FLUX, rng)
        net = niveaux["encaissements"][:, None] * (1 + e_enc) - niveaux["decaissements"][:, None] * (1 + e_dec)
        sigma_mois = ecart_type_mensuel(g, f.code_calendrier)
        net = net + rng.normal(0, sigma_mois, NB_SIM_FLUX)[None, :] / len(futur)   # choc mensuel réparti
        depots_fin = g.encours_depots_devise.iloc[-1]
        depots = depots_fin + net.cumsum(axis=0)
        reserve_pct = f.taux_reserve_liquidite_pct / 100
        position = reserve_pct * depots_fin + net.cumsum(axis=0)          # rééquilibrage au 1er du mois
        besoin = TAUX_FUITE_LCR * depots

        resultat = pd.DataFrame({"date_prevision": futur.date, "code_filiale": filiale,
                                 "code_devise": g.code_devise.iloc[-1]})
        for nom, q in QUANTILES.items():
            resultat[f"flux_net_{nom}_devise"] = np.quantile(net, q, axis=1)
            resultat[f"position_{nom}_devise"] = np.quantile(position, q, axis=1)
            resultat[f"depots_{nom}_devise"] = np.quantile(depots, q, axis=1)
        resultat["proba_sous_besoin_liquidite"] = (position < besoin).mean(axis=1)
        resultat["modele_encaissements"] = champions["encaissements"]
        resultat["modele_decaissements"] = champions["decaissements"]
        previsions.append(resultat)

        # Réserve requise : plus petite réserve (en % des dépôts) qui garde la position au-dessus du
        # besoin Bâle III tout le mois dans 99 % des trajectoires.
        manque = ((besoin - net.cumsum(axis=0)) / depots_fin).max(axis=0)     # réserve nécessaire par trajectoire
        reserve_requise = float(np.quantile(manque, CONFIANCE_RESERVE))
        liberable = (reserve_pct - reserve_requise) * depots_fin
        taux = float(f.taux_directeur_pct)
        reserves.append({
            "code_filiale": filiale, "code_devise": g.code_devise.iloc[-1], "date_arrete": date_arrete.date(),
            "encours_depots_devise": depots_fin, "taux_reserve_actuel_pct": 100 * reserve_pct,
            "reserve_requise_p99_pct": 100 * reserve_requise,
            "liquidite_liberable_devise": liberable,
            "liquidite_liberable_eur": liberable / g.taux_eur_jour.iloc[-1],
            "taux_directeur_pct": taux,
            "gain_annuel_eur": liberable / g.taux_eur_jour.iloc[-1] * taux / 100,
            "proba_sous_100_politique_actuelle": float((position < besoin).any(axis=0).mean()),
        })
        log.info("  %-3s : champions %s / %s ; réserve requise P99 %.1f %% (actuelle %.0f %%) ; libérable %s EUR",
                 filiale, champions["encaissements"], champions["decaissements"], 100 * reserve_requise,
                 100 * reserve_pct, f"{liberable / g.taux_eur_jour.iloc[-1]:,.0f}".replace(",", " "))

    prev = pd.concat(previsions, ignore_index=True)
    prev["date_arrete"] = date_arrete.date()
    prev["methode_simulation"] = (f"Erreurs du champion rééchantillonnées par blocs de 7 jours, "
                                  f"{NB_SIM_FLUX} trajectoires")
    bt = pd.concat(backtests, ignore_index=True)
    return prev, bt, pd.DataFrame(reserves)


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
    prev, bt, reserves = prevoir_tresorerie(engine, rng)
    log.info("Prévision des taux de change...")
    chg = prevoir_change(engine, rng)

    for nom, df in (("prevision_tresorerie_quotidienne", prev), ("backtest_prevision", bt),
                    ("reserve_optimale", reserves), ("prevision_change", chg)):
        df["date_calcul"] = horodatage_calcul
        df.to_sql(nom, engine, schema="ml", if_exists="replace", index=False)
        log.info("ml.%s : %d lignes écrites", nom, len(df))
