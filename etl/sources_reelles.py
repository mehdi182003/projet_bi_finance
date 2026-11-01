"""Étape EXTRACT (3/3) : séries RÉELLES publiées par les banques centrales et offices statistiques.

Ces séries sont la colonne vertébrale des 3 ans de flux de ZF Banque (2023-2025) :
  - encours de dépôts à vue par pays (mensuel ; hebdomadaire pour les États-Unis) ;
  - taux directeurs quotidiens par devise.

Chaque série est téléchargée depuis une API officielle puis mise en cache dans data/sources/
(fichiers versionnés), pour que le pipeline fonctionne ensuite sans Internet.
`python -m etl.sources_reelles` rafraîchit le cache.

Sources (toutes publiques et gratuites) :
  BCE       - BSI : dépôts à vue des ménages + entreprises (FR, BE, FI) ; taux de la facilité de dépôt
  Fed/FRED  - DPSACBW027NBOG : dépôts des banques commerciales américaines (hebdo, non CVS) ; DFEDTARU
  Banque du Canada - V37258 : M1+ brut non CVS ; V39079 : taux directeur
  SCB (Suède) - M1 ; Riksbank - taux directeur
  Danmarks Nationalbank (Statbank) - DNRUIPI : dépôts transférables ; DNRENTD : taux du compte courant
  FMI (MFS) - dépôts transférables inclus dans la masse monétaire (Norvège, Côte d'Ivoire)
  BEAC - bulletins mensuels : monnaie scripturale des banques commerciales (Cameroun)
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from .config import DOSSIER_DBT, DOSSIER_SOURCES

log = logging.getLogger(__name__)
DEBUT, FIN = "2022-12-01", "2025-12-31"   # 2022-12 : point d'ancrage initial au 31/12/2022
FICHIER_DEPOTS = DOSSIER_SOURCES / "depots_reels_2023_2025.csv"
FICHIER_TAUX = DOSSIER_SOURCES / "taux_directeurs_reels.csv"
FICHIER_BEAC = DOSSIER_SOURCES / "beac_cameroun_monnaie_scripturale.csv"
SEED_TAUX = DOSSIER_DBT / "seeds" / "ref_taux_directeurs.csv"
TIMEOUT = 120


def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def _fin_de_mois(periode: pd.Series) -> pd.Series:
    return pd.PeriodIndex(periode, freq="M").to_timestamp(how="end").normalize()


# ----------------------------------------------------------------- dépôts
def depots_bce(pays: str) -> pd.DataFrame:
    morceaux = []
    for secteur in ("2250", "2240"):   # ménages, sociétés non financières
        url = (f"https://data-api.ecb.europa.eu/service/data/BSI/M.{pays}.N.A.L21.A.1.U2.{secteur}.Z01.E"
               f"?format=csvdata&startPeriod={DEBUT[:7]}&endPeriod={FIN[:7]}")
        d = pd.read_csv(io.StringIO(_get(url).text))[["TIME_PERIOD", "OBS_VALUE"]]
        morceaux.append(d.set_index("TIME_PERIOD").OBS_VALUE)
    s = sum(morceaux) * 1e6   # millions EUR -> EUR
    return pd.DataFrame({"date_ancrage": _fin_de_mois(s.index.to_series()).values, "encours": s.values,
                         "source": "BCE BSI - dépôts à vue ménages + SNF (L21, 2250+2240)"})


def depots_fed() -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DPSACBW027NBOG&cosd={DEBUT}&coed={FIN}"
    d = pd.read_csv(io.StringIO(_get(url).text))
    d.columns = ["date", "valeur"]
    return pd.DataFrame({"date_ancrage": pd.to_datetime(d.date), "encours": d.valeur.astype(float) * 1e9,
                         "source": "Fed H.8 via FRED - DPSACBW027NBOG (hebdo, non CVS)"})


def depots_banque_canada() -> pd.DataFrame:
    url = f"https://www.bankofcanada.ca/valet/observations/V37258/json?start_date={DEBUT}&end_date={FIN}"
    obs = _get(url).json()["observations"]
    d = pd.DataFrame({"d": [o["d"] for o in obs], "v": [float(o["V37258"]["v"]) for o in obs]})
    return pd.DataFrame({"date_ancrage": _fin_de_mois(d.d.str[:7]).values, "encours": d.v.values * 1e6,
                         "source": "Banque du Canada - V37258 M1+ brut non CVS"})


def depots_scb_suede() -> pd.DataFrame:
    url = "https://api.scb.se/OV0104/v1/doris/en/ssd/FM/FM5001/FM5001A/FM5001penningmangd"
    requete = {"query": [
        {"code": "Penningm", "selection": {"filter": "item", "values": ["5LLM1.1E.NEP.V.A"]}},
        {"code": "ContentsCode", "selection": {"filter": "item", "values": ["000007WQ"]}},
    ], "response": {"format": "json"}}
    r = requests.post(url, json=requete, timeout=TIMEOUT)
    r.raise_for_status()
    lignes = [(x["key"][-1], float(x["values"][0])) for x in r.json()["data"] if x["values"][0] not in ("..", "")]
    d = pd.DataFrame(lignes, columns=["periode", "v"])
    d = d[(d.periode >= DEBUT[:4] + "M" + DEBUT[5:7]) & (d.periode <= FIN[:4] + "M12")]
    return pd.DataFrame({"date_ancrage": _fin_de_mois(d.periode.str.replace("M", "-")).values,
                         "encours": d.v.values * 1e6, "source": "SCB (Suède) - M1, encours"})


def depots_statbank_danemark() -> pd.DataFrame:
    requete = {"table": "DNRUIPI", "format": "BULK", "lang": "en", "variables": [
        {"code": "INSTRNAT", "values": ["PL10"]}, {"code": "DATA", "values": ["GNSB"]},
        {"code": "INDSEK", "values": ["1100", "1400"]}, {"code": "VALUTA", "values": ["Z01"]},
        {"code": "LØBETID1", "values": ["ALLE"]}, {"code": "Tid", "values": ["*"]}]}
    r = requests.post("https://api.statbank.dk/v1/data", json=requete, timeout=TIMEOUT)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), sep=";")
    d["periode"] = d["TID"].str.replace("M", "-")
    d = d[(d.periode >= DEBUT[:7]) & (d.periode <= FIN[:7])]
    s = d.groupby("periode")["INDHOLD"].apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
    return pd.DataFrame({"date_ancrage": _fin_de_mois(s.index.to_series()).values, "encours": s.values * 1e6,
                         "source": "Danmarks Nationalbank - DNRUIPI dépôts transférables SNF + ménages"})


def depots_fmi(pays_iso3: str) -> pd.DataFrame:
    url = (f"https://api.imf.org/external/sdmx/2.1/data/IMF.STA,MFS_ODC,10.0.0/{pays_iso3}.ODCORP_L_F22_IBM_ODCS..M"
           f"?startPeriod={DEBUT[:7]}")
    d = pd.read_csv(io.StringIO(_get(url, headers={"Accept": "application/vnd.sdmx.data+csv;version=1.0.0"}).text),
                    dtype=str)
    d = d[d.TIME_PERIOD.str.replace("-M", "-") <= FIN[:7]]
    return pd.DataFrame({"date_ancrage": _fin_de_mois(d.TIME_PERIOD.str.replace("-M", "-")).values,
                         "encours": d.OBS_VALUE.astype(float).values,
                         "source": "FMI MFS - dépôts transférables inclus dans la masse monétaire (F22)"})


def depots_beac_cameroun() -> pd.DataFrame:
    """Monnaie scripturale des banques commerciales (BCM), en millions de XAF, lue dans les
    bulletins mensuels de la BEAC. Les mois absents des bulletins sont interpolés (drapeau)."""
    if not FICHIER_BEAC.exists():
        raise SystemExit(f"{FICHIER_BEAC} manquant (extrait des bulletins BEAC, voir docs/07).")
    d = pd.read_csv(FICHIER_BEAC, parse_dates=["date_ancrage"])
    return pd.DataFrame({"date_ancrage": d.date_ancrage, "encours": d.monnaie_scripturale_bcm_mxaf * 1e6,
                         "source": "BEAC - bulletin " + d.bulletin_source})


SOURCES_DEPOTS = {   # code_filiale -> fonction
    "FR": lambda: depots_bce("FR"), "BNL": lambda: depots_bce("BE"), "FI": lambda: depots_bce("FI"),
    "US": depots_fed, "CA": depots_banque_canada, "SE": depots_scb_suede, "DK": depots_statbank_danemark,
    "NO": lambda: depots_fmi("NOR"), "CI": lambda: depots_fmi("CIV"), "CM": depots_beac_cameroun,
}


def collecter_depots() -> pd.DataFrame:
    morceaux = []
    for filiale, fonction in SOURCES_DEPOTS.items():
        d = fonction()
        d = d[(d.date_ancrage >= pd.Timestamp(DEBUT)) & (d.date_ancrage <= pd.Timestamp(FIN))].copy()
        d.insert(0, "code_filiale", filiale)
        # Mois manquants (ex. bulletins BEAC) : interpolation linéaire, signalée
        if filiale != "US":
            grille = pd.date_range(pd.Timestamp(DEBUT) + pd.offsets.MonthEnd(0), FIN, freq="ME")
            d = d.set_index("date_ancrage").reindex(grille)
            d["est_interpole"] = d.encours.isna()
            d["encours"] = d.encours.interpolate(limit_direction="both")
            d["code_filiale"] = filiale
            d["source"] = d.source.ffill().bfill()
            d = d.rename_axis("date_ancrage").reset_index()
        else:
            d["est_interpole"] = False
        log.info("  %-3s : %3d points (%d interpolés) du %s au %s - %s", filiale, len(d), d.est_interpole.sum(),
                 d.date_ancrage.min().date(), d.date_ancrage.max().date(), d.source.iloc[-1][:60])
        morceaux.append(d[["code_filiale", "date_ancrage", "encours", "est_interpole", "source"]])
    return pd.concat(morceaux, ignore_index=True)


# ---------------------------------------------------------------- taux directeurs
def _points_de_changement(d: pd.DataFrame, devise: str, banque: str, libelle: str, source: str) -> pd.DataFrame:
    d = d.dropna().sort_values("date")
    d = d[d.taux.ne(d.taux.shift())]
    return pd.DataFrame({"code_devise": devise, "banque_centrale": banque, "libelle_taux": libelle,
                         "date_effet": d.date.dt.date, "taux_directeur_pct": d.taux.round(4),
                         "a_verifier": False, "source": source})


def collecter_taux() -> pd.DataFrame:
    debut_taux = "2022-01-01"
    t = []
    d = pd.read_csv(io.StringIO(_get("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
                                     f"?format=csvdata&startPeriod={debut_taux}").text))
    t.append(_points_de_changement(pd.DataFrame({"date": pd.to_datetime(d.TIME_PERIOD), "taux": d.OBS_VALUE}),
                                   "EUR", "BCE", "Taux de la facilité de dépôt", "API BCE FM.D.U2.EUR.4F.KR.DFR.LEV"))
    d = pd.read_csv(io.StringIO(_get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd={debut_taux}").text))
    d.columns = ["date", "taux"]
    t.append(_points_de_changement(pd.DataFrame({"date": pd.to_datetime(d.date), "taux": pd.to_numeric(d.taux, errors="coerce")}),
                                   "USD", "Federal Reserve", "Fed Funds (borne haute)", "FRED DFEDTARU"))
    obs = _get(f"https://www.bankofcanada.ca/valet/observations/V39079/json?start_date={debut_taux}").json()["observations"]
    t.append(_points_de_changement(pd.DataFrame({"date": pd.to_datetime([o["d"] for o in obs]),
                                                 "taux": [float(o["V39079"]["v"]) for o in obs]}),
                                   "CAD", "Banque du Canada", "Taux directeur", "Banque du Canada Valet V39079"))
    obs = _get(f"https://api.riksbank.se/swea/v1/Observations/SECBREPOEFF/{debut_taux}").json()
    t.append(_points_de_changement(pd.DataFrame({"date": pd.to_datetime([o["date"] for o in obs]),
                                                 "taux": [float(o["value"]) for o in obs]}),
                                   "SEK", "Riksbank", "Taux directeur", "API Riksbank SECBREPOEFF"))
    d = pd.read_csv(io.StringIO(_get("https://data.norges-bank.no/api/data/IR/B.KPRA.SD.R"
                                     f"?format=csv&startPeriod={debut_taux}&locale=en").text), sep=";")
    col_date = [c for c in d.columns if "TIME_PERIOD" in c][0]
    col_val = [c for c in d.columns if "OBS_VALUE" in c][0]
    t.append(_points_de_changement(pd.DataFrame({"date": pd.to_datetime(d[col_date]), "taux": d[col_val].astype(float)}),
                                   "NOK", "Norges Bank", "Taux directeur", "API Norges Bank IR/B.KPRA.SD.R"))
    requete = {"table": "DNRENTD", "format": "BULK", "lang": "en", "variables": [
        {"code": "INSTRUMENT", "values": ["OFONAA"]}, {"code": "LAND", "values": ["DK"]},
        {"code": "OPGOER", "values": ["E"]}, {"code": "Tid", "values": ["*"]}]}
    r = requests.post("https://api.statbank.dk/v1/data", json=requete, timeout=TIMEOUT)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text), sep=";")
    d["date"] = pd.to_datetime(d.TID.str.replace("M", "-").str.replace("D", "-"))
    d = d[d.date >= debut_taux]
    t.append(_points_de_changement(pd.DataFrame({"date": d.date, "taux": pd.to_numeric(d.INDHOLD, errors="coerce")}),
                                   "DKK", "Danmarks Nationalbank", "Taux du compte courant", "Statbank DNRENTD"))
    # Zone CFA : pas d'API publique => saisie manuelle depuis les communiqués (à vérifier)
    manuels = pd.read_csv(DOSSIER_SOURCES / "taux_directeurs_cfa_manuels.csv", dtype={"a_verifier": bool})
    taux = pd.concat([*t, manuels], ignore_index=True)
    for devise, g in taux.groupby("code_devise"):
        log.info("  %s : %d changements de taux, dernier %s %% au %s", devise, len(g),
                 g.sort_values("date_effet").taux_directeur_pct.iloc[-1], g.date_effet.max())
    return taux


def rafraichir() -> None:
    DOSSIER_SOURCES.mkdir(parents=True, exist_ok=True)
    log.info("Dépôts réels par pays :")
    collecter_depots().to_csv(FICHIER_DEPOTS, index=False)
    log.info("Taux directeurs réels :")
    taux = collecter_taux()
    taux.to_csv(FICHIER_TAUX, index=False)
    # Le référentiel dbt des taux directeurs est produit à partir des sources officielles
    taux.sort_values(["code_devise", "date_effet"]).to_csv(SEED_TAUX, index=False)
    log.info("Référentiel dbt mis à jour : %s", SEED_TAUX)


def assurer_cache() -> None:
    """Télécharge les séries uniquement si le cache data/sources/ est absent."""
    if FICHIER_DEPOTS.exists() and FICHIER_TAUX.exists():
        log.info("Séries réelles déjà en cache dans %s", DOSSIER_SOURCES)
        return
    rafraichir()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rafraichir()
