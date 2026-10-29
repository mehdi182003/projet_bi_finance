"""Contrôle a posteriori de la prévision sur des données RÉELLES postérieures à la date d'arrêté.

La prévision s'arrête au 31/12/2025 et projette janvier 2026. Or les banques centrales ont depuis
publié les encours de dépôts de janvier 2026 : on vérifie si l'encours réel (x part de marché) tombe
dans la fourchette P5-P95 prévue pour le 31/01/2026. C'est un test hors échantillon sur du réel.
Nécessite Internet ; en cas d'échec, l'étape est ignorée sans bloquer le pipeline.
"""
from __future__ import annotations

import logging

import pandas as pd

from . import sources_reelles as sr
from .config import DOSSIER_DBT
from .db import moteur

log = logging.getLogger(__name__)
DATE_CONTROLE = pd.Timestamp("2026-01-31")


def controler() -> pd.DataFrame | None:
    engine = moteur()
    prev = pd.read_sql("select code_filiale, date_prevision, depots_p05_devise, depots_p50_devise, depots_p95_devise "
                       "from ml.prevision_tresorerie_quotidienne", engine, parse_dates=["date_prevision"])
    prev = prev[prev.date_prevision == DATE_CONTROLE].set_index("code_filiale")
    parts = pd.read_csv(DOSSIER_DBT / "seeds" / "ref_filiales.csv").set_index("code_filiale").part_de_marche_depots_pct
    ancien_debut, ancien_fin = sr.DEBUT, sr.FIN
    sr.DEBUT, sr.FIN = "2025-12-01", "2026-02-28"
    lignes = []
    try:
        for filiale, fonction in sr.SOURCES_DEPOTS.items():
            if filiale == "CM":                       # bulletin BEAC : pas de point mensuel janvier 2026 en API
                continue
            try:
                d = fonction()
            except Exception as exc:                  # source indisponible : on passe
                log.warning("  %s : source indisponible (%s)", filiale, exc)
                continue
            s = d.set_index("date_ancrage").encours.sort_index() * parts[filiale] / 100
            if DATE_CONTROLE not in s.index:          # séries hebdo : interpolation au 31/01
                s.loc[DATE_CONTROLE] = float("nan")
                s = s.sort_index().interpolate(method="time")
            if pd.isna(s.get(DATE_CONTROLE)) or filiale not in prev.index:
                continue
            p = prev.loc[filiale]
            reel = float(s.loc[DATE_CONTROLE])
            lignes.append({"code_filiale": filiale, "date_controle": DATE_CONTROLE.date(),
                           "depots_reels_devise": reel, "depots_p05_devise": p.depots_p05_devise,
                           "depots_p50_devise": p.depots_p50_devise, "depots_p95_devise": p.depots_p95_devise,
                           "erreur_p50_pct": 100 * (p.depots_p50_devise - reel) / reel,
                           "dans_intervalle_90": bool(p.depots_p05_devise <= reel <= p.depots_p95_devise),
                           "source": d.source.iloc[-1]})
    finally:
        sr.DEBUT, sr.FIN = ancien_debut, ancien_fin
    if not lignes:
        log.warning("Contrôle a posteriori impossible (pas d'accès aux sources) : étape ignorée.")
        return None
    res = pd.DataFrame(lignes)
    res.to_sql("controle_depots_reels", engine, schema="ml", if_exists="replace", index=False)
    for r in res.itertuples():
        log.info("  %-3s : réel %s | prévu P50 %s (erreur %+.2f %%) | dans [P5;P95] : %s", r.code_filiale,
                 f"{r.depots_reels_devise / 1e6:,.0f} M", f"{r.depots_p50_devise / 1e6:,.0f} M",
                 r.erreur_p50_pct, "oui" if r.dans_intervalle_90 else "NON")
    log.info("Couverture de l'intervalle à 90 %% : %d / %d filiales", res.dans_intervalle_90.sum(), len(res))
    return res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    controler()
