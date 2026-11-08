"""Génère le dictionnaire de données Excel du projet Crésus (livrable complémentaire du MOE POC).

    python docs/dictionnaire/generer_dictionnaire.py

Lit la structure RÉELLE des tables dans PostgreSQL (après `python pipeline.py`), y associe les
descriptions de docs/dictionnaire/descriptions.py, puis écrit :
    livrables/05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_BI-predictive-Finance_G5.xlsx

Onglets : Lisez-moi · Tables (1 ligne par table) · Dictionnaire (1 ligne par colonne) ·
Faits x dimensions (matrice du schéma en étoile).
"""
from __future__ import annotations

import datetime as dt
import sys
from decimal import Decimal
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg                                                    # noqa: E402
from openpyxl import Workbook                                     # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side   # noqa: E402
from openpyxl.utils import get_column_letter                      # noqa: E402

from descriptions import COLONNES, COMMUNES, TABLES               # noqa: E402
from etl.config import PG                                         # noqa: E402

SORTIE = RACINE / "livrables" / "05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_BI-predictive-Finance_G5.xlsx"
DOSSIER_TMDL = RACINE / "powerbi" / "Cresus" / "Cresus.SemanticModel" / "definition" / "tables"

# ordre de présentation : le schéma en étoile d'abord, puis l'amont de la chaîne
COUCHES = [
    ("marts", "Or (schéma en étoile)"),
    ("ml", "Prédictif (sorties Python)"),
    ("referentiel", "Référentiels (seeds dbt)"),
    ("intermediate", "Argent (intermediate)"),
    ("staging", "Argent (staging)"),
    ("raw", "Bronze (données brutes)"),
]
DIMENSIONS = ["dim_date", "dim_filiale", "dim_devise", "dim_type_transaction", "dim_scenario_stress"]
CLE_DIMENSION = {"dim_date": "date_jour", "dim_filiale": "code_filiale", "dim_devise": "code_devise",
                 "dim_type_transaction": "code_type", "dim_scenario_stress": "code_scenario"}
CLE_ETRANGERE = {"code_filiale": "dim_filiale", "code_devise": "dim_devise",
                 "code_type": "dim_type_transaction", "code_scenario": "dim_scenario_stress"}
TECHNIQUES = {"nom_fichier", "num_ligne", "_fichier", "_ligne", "_date_chargement", "date_calcul",
              "id_ligne_source", "date_chargement", "empreinte_md5"}
# faits « instantanés » : un stock ne s'additionne pas dans le temps
INSTANTANES = {"fct_position_tresorerie_quotidienne", "mart_liquidite_placement", "mart_exposition_change",
               "mart_qualite_ancrage", "mart_prevision_tresorerie", "mart_controle_a_posteriori",
               "prevision_tresorerie_quotidienne", "controle_depots_reels"}
NON_ADDITIF = ("pct", "pts", "taux", "ratio", "volatilite", "proba", "jours", "variation", "rapport",
               "multiplicateur", "valeur_eur_par_unite", "_bp")
# préfixes de stocks (semi-additifs) et de flux (additifs) ; testés avant les motifs non additifs
STOCK = ("position", "encours", "cible", "reserve_liquidite", "exposition", "effet_change", "besoin_liquidite",
         "depots_", "liquidite_", "ecart_devise")
FLUX = ("encaissements", "decaissements", "flux_net", "operation_tresorerie", "reel", "prevu", "impact_")

COULEUR = {"Dimension": "DDEBF7", "Fait": "FCE4D6", "Sortie": "FFF2CC", "Référentiel": "E2EFDA"}
ENTETE = PatternFill("solid", fgColor="1F3864")
POLICE = "Arial"
BORDURE = Border(*(Side(style="thin", color="BFBFBF"),) * 4)


# ------------------------------------------------------------------------------- lecture base
def lire_structure(cnx) -> list[dict]:
    schemas = [s for s, _ in COUCHES]
    lignes = cnx.execute(
        """select c.table_schema, c.table_name, t.table_type, c.column_name, c.data_type, c.ordinal_position
           from information_schema.columns c
           join information_schema.tables t using (table_schema, table_name)
           where c.table_schema = any(%s)
           order by c.table_schema, c.table_name, c.ordinal_position""", (schemas,)).fetchall()
    tables: dict[tuple, dict] = {}
    for schema, table, ttype, col, dtype, pos in lignes:
        t = tables.setdefault((schema, table), {"schema": schema, "table": table, "vue": ttype == "VIEW", "colonnes": []})
        t["colonnes"].append({"nom": col, "type": dtype, "pos": pos})
    for t in tables.values():
        ident = f'"{t["schema"]}"."{t["table"]}"'
        t["nb_lignes"] = None if t["vue"] else cnx.execute(f"select count(*) from {ident}").fetchone()[0]
        noms = [c["nom"] for c in t["colonnes"]]
        echantillon = cnx.execute(f"select * from {ident} limit 200").fetchall()
        for i, c in enumerate(t["colonnes"]):
            c["exemple"] = next((formater(r[i]) for r in echantillon if r[i] not in (None, "")), "")
            if not c["exemple"]:                # colonne vide sur l'échantillon : on cherche une valeur ailleurs
                r = cnx.execute(f'select "{c["nom"]}" from {ident} where "{c["nom"]}" is not null limit 1').fetchone()
                c["exemple"] = formater(r[0]) if r else "(toujours vide dans ce système)"
        assert len(noms) == len(t["colonnes"])
    ordre = {s: i for i, (s, _) in enumerate(COUCHES)}

    def cle(t):
        nom = t["table"]
        rang = 0 if nom.startswith("dim_") else 1 if nom.startswith("fct_") else 2
        return ordre[t["schema"]], rang, nom
    return sorted(tables.values(), key=cle)


def formater(v) -> str:
    if isinstance(v, bool):
        return "Vrai" if v else "Faux"
    if isinstance(v, (float, Decimal)):
        v = float(v) + 0.0                      # évite l'affichage « -0 »
        if v == 0:
            return "0"
        return f"{v:,.4f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",") if abs(v) < 1e15 else str(v)
    if isinstance(v, dt.datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    texte = str(v).strip()
    return texte[:60] + "…" if len(texte) > 60 else texte


def tables_power_bi() -> set[str]:
    return {p.stem for p in DOSSIER_TMDL.glob("*.tmdl") if p.stem.startswith(("dim_", "fct_", "mart_"))}


# --------------------------------------------------------------------------- classification
def famille(type_table: str) -> str:
    for cle in ("Dimension", "Fait", "Sortie", "Référentiel"):
        if type_table.startswith(cle):
            return cle
    return ""


def role(t: dict, type_table: str, c: dict) -> str:
    nom, dtype = c["nom"], c["type"]
    if nom in TECHNIQUES:
        return "Technique (traçabilité)"
    fam = famille(type_table)
    if fam == "Dimension":
        if nom == CLE_DIMENSION.get(t["table"]):
            return "Clé primaire"
        if nom in CLE_ETRANGERE:
            return f"Clé étrangère → {CLE_ETRANGERE[nom]}"
        return "Attribut descriptif"
    if fam in ("Fait", "Sortie"):
        if nom.startswith("id_") and c["pos"] == 1:
            return "Clé primaire (technique)"
        if nom in CLE_ETRANGERE:
            return f"Clé étrangère → {CLE_ETRANGERE[nom]}"
        if dtype == "date":
            return "Clé étrangère → dim_date"
        if dtype == "boolean":
            return "Indicateur (dimension dégénérée)"
        if dtype.startswith("timestamp") or nom == "heure":
            return "Attribut temporel (dimension dégénérée)"
        if dtype in ("text", "character varying"):
            return "Attribut qualitatif du fait"
        return "Mesure"
    if t["schema"] == "raw":
        return "Donnée brute" + (" (texte)" if dtype == "text" else "")
    if nom.startswith(("code_", "id_", "ref_")) or nom in ("valeur_normalisee", "id_client"):
        return "Clé / identifiant"
    if dtype == "boolean":
        return "Indicateur de contrôle"
    if dtype == "date" or dtype.startswith("timestamp"):
        return "Date"
    if dtype in ("text", "character varying"):
        return "Attribut"
    return "Paramètre" if fam == "Référentiel" else "Valeur numérique"


def additivite(t: dict, c: dict, r: str) -> str:
    if r != "Mesure":
        return ""
    nom, table = c["nom"], t["table"]
    if nom.startswith("var_95"):
        return "Non additive (la somme des devises est une borne prudente)"
    semi = "Semi-additive (stock : pas de somme dans le temps)"
    if nom.startswith("nb_"):
        return "Additive"
    if "moyen" in nom:
        return "Semi-additive (moyenne glissante : pas de somme dans le temps)"
    if nom.startswith(FLUX):
        return "Additive"
    if nom.startswith(STOCK):
        return semi
    if any(m in nom for m in NON_ADDITIF):
        return "Non additive"
    if table in INSTANTANES:          # fait instantané : chaque jour est une photo, on ne somme pas les jours
        return semi
    return "Additive"


def unite(c: dict, r: str) -> str:
    nom, dtype = c["nom"], c["type"]
    if dtype == "boolean":
        return "Vrai / Faux"
    if dtype == "date":
        return "Date"
    if dtype.startswith("timestamp"):
        return "Date et heure"
    if dtype in ("text", "character varying"):
        return "Texte"
    if nom in ("taux_eur", "taux_eur_jour", "taux_eur_reference", "taux_reference", "taux", "taux_depart",
               "taux_realise", "parite_fixe_par_eur") or nom.startswith("taux_p"):
        return "Unités de devise pour 1 EUR"
    if nom == "valeur_eur_par_unite":
        return "EUR pour 1 unité de devise"
    if nom.endswith("_bp"):
        return "Points de base"
    if nom.endswith("_pts"):
        return "Points de %"
    if "jours" in nom:
        return "Jours"
    if "pct" in nom:
        return "%"
    if nom.startswith("proba"):
        return "Probabilité (0 à 1)"
    if nom == "rapport_cout_risque":
        return "Ratio"
    if nom.startswith("nb_") or nom in ("nb_operations",):
        return "Nombre"
    if nom in ("volatilite_quotidienne", "ratio_reserve_sur_depots"):
        return "Fraction (0,15 = 15 %)"
    if nom == "multiplicateur_sorties":
        return "Coefficient"
    if nom == "heure":
        return "Heure (0 à 23)"
    if nom.endswith("_eur") or "_eur_" in nom:
        return "EUR"
    if "devise" in nom or nom in ("reel", "prevu", "total_credits", "total_debits", "encours_zf_devise", "total_annonce"):
        return "Devise locale (pas de somme entre devises)"
    if nom in ("annee", "trimestre", "mois", "jour_semaine", "semaine_iso", "id_date", "ordre_affichage",
               "sens", "sens_source", "sens_attendu", "sens_jambe_emetteur", "rang_occurrence", "id_groupe_publication",
               "num_ligne", "_ligne"):
        return "Code / numéro"
    return "Nombre"


def description(t: dict, nom: str) -> str:
    return COLONNES.get(t["table"], {}).get(nom) or COMMUNES.get(nom, "")


# ------------------------------------------------------------------------------- écriture Excel
def entete(ws, ligne: int, titres: list[str], largeurs: list[int]) -> None:
    for j, (titre, largeur) in enumerate(zip(titres, largeurs), start=1):
        cell = ws.cell(row=ligne, column=j, value=titre)
        cell.font = Font(name=POLICE, bold=True, color="FFFFFF", size=10)
        cell.fill = ENTETE
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDURE
        ws.column_dimensions[get_column_letter(j)].width = largeur
    ws.row_dimensions[ligne].height = 30


def corps(cell, couleur: str | None = None, gras: bool = False) -> None:
    cell.font = Font(name=POLICE, size=10, bold=gras)
    cell.alignment = Alignment(vertical="top", wrap_text=True)
    cell.border = BORDURE
    if couleur:
        cell.fill = PatternFill("solid", fgColor=couleur)


def ecrire(tables: list[dict]) -> tuple[int, int, list[str]]:
    wb = Workbook()
    pbi = tables_power_bi()
    couche_de = dict(COUCHES)
    manquantes: list[str] = []

    # ---------- Dictionnaire (1 ligne par colonne)
    wd = wb.active
    wd.title = "Dictionnaire"
    titres = ["Couche", "Schéma", "Table", "Type de table", "N°", "Colonne", "Type SQL", "Rôle",
              "Additivité", "Unité", "Description", "Exemple de valeur"]
    entete(wd, 1, titres, [20, 12, 32, 26, 5, 32, 17, 30, 26, 24, 70, 26])
    ligne = 2
    for t in tables:
        meta = TABLES.get(f'{t["schema"]}.{t["table"]}', {})
        type_table = meta.get("type", "Vue" if t["vue"] else "Table")
        coul = COULEUR.get(famille(type_table))
        for c in t["colonnes"]:
            r = role(t, type_table, c)
            desc = description(t, c["nom"])
            if not desc:
                manquantes.append(f'{t["schema"]}.{t["table"]}.{c["nom"]}')
            valeurs = [couche_de[t["schema"]], t["schema"], t["table"], type_table, c["pos"], c["nom"], c["type"],
                       r, additivite(t, c, r), unite(c, r), desc, c["exemple"]]
            for j, v in enumerate(valeurs, start=1):
                corps(wd.cell(row=ligne, column=j, value=v), coul, gras=(j == 6 and r.startswith("Clé primaire")))
            ligne += 1
    derniere = ligne - 1
    wd.freeze_panes = "G2"
    wd.auto_filter.ref = f"A1:{get_column_letter(len(titres))}{derniere}"
    nb_colonnes = derniere - 1

    # ---------- Tables (1 ligne par table)
    wt = wb.create_sheet("Tables", 0)
    titres_t = ["N°", "Couche", "Schéma", "Table", "Type de table", "Répond à", "Grain", "Nb colonnes",
                "Nb lignes (jeu léger)", "Importée dans Power BI", "Description"]
    entete(wt, 1, titres_t, [5, 20, 12, 32, 26, 22, 42, 11, 14, 12, 80])
    for i, t in enumerate(tables, start=1):
        meta = TABLES.get(f'{t["schema"]}.{t["table"]}', {})
        type_table = meta.get("type", "Vue" if t["vue"] else "Table")
        coul = COULEUR.get(famille(type_table))
        n = i + 1
        valeurs = [i, couche_de[t["schema"]], t["schema"], t["table"], type_table, meta.get("question", ""),
                   meta.get("grain", ""),
                   f'=COUNTIFS(Dictionnaire!$B$2:$B${derniere},C{n},Dictionnaire!$C$2:$C${derniere},D{n})',
                   t["nb_lignes"] if t["nb_lignes"] is not None else "vue",
                   "Oui" if t["schema"] == "marts" and t["table"] in pbi else "Non",
                   meta.get("description", "")]
        for j, v in enumerate(valeurs, start=1):
            cell = wt.cell(row=n, column=j, value=v)
            corps(cell, coul, gras=(j == 4))
            if j == 9 and isinstance(v, int):
                cell.number_format = "#,##0"
        if not meta:
            manquantes.append(f'TABLE {t["schema"]}.{t["table"]}')
    wt.freeze_panes = "E2"
    wt.auto_filter.ref = f"A1:K{len(tables) + 1}"

    # ---------- Faits x dimensions (matrice en bus)
    wm = wb.create_sheet("Faits x dimensions", 1)
    wm["A1"] = "Matrice du schéma en étoile : quelles dimensions décrivent chaque table de faits"
    wm["A1"].font = Font(name=POLICE, bold=True, size=12)
    wm["A2"] = ("✓ = la table de faits porte la clé de la dimension (calculé à partir de l'onglet "
                "Dictionnaire). Les dimensions répondent à qui / quoi / quand / où ; les faits à « combien ».")
    wm["A2"].font = Font(name=POLICE, italic=True, size=10)
    entete(wm, 4, ["Table de faits", "Type de fait", "Grain"] + DIMENSIONS + ["Nb mesures"],
           [34, 30, 46] + [16] * len(DIMENSIONS) + [11])
    faits = [t for t in tables if t["schema"] == "marts" and not t["table"].startswith("dim_")]
    for i, t in enumerate(faits, start=5):
        meta = TABLES.get(f'marts.{t["table"]}', {})
        corps(wm.cell(row=i, column=1, value=t["table"]), COULEUR["Fait"], gras=True)
        corps(wm.cell(row=i, column=2, value=meta.get("type", "")), COULEUR["Fait"])
        corps(wm.cell(row=i, column=3, value=meta.get("grain", "")), COULEUR["Fait"])
        for j, d in enumerate(DIMENSIONS, start=4):
            col = get_column_letter(j)
            f = (f'=IF(COUNTIFS(Dictionnaire!$C$2:$C${derniere},$A{i},Dictionnaire!$H$2:$H${derniere},'
                 f'"Clé étrangère → "&{col}$4)>0,"✓","")')
            cell = wm.cell(row=i, column=j, value=f)
            corps(cell)
            cell.alignment = Alignment(horizontal="center", vertical="top")
        cell = wm.cell(row=i, column=len(DIMENSIONS) + 4,
                       value=f'=COUNTIFS(Dictionnaire!$C$2:$C${derniere},$A{i},Dictionnaire!$H$2:$H${derniere},"Mesure")')
        corps(cell)
    wm.freeze_panes = "B5"

    # ---------- Lisez-moi
    wl = wb.create_sheet("Lisez-moi", 0)
    wl.column_dimensions["A"].width = 30
    wl.column_dimensions["B"].width = 110
    lignes = [
        ("Dictionnaire de données — Projet Crésus (ZF Banque)", None),
        ("Livrable complémentaire du MOE POC — IBI, sujet 3 « BI prédictive Finance », groupe G5", None),
        ("", None),
        ("Généré le", dt.date.today().strftime("%d/%m/%Y")),
        ("Source", "Structure réelle de l'entrepôt PostgreSQL (base cresus) après `python pipeline.py`, "
                   "descriptions dans docs/dictionnaire/descriptions.py. Régénérer : "
                   "python docs/dictionnaire/generer_dictionnaire.py"),
        ("Jeu de données", "Jeu versionné (lots de 500 opérations). Le nombre de lignes est compté sur ce jeu ; "
                           "le gros volume (lots de 50) multiplie par environ 10 les tables d'opérations."),
        ("Nombre de tables", f"=COUNTA(Tables!D2:D{len(tables) + 1})"),
        ("Nombre de colonnes", f"=COUNTA(Dictionnaire!F2:F{derniere})"),
        ("Dont dimensions", f'=COUNTIFS(Tables!E2:E{len(tables) + 1},"Dimension")'),
        ("Dont tables de faits (marts)", f'=COUNTIFS(Tables!C2:C{len(tables) + 1},"marts",Tables!E2:E{len(tables) + 1},"Fait*")'),
        ("", None),
        ("Onglets", None),
        ("Tables", "Une ligne par table : couche, type (dimension ou fait), question à laquelle elle répond, grain, volume."),
        ("Faits x dimensions", "Matrice du schéma en étoile : les dimensions qui décrivent chaque table de faits."),
        ("Dictionnaire", "Une ligne par colonne : type, rôle, additivité, unité, description et exemple réel."),
        ("", None),
        ("Règle RG-MOD-01", "Une dimension décrit le CONTEXTE (qui, quoi, quand, où) et ne contient aucune mesure. "
                            "Une table de faits contient les MESURES (combien). Les nombres autrefois portés par "
                            "dim_filiale (part de marché, taux de réserve, clients, encours et réserve de départ) sont "
                            "dans fct_situation_initiale_filiale ; les chocs chiffrés de dim_scenario_stress sont dans "
                            "mart_stress_test. Le test dbt assert_dimensions_sans_mesure le vérifie à chaque exécution."),
        ("Convention de nommage", "dim_ = dimension · fct_ = fait de base · mart_ = fait dérivé (analyse, qualité, "
                                  "prévision) · ref_ = référentiel · stg_ / int_ = nettoyage · src_ = donnée brute."),
        ("", None),
        ("Légende des couleurs", None),
        ("Dimension", "Contexte : qui, quoi, quand, où"),
        ("Fait", "Mesures : combien"),
        ("Sortie de modèle", "Résultats Python (schéma ml), repris par les faits de prévision"),
        ("Référentiel", "Paramétrage (seeds dbt)"),
        ("", None),
        ("Rôle", None),
        ("Clé primaire", "Identifie une ligne de la table."),
        ("Clé étrangère → dim_x", "Relie le fait à une dimension (filtre dans Power BI)."),
        ("Mesure", "Nombre que l'on agrège (somme, moyenne, dernier jour…)."),
        ("Attribut descriptif", "Texte ou code qui décrit le contexte, dans une dimension."),
        ("Dimension dégénérée", "Indicateur ou attribut stocké dans le fait sans table de dimension propre."),
        ("", None),
        ("Additivité", None),
        ("Additive", "Se somme sur toutes les dimensions (ex. décaissements)."),
        ("Semi-additive", "Stock : se somme entre filiales mais pas dans le temps ; on lit le dernier jour (ex. position)."),
        ("Non additive", "Ne se somme jamais : ratio, taux, pourcentage, nombre de jours (ex. ratio de liquidité)."),
        ("Devise locale", "Un montant en devise locale ne s'additionne jamais entre filiales de devises différentes : utiliser la colonne _eur."),
    ]
    for i, (a, b) in enumerate(lignes, start=1):
        ca, cb = wl.cell(row=i, column=1, value=a), wl.cell(row=i, column=2, value=b)
        ca.font = Font(name=POLICE, size=10, bold=True)
        cb.font = Font(name=POLICE, size=10)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if a in COULEUR or a == "Sortie de modèle":
            ca.fill = PatternFill("solid", fgColor=COULEUR["Sortie" if a == "Sortie de modèle" else a])
    wl["A1"].font = Font(name=POLICE, size=14, bold=True)
    wl["A2"].font = Font(name=POLICE, size=10, italic=True)
    for titre in ("Onglets", "Légende des couleurs", "Rôle", "Additivité"):
        for i, (a, _) in enumerate(lignes, start=1):
            if a == titre:
                wl.cell(row=i, column=1).font = Font(name=POLICE, size=11, bold=True, color="1F3864")

    wb.calculation.fullCalcOnLoad = True      # Excel recalcule les formules à l'ouverture
    SORTIE.parent.mkdir(exist_ok=True)
    wb.save(SORTIE)
    return len(tables), nb_colonnes, manquantes


def main() -> None:
    with psycopg.connect(**PG) as cnx:
        tables = lire_structure(cnx)
    nb_t, nb_c, manquantes = ecrire(tables)
    print(f"{SORTIE.name} : {nb_t} tables, {nb_c} colonnes")
    if manquantes:
        print(f"{len(manquantes)} description(s) manquante(s) :")
        for m in manquantes:
            print("  -", m)


if __name__ == "__main__":
    main()
