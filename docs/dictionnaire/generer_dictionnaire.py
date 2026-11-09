"""Génère le dictionnaire de données Excel du MOE POC : une ligne par colonne.

    python docs/dictionnaire/generer_dictionnaire.py

Lit les 20 tables du schéma en étoile (schéma marts : 5 dimensions et 15 tables de faits) dans
PostgreSQL, après `python pipeline.py`, et y associe les descriptions de descriptions.py.
Une colonne sans description est signalée : la compléter dans descriptions.py.
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

DIMENSIONS = ["dim_date", "dim_filiale", "dim_devise", "dim_type_transaction", "dim_scenario_stress"]
CLE_DIMENSION = {"dim_date": "date_jour", "dim_filiale": "code_filiale", "dim_devise": "code_devise",
                 "dim_type_transaction": "code_type", "dim_scenario_stress": "code_scenario"}
CLE_ETRANGERE = {"code_filiale": "dim_filiale", "code_devise": "dim_devise",
                 "code_type": "dim_type_transaction", "code_scenario": "dim_scenario_stress"}
DATES_HORS_CLE = {"origine", "date_calcul"}          # dates qui ne servent pas à relier la table au calendrier
NUMERIQUES = ("numeric", "double precision", "integer", "bigint", "smallint", "real")
ATTRIBUTS_NUMERIQUES = {"heure"}                       # nombres qui décrivent la ligne, sans être des quantités

# stocks (semi-additifs) et flux (additifs), testés avant les motifs non additifs
INSTANTANES = {"fct_position_tresorerie_quotidienne", "mart_liquidite_placement", "mart_exposition_change",
               "mart_qualite_ancrage", "mart_prevision_tresorerie", "mart_controle_a_posteriori"}
NON_ADDITIF = ("pct", "pts", "taux", "ratio", "volatilite", "proba", "jours", "variation", "rapport",
               "multiplicateur", "valeur_eur_par_unite", "_bp", "var_95")
STOCK = ("position", "encours", "cible", "reserve_liquidite", "exposition", "effet_change", "besoin_liquidite",
         "depots_", "liquidite_", "ecart_devise")
FLUX = ("encaissements", "decaissements", "flux_net", "operation_tresorerie", "reel", "prevu", "impact_")

TYPES_SQL = {"text": "texte", "character varying": "texte", "double precision": "décimal", "numeric": "décimal",
             "real": "décimal", "integer": "entier", "bigint": "entier", "smallint": "entier",
             "boolean": "booléen", "date": "date"}

COULEUR = {"Dimension": "DDEBF7", "Fait": "FCE4D6"}
ENTETE = PatternFill("solid", fgColor="1F3864")
POLICE = "Arial"
BORDURE = Border(*(Side(style="thin", color="BFBFBF"),) * 4)


# ------------------------------------------------------------------------------- lecture base
def lire_structure(cnx) -> list[dict]:
    lignes = cnx.execute(
        """select table_name, column_name, data_type, ordinal_position
           from information_schema.columns
           where table_schema = 'marts' and (table_name like 'dim\\_%%' or table_name like 'fct\\_%%'
                                              or table_name like 'mart\\_%%')
           order by table_name, ordinal_position""").fetchall()
    tables: dict[str, dict] = {}
    for table, col, dtype, pos in lignes:
        tables.setdefault(table, {"table": table, "colonnes": []})["colonnes"].append(
            {"nom": col, "type": dtype, "pos": pos})
    for t in tables.values():
        ident = f'marts."{t["table"]}"'
        t["nb_lignes"] = cnx.execute(f"select count(*) from {ident}").fetchone()[0]
        # exemples pris de préférence dans la période d'analyse (2023-2025)
        date = next((c["nom"] for c in t["colonnes"] if c["type"] == "date" and c["nom"] not in DATES_HORS_CLE), None)
        echantillon = []
        if date:
            echantillon = cnx.execute(
                f"""select * from {ident} where "{date}" between '2023-01-01' and '2025-12-31' limit 200""").fetchall()
        echantillon = echantillon or cnx.execute(f"select * from {ident} limit 200").fetchall()
        for i, c in enumerate(t["colonnes"]):
            c["exemple"] = next((formater(r[i]) for r in echantillon if r[i] not in (None, "")), "")
            if not c["exemple"]:
                r = cnx.execute(f'select "{c["nom"]}" from {ident} where "{c["nom"]}" is not null limit 1').fetchone()
                c["exemple"] = formater(r[0]) if r else "(vide)"
    rang = {"dim": 0, "fct": 1, "mart": 2}
    return sorted(tables.values(), key=lambda t: (rang[t["table"].split("_")[0]], t["table"]))


def jeu_de_donnees(cnx) -> str:
    lignes = cnx.execute("select coalesce(sum(nb_lignes_brutes), 0) from marts.mart_qualite_sources").fetchone()[0]
    return "gros volume (lots de 50 opérations)" if lignes > 10_000_000 else "jeu léger (lots de 500 opérations)"


def formater(v) -> str:
    if isinstance(v, bool):
        return "Vrai" if v else "Faux"
    if isinstance(v, (float, Decimal)):
        v = float(v) + 0.0                      # évite l'affichage « -0 »
        if v == 0:
            return "0"
        decimales = 0 if abs(v) >= 100 else 2 if abs(v) >= 1 else 4
        texte = f"{v:,.{decimales}f}"
        if decimales:
            texte = texte.rstrip("0").rstrip(".")
        return texte.replace(",", " ").replace(".", ",")
    if isinstance(v, dt.datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, dt.date):
        return v.strftime("%d/%m/%Y")
    texte = str(v).strip()
    return texte[:60] + "…" if len(texte) > 60 else texte


def tables_power_bi() -> set[str]:
    return {p.stem for p in DOSSIER_TMDL.glob("*.tmdl")}


# --------------------------------------------------------------------------- classification
def type_table(table: str) -> str:
    return "Dimension" if table.startswith("dim_") else "Fait"


def role(table: str, c: dict) -> str:
    nom, dtype = c["nom"], c["type"]
    if table.startswith("dim_"):
        if nom == CLE_DIMENSION.get(table):
            return "Clé primaire"
        if nom in CLE_ETRANGERE:
            return f"Clé étrangère ({CLE_ETRANGERE[nom]})"
        return "Attribut"
    if nom.startswith("id_") and c["pos"] == 1:
        return "Clé primaire"
    if nom in CLE_ETRANGERE:
        return f"Clé étrangère ({CLE_ETRANGERE[nom]})"
    if dtype == "date" and nom not in DATES_HORS_CLE:
        return "Clé étrangère (dim_date)"
    if dtype in NUMERIQUES and nom not in ATTRIBUTS_NUMERIQUES:
        return "Mesure"
    return "Attribut"


def additivite(table: str, nom: str) -> str:
    if nom.startswith("nb_"):
        return "Additive"
    if "moyen" in nom:
        return "Semi-additive"
    if nom.startswith(FLUX):
        return "Additive"
    if nom.startswith(STOCK):
        return "Semi-additive"
    if any(m in nom for m in NON_ADDITIF):
        return "Non additive"
    return "Semi-additive" if table in INSTANTANES else "Additive"


def unite(nom: str) -> str:
    if nom in ("taux_eur", "taux_eur_jour", "taux_eur_reference", "taux_reference", "taux", "taux_depart",
               "taux_realise") or nom.startswith("taux_p"):
        return "Devise pour 1 EUR"
    if nom == "valeur_eur_par_unite":
        return "EUR pour 1 unité"
    if nom.endswith("_bp"):
        return "Points de base"
    if nom.endswith("_pts"):
        return "Points de %"
    if "jours" in nom:
        return "Jours"
    if "pct" in nom:
        return "%"
    if nom.startswith("proba"):
        return "Probabilité"
    if nom in ("rapport_cout_risque", "multiplicateur_sorties"):
        return "Coefficient"
    if nom in ("volatilite_quotidienne", "ratio_reserve_sur_depots"):
        return "Fraction"
    if nom.startswith("nb_"):
        return "Nombre"
    if nom.endswith("_eur") or "_eur_" in nom:
        return "EUR"
    if "devise" in nom or nom in ("reel", "prevu"):
        return "Devise locale"
    return "Nombre"


def description(table: str, nom: str) -> str:
    return COLONNES.get(table, {}).get(nom) or COMMUNES.get(nom, "")


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


def ecrire(tables: list[dict], jeu: str) -> tuple[int, int, list[str]]:
    wb = Workbook()
    pbi = tables_power_bi()
    manquantes: list[str] = []

    # ---------- Dictionnaire : une ligne par colonne
    wd = wb.active
    wd.title = "Dictionnaire"
    titres = ["Table", "Type", "N°", "Colonne", "Type de donnée", "Rôle", "Additivité", "Unité",
              "Description", "Exemple"]
    entete(wd, 1, titres, [32, 11, 5, 32, 12, 26, 14, 16, 70, 24])
    ligne = 2
    for t in tables:
        tt = type_table(t["table"])
        for c in t["colonnes"]:
            r = role(t["table"], c)
            desc = description(t["table"], c["nom"])
            if not desc:
                manquantes.append(f'{t["table"]}.{c["nom"]}')
            mesure = r == "Mesure"
            valeurs = [t["table"], tt, c["pos"], c["nom"], TYPES_SQL.get(c["type"], "date et heure"), r,
                       additivite(t["table"], c["nom"]) if mesure else "", unite(c["nom"]) if mesure else "",
                       desc, c["exemple"]]
            for j, v in enumerate(valeurs, start=1):
                corps(wd.cell(row=ligne, column=j, value=v), COULEUR[tt], gras=(j == 4 and r == "Clé primaire"))
            ligne += 1
    derniere = ligne - 1
    wd.freeze_panes = "E2"
    wd.auto_filter.ref = f"A1:{get_column_letter(len(titres))}{derniere}"
    nb_colonnes = derniere - 1

    # ---------- Tables : une ligne par table
    wt = wb.create_sheet("Tables", 0)
    titres_t = ["N°", "Table", "Type", "Type de fait", "Répond à", "Grain", "Nb colonnes",
                "Nb lignes", "Dans Power BI", "Description"]
    entete(wt, 1, titres_t, [5, 34, 11, 28, 22, 42, 11, 13, 10, 80])
    for i, t in enumerate(tables, start=1):
        meta = TABLES.get(f'marts.{t["table"]}', {})
        if not meta:
            manquantes.append(f'TABLE {t["table"]}')
        tt = type_table(t["table"])
        n = i + 1
        valeurs = [i, t["table"], tt, "" if tt == "Dimension" else meta.get("type", ""), meta.get("question", ""),
                   meta.get("grain", ""), f'=COUNTIFS(Dictionnaire!$A$2:$A${derniere},B{n})', t["nb_lignes"],
                   "Oui" if t["table"] in pbi else "Non", meta.get("description", "")]
        for j, v in enumerate(valeurs, start=1):
            cell = wt.cell(row=n, column=j, value=v)
            corps(cell, COULEUR[tt], gras=(j == 2))
            if j == 8:
                cell.number_format = "#,##0"
    wt.freeze_panes = "C2"
    wt.auto_filter.ref = f"A1:J{len(tables) + 1}"

    # ---------- Faits x dimensions
    wm = wb.create_sheet("Faits x dimensions", 1)
    wm["A1"] = "Dimensions reliées à chaque table de faits"
    wm["A1"].font = Font(name=POLICE, bold=True, size=12)
    wm["A2"] = "✓ : la table de faits contient la clé de la dimension (calculé à partir de l'onglet Dictionnaire)."
    wm["A2"].font = Font(name=POLICE, italic=True, size=10)
    entete(wm, 4, ["Table de faits", "Grain"] + DIMENSIONS + ["Nb mesures"], [34, 46] + [16] * len(DIMENSIONS) + [11])
    faits = [t for t in tables if not t["table"].startswith("dim_")]
    for i, t in enumerate(faits, start=5):
        meta = TABLES.get(f'marts.{t["table"]}', {})
        corps(wm.cell(row=i, column=1, value=t["table"]), COULEUR["Fait"], gras=True)
        corps(wm.cell(row=i, column=2, value=meta.get("grain", "")), COULEUR["Fait"])
        for j in range(3, 3 + len(DIMENSIONS)):
            col = get_column_letter(j)
            f = (f'=IF(COUNTIFS(Dictionnaire!$A$2:$A${derniere},$A{i},Dictionnaire!$F$2:$F${derniere},'
                 f'"Clé étrangère ("&{col}$4&")")>0,"✓","")')
            cell = wm.cell(row=i, column=j, value=f)
            corps(cell)
            cell.alignment = Alignment(horizontal="center", vertical="top")
        corps(wm.cell(row=i, column=3 + len(DIMENSIONS),
                      value=f'=COUNTIFS(Dictionnaire!$A$2:$A${derniere},$A{i},Dictionnaire!$F$2:$F${derniere},"Mesure")'))
    wm.freeze_panes = "B5"

    # ---------- Lisez-moi
    wl = wb.create_sheet("Lisez-moi", 0)
    wl.column_dimensions["A"].width = 30
    wl.column_dimensions["B"].width = 110
    nb_t = len(tables) + 1
    lignes = [
        ("Dictionnaire de données du projet Crésus", None),
        ("MOE POC, IBI sujet 3 « BI prédictive Finance », groupe G5", None),
        ("", None),
        ("Contenu", "Les tables du schéma en étoile (schéma marts, couche Gold) : les dimensions et les tables "
                    "de faits, avec toutes leurs colonnes."),
        ("Nombre de lignes", f"Compté sur le {jeu}."),
        ("Nombre de tables", f"=COUNTA(Tables!B2:B{nb_t})"),
        ("Dont dimensions", f'=COUNTIFS(Tables!C2:C{nb_t},"Dimension")'),
        ("Dont tables de faits", f'=COUNTIFS(Tables!C2:C{nb_t},"Fait")'),
        ("Nombre de colonnes", f"=COUNTA(Dictionnaire!D2:D{derniere})"),
        ("", None),
        ("Onglets", None),
        ("Tables", "Une ligne par table : type, question à laquelle elle répond, grain, volume."),
        ("Faits x dimensions", "Les dimensions reliées à chaque table de faits."),
        ("Dictionnaire", "Une ligne par colonne : type de donnée, rôle, additivité, unité, description, exemple."),
        ("", None),
        ("Dimensions et faits", "Une dimension décrit le contexte (qui, quoi, quand, où). Une table de faits "
                                "contient les mesures (combien). Aucune dimension ne contient de mesure : c'est la "
                                "règle RG-MOD-01, vérifiée par un test dbt à chaque exécution."),
        ("Nombres dans les dimensions", "Quelques colonnes de dimension sont des nombres sans être des quantités : "
                                        "la parité fixe du franc CFA (655,957 pour 1 euro), le sens d'un type "
                                        "d'opération (+1 ou -1), l'ordre d'affichage et les numéros du calendrier "
                                        "(année, mois, semaine). On ne les additionne jamais."),
        ("Préfixes", "dim_ pour une dimension, fct_ pour un fait de base, mart_ pour un fait calculé à partir "
                     "des autres (analyse, prévision, qualité)."),
        ("", None),
        ("Rôle", None),
        ("Clé primaire", "Identifie une ligne de la table."),
        ("Clé étrangère", "Relie la table à la dimension indiquée entre parenthèses."),
        ("Attribut", "Texte, code, date ou indicateur Vrai / Faux qui décrit la ligne."),
        ("Mesure", "Nombre que l'on additionne, compare ou moyenne."),
        ("", None),
        ("Additivité des mesures", None),
        ("Additive", "S'additionne sur toutes les dimensions, par exemple les décaissements."),
        ("Semi-additive", "Un stock. Il s'additionne entre filiales, pas dans le temps : on lit le dernier jour, "
                          "par exemple pour la position."),
        ("Non additive", "Ne s'additionne pas : ratio, taux, pourcentage, nombre de jours. La VaR du groupe "
                         "additionne les VaR par devise, ce qui donne une estimation prudente."),
        ("Devise locale", "Un montant en devise locale ne s'additionne jamais entre filiales. On additionne les "
                          "colonnes en euros (_eur)."),
    ]
    for i, (a, b) in enumerate(lignes, start=1):
        ca, cb = wl.cell(row=i, column=1, value=a), wl.cell(row=i, column=2, value=b)
        ca.font = Font(name=POLICE, size=10, bold=True)
        cb.font = Font(name=POLICE, size=10)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
    wl["A1"].font = Font(name=POLICE, size=14, bold=True)
    wl["A2"].font = Font(name=POLICE, size=10, italic=True)
    for i, (a, b) in enumerate(lignes, start=1):
        if a and b is None and i > 2:
            wl.cell(row=i, column=1).font = Font(name=POLICE, size=11, bold=True, color="1F3864")

    wb.calculation.fullCalcOnLoad = True      # Excel recalcule les formules à l'ouverture
    SORTIE.parent.mkdir(exist_ok=True)
    wb.save(SORTIE)
    return len(tables), nb_colonnes, manquantes


def main() -> None:
    with psycopg.connect(**PG) as cnx:
        tables = lire_structure(cnx)
        jeu = jeu_de_donnees(cnx)
    nb_t, nb_c, manquantes = ecrire(tables, jeu)
    print(f"{SORTIE.name} : {nb_t} tables, {nb_c} colonnes ({jeu})")
    if manquantes:
        print(f"{len(manquantes)} description(s) manquante(s) :")
        for m in manquantes:
            print("  -", m)


if __name__ == "__main__":
    main()
