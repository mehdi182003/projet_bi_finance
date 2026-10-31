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

Sorties :
  - la « vérité » (opérations réelles de ZF Banque), transmise à etl/systemes_sources.py qui écrit les
    EXPORTS BRUTS de chaque système bancaire, avec leurs formats et leurs défauts (data/sources_internes/) ;
  - data/sources/ancrages_zf.csv : encours de référence (dépôts réels x part de marché).
"""
from __future__ import annotations

import logging
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

from .config import DOSSIER_DATA, DOSSIER_DBT, DOSSIER_SOURCES, FICHIER_WEBSTAT, GRAINE_ALEATOIRE
from .extraction_bce import lire_webstat
from .extraction_paysim import trouver_fichier_paysim
from .sources_reelles import FICHIER_DEPOTS

log = logging.getLogger(__name__)

DEBUT, FIN = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31")
DATE_INITIALE = pd.Timestamp("2022-12-31")
POIDS = 100                     # opérations représentées par une ligne (--taille-lot ; 100 = jeu versionné)
TAUX_ROTATION = 0.008           # décaissements bruts d'un jour ouvré / encours de dépôts (PaySim réel : 0,78 %)
PART_MIN_ENTREES = 0.30         # les encaissements d'une période valent au moins 30 % des décaissements
VALEUR_UNITE_PAYSIM_EUR = 0.01  # 1 unité PaySim = 0,01 EUR (transaction médiane ~750 EUR)
BRUIT_JOUR = 0.15               # écart-type log du bruit quotidien
STEPS_STABLES = (121, 408)      # fenêtre d'activité stable de PaySim (docs/06)
FICHIER_ANCRAGES = DOSSIER_SOURCES / "ancrages_zf.csv"

TYPES_SORTIE = ["TRANSFER", "DEBIT", "PAYMENT", "CASH_OUT"]   # ni virement ni prélèvement le week-end

# --- Réalisme économique (hypothèses documentées, paramétrables) -----------------------------------
# PaySim fournit la FORME des montants (dispersion, fraude, heures) mais pas leur niveau : ses tickets
# (retrait médian ~1 500 EUR, mêmes montants dans tous les pays) ne sont pas ceux d'une banque de détail.
# On garde la forme de chaque type et on recale sa moyenne sur un ticket réaliste (EUR, France = 1,0),
# puis on le module par un facteur de niveau de vie. Les totaux journaliers, eux, restent ancrés sur les
# dépôts réels : changer la taille des tickets change le NOMBRE d'opérations, pas les montants totaux.
TICKET_MOYEN_EUR = {"PAYMENT": 45, "CASH_OUT": 110, "DEBIT": 180, "TRANSFER": 2_500,
                    "CASH_IN": 450, "VIREMENT_RECU": 1_800}
FACTEUR_TICKET = {"FR": 1.0, "BNL": 1.1, "FI": 1.05, "SE": 1.1, "DK": 1.3, "NO": 1.5,    # niveau de vie relatif,
                  "CI": 0.35, "CM": 0.30, "CA": 1.0, "US": 1.4}                           # ordre de grandeur (a_verifier)
EPARGNE_MOYENNE_PAR_CLIENT_EUR = 20_000   # dépôt à vue moyen par client (France = 1,0) : fixe le nombre de clients
PROFILS_FLUX = {   # part de la VALEUR décaissée par type, et part des encaissements en virements (sinon espèces)
    "europe": {"sorties": {"TRANSFER": .50, "DEBIT": .25, "PAYMENT": .17, "CASH_OUT": .08}, "virements": .90},
    "afrique": {"sorties": {"TRANSFER": .40, "DEBIT": .05, "PAYMENT": .10, "CASH_OUT": .45}, "virements": .55},
    "amerique": {"sorties": {"TRANSFER": .42, "DEBIT": .28, "PAYMENT": .22, "CASH_OUT": .08}, "virements": .93},
}
BRUIT_COMPOSITION = 0.15        # variabilité quotidienne de la composition des flux
PART_FRAUDE_CONSERVEE = 0.10    # fraudes PaySim gardées (ramène la fraude à ~0,03 % de la valeur décaissée)
HEURES_BATCH = (5, 9)           # prélèvements et virements reçus sont traités en lot tôt le matin


def profil_flux(code_filiale: str) -> dict:
    zone = "afrique" if code_filiale in ("CI", "CM") else "amerique" if code_filiale in ("CA", "US") else "europe"
    return PROFILS_FLUX[zone]


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
    return pd.concat(morceaux)[["date", "est_ouvre", "rang_ouvre", "encaissements", "decaissements"]]


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


def tirer(pool: pd.DataFrame, cibles_eur: np.ndarray, jours: np.ndarray, rng, ticket_eur: float) -> pd.DataFrame:
    """Tire des opérations (forme PaySim, moyenne recalée sur `ticket_eur`), ajustées au total cible du jour."""
    n = np.maximum(np.rint(cibles_eur / (POIDS * ticket_eur)).astype(int), (cibles_eur > 0).astype(int))
    idx = rng.integers(0, len(pool), n.sum())
    t = pool.iloc[idx].reset_index(drop=True)
    t["jour"] = np.repeat(jours, n)
    t["montant_eur"] = t.forme.values * ticket_eur
    somme = np.bincount(np.repeat(np.arange(len(jours)), n), weights=t.montant_eur.values * POIDS,
                        minlength=len(jours))
    facteur = np.divide(cibles_eur, somme, out=np.zeros_like(cibles_eur), where=somme > 0)
    t["montant_eur"] = t.montant_eur.values * np.repeat(facteur, n)
    return t


def formes_par_type(texture: pd.DataFrame) -> dict:
    """Une forme de montant (moyenne = 1) par type d'opération, tirée de PaySim ; VIREMENT_RECU prend celle de CASH_IN.

    PaySim surreprésente la fraude (~0,3 % des décaissements en valeur une fois recalé, contre ~0,03 % pour
    les paiements par carte selon la BCE) : on ne conserve qu'une part PART_FRAUDE_CONSERVEE des fraudes.
    """
    garder = np.random.default_rng(GRAINE_ALEATOIRE).random(len(texture)) < PART_FRAUDE_CONSERVEE
    texture = texture[(texture.isFraud == 0) | garder]
    formes = {}
    for type_, g in texture.groupby("type"):
        formes[type_] = (g.assign(forme=g.montant_eur / g.montant_eur.mean())[["forme", "heure", "isFraud"]]
                         .reset_index(drop=True))
    formes["VIREMENT_RECU"] = formes["CASH_IN"]
    return formes


def repartition_quotidienne(flux: pd.DataFrame, profil: dict, rng: np.random.Generator) -> dict:
    """Ventile les décaissements et encaissements de chaque jour par type, selon le profil du pays."""
    ouvre = flux.est_ouvre.values
    part = np.tile(np.array([profil["sorties"][t] for t in TYPES_SORTIE]), (len(flux), 1))
    part[~ouvre, :2] = 0                                              # ni virement ni prélèvement le week-end
    debut_mois = ouvre & (flux.rang_ouvre.values <= 3)
    part[:, 1] *= np.where(debut_mois, 2.5, 0.6)                      # loyers, factures : début de mois
    part = part * rng.lognormal(0, BRUIT_COMPOSITION, part.shape)
    part = part / part.sum(axis=1, keepdims=True)
    virement = np.clip(profil["virements"] * np.where(ouvre, 1.0, 0.5)
                       * rng.lognormal(0, BRUIT_COMPOSITION / 3, len(flux)), 0, 0.99)
    cibles = {t: flux.decaissements.values * part[:, k] for k, t in enumerate(TYPES_SORTIE)}
    cibles["VIREMENT_RECU"] = flux.encaissements.values * virement
    cibles["CASH_IN"] = flux.encaissements.values * (1 - virement)
    return cibles


def transactions_filiale(f: pd.Series, flux: pd.DataFrame, texture: pd.DataFrame, taux: pd.Series,
                         rng: np.random.Generator, encours_moyen_eur: float) -> pd.DataFrame:
    flux = flux.reset_index(drop=True)
    jours = flux.date.values
    taux_jour = taux.reindex(flux.date).ffill().bfill().values         # devise locale pour 1 EUR
    formes = formes_par_type(texture)
    facteur = FACTEUR_TICKET[f.code_filiale]
    cibles = repartition_quotidienne(flux, profil_flux(f.code_filiale), rng)
    morceaux = []
    for type_, cible in cibles.items():
        m = cible > 0
        t = tirer(formes[type_], cible[m] / taux_jour[m], jours[m], rng, TICKET_MOYEN_EUR[type_] * facteur)
        t["type"] = type_
        if type_ in ("DEBIT", "VIREMENT_RECU"):                        # traitements en lot, tôt le matin
            t["heure"] = rng.integers(*HEURES_BATCH, len(t))
        morceaux.append(t)
    t = pd.concat(morceaux, ignore_index=True)
    t["taux"] = pd.Series(taux_jour, index=jours).reindex(t.jour).values
    nb_clients = max(int(encours_moyen_eur / (EPARGNE_MOYENNE_PAR_CLIENT_EUR * facteur)), 1_000)
    rang = 1 + np.floor(nb_clients * rng.random(len(t)) ** 2.5).astype(int)   # quelques clients très actifs ;
                                                                               # 0000000 = valeur nulle des exports
    decimales = 0 if f.code_devise in ("XOF", "XAF") else 2                # le franc CFA n'a pas de centimes
    v = pd.DataFrame({
        "horodatage": pd.to_datetime(t.jour) + pd.to_timedelta(t.heure, unit="h")
                      + pd.to_timedelta(rng.integers(0, 3600, len(t)), unit="s"),
        "code_filiale": f.code_filiale,
        "code_type": t.type.values,
        "montant_devise": np.round(t.montant_eur.values * t.taux.values, decimales),
        "poids": POIDS,
        "id_client": [f"{f.code_filiale}-{r:07d}" for r in rang],
        "est_fraude": t.isFraud.values.astype(int),
    })
    v = v[v.montant_devise > 0].sort_values("horodatage").reset_index(drop=True)
    jour = v.horodatage.dt.strftime("%Y%m%d")
    v.insert(0, "ref_operation", f.code_filiale + jour + "-" + (v.groupby(jour).cumcount() + 1).astype(str).str.zfill(6))
    return v


def encours_moyen_eur(anc: pd.DataFrame, taux: pd.Series) -> float:
    cours = taux.reindex(pd.date_range(DATE_INITIALE, FIN)).ffill().bfill().reindex(anc.date_ancrage).values
    return float((anc.encours_zf_devise.values / cours).mean())


def dossier_par_defaut(taille_lot: int) -> Path:
    from .systemes_sources import DOSSIER_SOURCES_INTERNES
    return DOSSIER_SOURCES_INTERNES if taille_lot == 100 else DOSSIER_DATA / "generees" / f"lot_{taille_lot}"


def generer(fichier_paysim: Path | None = None, taille_lot: int = 100, dossier: Path | None = None) -> Path:
    """Construit la vérité 2023-2025, filiale par filiale, et écrit aussitôt ses exports bruts.

    Traiter une filiale à la fois borne la mémoire (utile pour les petites tailles de lot, donc les
    gros volumes) ; l'ordre des tirages aléatoires est inchangé => résultat identique à graine égale.
    """
    from .systemes_sources import GRAINE_DEFAUTS, ecrire_soldes, exporter_filiale, soldes_filiale
    global POIDS
    POIDS = taille_lot
    dossier = dossier or dossier_par_defaut(taille_lot)
    rng = np.random.default_rng(GRAINE_ALEATOIRE)
    rng_exports = np.random.default_rng(GRAINE_DEFAUTS)
    filiales = pd.read_csv(DOSSIER_DBT / "seeds" / "ref_filiales.csv")
    depots = pd.read_csv(FICHIER_DEPOTS, parse_dates=["date_ancrage"])
    change = lire_webstat(FICHIER_WEBSTAT)
    change["date_cours"] = pd.to_datetime(change.date_cours)
    texture = charger_texture(fichier_paysim)
    log.info("Taille de lot : %d opérations par ligne ; sortie : %s", POIDS, dossier)

    tous_ancrages, soldes = [], []
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
        t = transactions_filiale(f, flux, texture, taux, rng, encours_moyen_eur(anc, taux))
        exporter_filiale(rng_exports, t, f, dossier)
        soldes.append(soldes_filiale(t))
        del t
    FICHIER_ANCRAGES.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(tous_ancrages).to_csv(FICHIER_ANCRAGES, index=False)
    ecrire_soldes(soldes, dossier)
    return dossier


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    generer()
