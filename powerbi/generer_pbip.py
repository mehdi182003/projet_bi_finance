"""Génère le projet Power BI (format .pbip) du cockpit Crésus.

Le projet est un dossier de fichiers texte que Power BI Desktop ouvre directement
(Fichier > Ouvrir > Cresus.pbip) :
  Cresus/Cresus.pbip                      raccourci à ouvrir
  Cresus/Cresus.SemanticModel/            modèle de données (TMDL) : tables, relations, mesures DAX
  Cresus/Cresus.Report/                   rapport (PBIR) : 6 pages et leurs visuels

Étapes :
  1. lit la structure des tables du schéma `marts` dans PostgreSQL (noms et types de colonnes) ;
  2. construit le modèle au format TMSL (model.bim), avec les mesures de powerbi/mesures_dax.dax ;
  3. le convertit en TMDL avec la bibliothèque officielle Microsoft (outil .NET TomTool), qui le valide ;
  4. écrit le rapport (pages, visuels) et le valide contre les schémas JSON publiés par Microsoft.

Usage :
  dotnet build powerbi/outils/TomTool -c Release -o powerbi/outils/TomTool/bin   (nécessite le SDK .NET 8)
  python powerbi/generer_pbip.py --tomtool powerbi/outils/TomTool/bin/TomTool.dll [--schemas <clone microsoft/json-schemas>]
Le résultat est versionné : il n'est nécessaire de relancer ce script que si le modèle dbt change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
from etl.db import connexion  # noqa: E402

DOSSIER_PBI = RACINE / "powerbi"
NOM = "Cresus"
SCHEMA_URL = "https://developer.microsoft.com/json-schemas/fabric"
V_REPORT, V_PAGE, V_VISUAL = "2.0.0", "2.0.0", "2.0.0"

# Tables du schéma marts importées dans le modèle
TABLES = [
    "dim_date", "dim_filiale", "dim_devise", "dim_type_transaction", "dim_scenario_stress",
    "fct_flux_tresorerie_horaire", "fct_position_tresorerie_quotidienne", "fct_taux_change",
    "mart_exposition_change", "mart_liquidite_placement", "mart_stress_test",
    "mart_prevision_tresorerie", "mart_prevision_change", "mart_qualite_prevision",
    "mart_backtest_journalier", "mart_qualite_donnees",
]

# (table « plusieurs », colonne) -> (table « un », colonne)
RELATIONS = [
    ("fct_flux_tresorerie_horaire", "date_operation", "dim_date", "date_jour"),
    ("fct_position_tresorerie_quotidienne", "date_position", "dim_date", "date_jour"),
    ("fct_taux_change", "date_cours", "dim_date", "date_jour"),
    ("mart_exposition_change", "date_position", "dim_date", "date_jour"),
    ("mart_liquidite_placement", "date_position", "dim_date", "date_jour"),
    ("mart_prevision_tresorerie", "date_jour", "dim_date", "date_jour"),
    ("mart_prevision_change", "date_jour", "dim_date", "date_jour"),
    ("mart_backtest_journalier", "date_jour", "dim_date", "date_jour"),
    ("fct_flux_tresorerie_horaire", "code_filiale", "dim_filiale", "code_filiale"),
    ("fct_position_tresorerie_quotidienne", "code_filiale", "dim_filiale", "code_filiale"),
    ("mart_liquidite_placement", "code_filiale", "dim_filiale", "code_filiale"),
    ("mart_stress_test", "code_filiale", "dim_filiale", "code_filiale"),
    ("mart_prevision_tresorerie", "code_filiale", "dim_filiale", "code_filiale"),
    ("mart_qualite_prevision", "code_filiale", "dim_filiale", "code_filiale"),
    ("mart_backtest_journalier", "code_filiale", "dim_filiale", "code_filiale"),
    ("dim_filiale", "code_devise", "dim_devise", "code_devise"),
    ("fct_taux_change", "code_devise", "dim_devise", "code_devise"),
    ("mart_exposition_change", "code_devise", "dim_devise", "code_devise"),
    ("mart_prevision_change", "code_devise", "dim_devise", "code_devise"),
    ("fct_flux_tresorerie_horaire", "code_type", "dim_type_transaction", "code_type"),
    ("mart_stress_test", "code_scenario", "dim_scenario_stress", "code_scenario"),
]

# Paramètres What-if : nom -> (min, max, pas, défaut)
PARAMETRES_WHATIF = {
    "Choc retraits %": (0, 30, 1, 0),
    "Choc change %": (-50, 20, 1, 0),
    "Multiplicateur sorties": (1, 3, 0.1, 1),
    "Choc taux (pb)": (0, 300, 25, 0),
}

TYPES_PG = {
    "integer": "int64", "bigint": "int64", "smallint": "int64",
    "numeric": "double", "double precision": "double", "real": "double",
    "boolean": "boolean", "date": "dateTime",
    "timestamp without time zone": "dateTime", "timestamp with time zone": "dateTime",
    "text": "string", "character varying": "string",
}
# colonnes numériques qu'il ne faut pas additionner (taux, ratios, rangs...)
NON_ADDITIF = re.compile(r"(pct|taux|ratio|volatilite|jours|proba|heure|annee|trimestre|mois|semaine|"
                         r"ordre|step|^id_|choc|multiplicateur|parite|rapport|jour_)")


def gid(*parties: str) -> str:
    """Identifiant stable (même résultat à chaque génération => diffs Git lisibles)."""
    return hashlib.md5("|".join(parties).encode()).hexdigest()[:20]


# ------------------------------------------------------------------- modèle
def lire_colonnes() -> dict[str, list[tuple[str, str]]]:
    with connexion() as cnx:
        lignes = cnx.execute(
            """select table_name, column_name, data_type from information_schema.columns
               where table_schema = 'marts' order by table_name, ordinal_position"""
        ).fetchall()
    colonnes: dict[str, list[tuple[str, str]]] = {}
    for table, col, typ in lignes:
        colonnes.setdefault(table, []).append((col, TYPES_PG[typ]))
    manquantes = [t for t in TABLES if t not in colonnes]
    if manquantes:
        raise SystemExit(f"Tables absentes du schéma marts (lancer le pipeline) : {manquantes}")
    return colonnes


def expression_m(table: str) -> list[str]:
    return [
        "let",
        "    Source = PostgreSQL.Database(ServeurPostgres, BasePostgres),",
        f'    Donnees = Source{{[Schema="marts",Item="{table}"]}}[Data]',
        "in",
        "    Donnees",
    ]


def colonne_tmsl(table: str, nom: str, typ: str) -> dict:
    col = {"name": nom, "dataType": typ, "sourceColumn": nom, "lineageTag": gid(table, nom)}
    if typ in ("int64", "double") and not NON_ADDITIF.search(nom):
        col["summarizeBy"] = "sum"
        col["formatString"] = "#,0"
    else:
        col["summarizeBy"] = "none"
    if typ == "dateTime":
        col["formatString"] = "dd/mm/yyyy hh:nn" if nom == "horodatage" else "dd/mm/yyyy"
    if nom.startswith("id_"):
        col["isHidden"] = True
    return col


def format_mesure(nom: str) -> str | None:
    if nom.startswith("Valeur "):
        return "0.0"
    if nom in ("Recommandation de couverture", "Statut de résilience", "Couleur statut"):
        return None
    if nom == "Date d'arrêté":
        return "dd/mm/yyyy"
    if "jours" in nom.lower() and "(EUR" not in nom:     # avant le test « % » : « Jours avant passage sous 100 % »
        return "0.0"
    if nom.endswith("%"):
        return "0.0 %"
    if nom.startswith("Facteur"):
        return "0.00"
    if nom.startswith("Taux EUR") or nom.startswith("Taux de change"):
        return "0.0000"
    if nom.startswith("Rapport"):
        return "0.00"
    return "#,0"


def lire_mesures_dax() -> list[dict]:
    """Découpe powerbi/mesures_dax.dax en mesures (nom, expression, dossier d'affichage)."""
    mesures, courante, dossier = [], None, "Mesures"
    debut = re.compile(r"^([^\s/][^=]*?)\s=\s?(.*)$")
    for ligne in (DOSSIER_PBI / "mesures_dax.dax").read_text(encoding="utf-8").splitlines():
        section = re.match(r"^// -+ (\d\. .+)$", ligne)
        if section:
            dossier = section.group(1).strip().capitalize()
            courante = None
            continue
        if ligne.startswith("//") or not ligne.strip():
            courante = None if not ligne.strip() else courante
            continue
        m = debut.match(ligne)
        # un nom de mesure ne contient jamais « [ » et ne commence pas par un mot-clé DAX
        est_debut = (m is not None and not ligne.startswith(" ") and "[" not in m.group(1)
                     and not re.match(r"^(VAR|RETURN)\b", m.group(1)))
        if est_debut:
            courante = {"name": m.group(1).strip(), "lignes": [m.group(2)] if m.group(2) else [], "dossier": dossier}
            mesures.append(courante)
        elif courante is not None:
            courante["lignes"].append(ligne)
    resultat = []
    for me in mesures:
        expr = "\n".join(l for l in me["lignes"]).strip()
        mesure = {"name": me["name"], "expression": expr, "displayFolder": me["dossier"],
                  "lineageTag": gid("mesure", me["name"])}
        fmt = format_mesure(me["name"])
        if fmt:
            mesure["formatString"] = fmt
        resultat.append(mesure)
    return resultat


def table_whatif(nom: str, mini, maxi, pas, defaut) -> dict:
    typ = "double" if isinstance(pas, float) else "int64"
    return {
        "name": nom,
        "lineageTag": gid("whatif", nom),
        "columns": [{
            "type": "calculatedTableColumn", "name": nom, "dataType": typ, "isNameInferred": False,
            "isDataTypeInferred": True, "sourceColumn": "[Value]", "summarizeBy": "none",
            "formatString": "0.0" if typ == "double" else "0", "lineageTag": gid("whatif", nom, "col"),
            "extendedProperties": [{"type": "json", "name": "ParameterMetadata", "value": {"version": 0}}],
        }],
        "partitions": [{"name": nom, "mode": "import",
                        "source": {"type": "calculated", "expression": f"GENERATESERIES({mini}, {maxi}, {pas})"}}],
        "measures": [{"name": f"Valeur {nom}", "expression": f"SELECTEDVALUE('{nom}'[{nom}], {defaut})",
                      "formatString": "0.0", "lineageTag": gid("whatif", nom, "mesure")}],
    }


def construire_modele(colonnes: dict) -> dict:
    tables = []
    for t in TABLES:
        table = {
            "name": t, "lineageTag": gid("table", t),
            "columns": [colonne_tmsl(t, c, typ) for c, typ in colonnes[t]],
            "partitions": [{"name": t, "mode": "import", "source": {"type": "m", "expression": expression_m(t)}}],
        }
        if t == "dim_date":
            table["dataCategory"] = "Time"
            for c in table["columns"]:
                if c["name"] == "date_jour":
                    c["isKey"] = True
                if c["name"] == "libelle_mois":
                    c["sortByColumn"] = "mois"
                if c["name"] == "libelle_jour":
                    c["sortByColumn"] = "jour_semaine"
        if t == "dim_filiale":
            for c in table["columns"]:
                if c["name"] == "pays":
                    c["dataCategory"] = "Country"
        tables.append(table)

    tables.append({
        "name": "_Mesures", "lineageTag": gid("table", "_Mesures"),
        "columns": [{"type": "calculatedTableColumn", "name": "Masque", "dataType": "int64", "isHidden": True,
                     "isNameInferred": True, "isDataTypeInferred": True, "sourceColumn": "[Masque]",
                     "summarizeBy": "none", "lineageTag": gid("_Mesures", "Masque")}],
        "partitions": [{"name": "_Mesures", "mode": "import",
                        "source": {"type": "calculated", "expression": 'ROW("Masque", 1)'}}],
        "measures": lire_mesures_dax(),
    })
    for nom, (mini, maxi, pas, defaut) in PARAMETRES_WHATIF.items():
        tables.append(table_whatif(nom, mini, maxi, pas, defaut))
    tables.append({
        "name": "Devises choquées", "lineageTag": gid("table", "Devises choquées"),
        "columns": [{"type": "calculatedTableColumn", "name": "Cible", "dataType": "string",
                     "isNameInferred": True, "isDataTypeInferred": True, "sourceColumn": "[Cible]",
                     "summarizeBy": "none", "lineageTag": gid("Devises choquées", "Cible")}],
        "partitions": [{"name": "Devises choquées", "mode": "import", "source": {
            "type": "calculated",
            "expression": 'DATATABLE ( "Cible", STRING, { { "Toutes devises hors EUR" }, { "USD" }, { "CAD" }, '
                          '{ "Couronnes nordiques" }, { "Franc CFA" } } )'}}],
    })

    noms = {t["name"]: {c["name"] for c in t["columns"]} for t in tables}
    relations = []
    for de_t, de_c, vers_t, vers_c in RELATIONS:
        assert de_c in noms[de_t] and vers_c in noms[vers_t], (de_t, de_c, vers_t, vers_c)
        relations.append({"name": gid("rel", de_t, de_c), "fromTable": de_t, "fromColumn": de_c,
                          "toTable": vers_t, "toColumn": vers_c})

    return {
        "name": NOM,
        "compatibilityLevel": 1567,
        "model": {
            "culture": "fr-FR",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "fr-FR",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "tables": tables,
            "relationships": relations,
            "expressions": [
                {"name": "ServeurPostgres", "kind": "m", "lineageTag": gid("param", "serveur"),
                 "expression": '"localhost:5432" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'},
                {"name": "BasePostgres", "kind": "m", "lineageTag": gid("param", "base"),
                 "expression": '"cresus" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'},
            ],
            "annotations": [{"name": "__PBI_TimeIntelligenceEnabled", "value": "0"},
                            {"name": "PBI_ProTooling", "value": "[\"DevMode\"]"}],
        },
    }


# ------------------------------------------------------------------ rapport
def lit(valeur) -> dict:
    """Littéral PBIR : texte entre apostrophes, booléens/nombres suffixés selon le type."""
    if isinstance(valeur, bool):
        v = "true" if valeur else "false"
    elif isinstance(valeur, (int, float)):
        v = f"{valeur}D"
    else:
        v = "'" + str(valeur).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


def mesure(nom: str, table: str = "_Mesures", libelle: str | None = None) -> dict:
    p = {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": nom}},
         "queryRef": f"{table}.{nom}", "nativeQueryRef": nom}
    if libelle:
        p["displayName"] = libelle
    return p


def colonne(table: str, nom: str, libelle: str | None = None) -> dict:
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": nom}},
         "queryRef": f"{table}.{nom}", "nativeQueryRef": nom}
    if libelle:
        p["displayName"] = libelle
    return p


def somme(table: str, nom: str, libelle: str | None = None) -> dict:
    p = {"field": {"Aggregation": {"Expression": {"Column": {"Expression": {"SourceRef": {"Entity": table}},
                                                              "Property": nom}}, "Function": 0}},
         "queryRef": f"Sum({table}.{nom})", "nativeQueryRef": f"Somme de {nom}"}
    if libelle:
        p["displayName"] = libelle
    return p


def visuel(page: str, idx: int, type_: str, x, y, l, h, titre: str, roles: dict, objets: dict | None = None) -> dict:
    v = {
        "$schema": f"{SCHEMA_URL}/item/report/definition/visualContainer/{V_VISUAL}/schema.json",
        "name": gid(page, str(idx)),
        "position": {"x": x, "y": y, "z": idx * 1000, "width": l, "height": h, "tabOrder": idx * 1000},
        "visual": {
            "visualType": type_,
            "query": {"queryState": {role: {"projections": projs} for role, projs in roles.items()}},
            "visualContainerObjects": {"title": [{"properties": {"show": lit(True), "text": lit(titre)}}]},
            "drillFilterOtherVisuals": True,
        },
    }
    if objets:
        v["visual"]["objects"] = objets
    return v


def carte(page, idx, x, y, nom, titre):
    return visuel(page, idx, "card", x, y, 200, 110, titre, {"Values": [mesure(nom)]},
                  {"labels": [{"properties": {"fontSize": lit(20)}}],
                   "categoryLabels": [{"properties": {"show": lit(False)}}]})


def segment(page, idx, x, y, l, h, champ, titre, unique=False):
    objets = {"data": [{"properties": {"mode": lit("Dropdown")}}]}
    if unique:
        objets["selection"] = [{"properties": {"singleSelect": lit(True)}}]
    return visuel(page, idx, "slicer", x, y, l, h, titre, {"Values": [champ]}, objets)


def pages_rapport() -> list[tuple[str, str, list[dict]]]:
    p = []
    # 1. Cockpit
    n = "p1_cockpit"
    vs = [segment(n, 1, 20, 10, 300, 60, colonne("dim_filiale", "region", "Région"), "Région"),
          segment(n, 2, 340, 10, 300, 60, colonne("dim_filiale", "nom_filiale", "Filiale"), "Filiale")]
    kpis = [("Position de trésorerie (EUR)", "Position de trésorerie"),
            ("Consommation quotidienne de la position %", "Consommation / jour"),
            ("Ratio de couverture liquidité %", "Ratio de liquidité (LCR simplifié)"),
            ("Jours avant passage sous 100 %", "Jours avant 100 % (filiale la plus exposée)"),
            ("Gain annuel de placement (EUR)", "Gain annuel de placement"),
            ("Coût annuel de refinancement (EUR)", "Coût annuel de refinancement"),
            ("VaR change 95 % 10 j (EUR)", "VaR change 95 % 10 j"),
            ("Résultat net de trésorerie annuel (EUR)", "Résultat net de trésorerie / an")]
    for i, (m, t) in enumerate(kpis):
        vs.append(carte(n, 10 + i, 20 + (i % 4) * 310, 80 + (i // 4) * 120, m, t))
    vs.append(visuel(n, 30, "lineChart", 20, 330, 740, 370, "Position de trésorerie par filiale (EUR)",
                     {"Category": [colonne("dim_date", "date_jour", "Date")],
                      "Y": [somme("fct_position_tresorerie_quotidienne", "position_cloture_eur", "Position (EUR)")],
                      "Series": [colonne("dim_filiale", "nom_filiale", "Filiale")]}))
    vs.append(visuel(n, 31, "tableEx", 780, 330, 480, 370, "Liquidité par filiale à la date d'arrêté",
                     {"Values": [colonne("dim_filiale", "nom_filiale", "Filiale"),
                                 mesure("Ratio de couverture liquidité %", libelle="Ratio"),
                                 mesure("Jours avant passage sous 100 %", libelle="Jours avant 100 %"),
                                 mesure("Liquidité excédentaire (EUR)", libelle="Excédent"),
                                 mesure("Besoin de refinancement (EUR)", libelle="Refinancement")]}))
    p.append((n, "Cockpit DAF", vs))

    # 2. Flux
    n = "p2_flux"
    vs = [segment(n, 1, 20, 10, 300, 60, colonne("dim_filiale", "nom_filiale", "Filiale"), "Filiale"),
          carte(n, 2, 340, 10, "Solde net quotidien moyen (EUR)", "Solde net quotidien moyen"),
          carte(n, 3, 560, 10, "Nb opérations", "Nombre d'opérations"),
          carte(n, 4, 780, 10, "Part des gros décaissements %", "Part des gros décaissements (≥ 10 k€)"),
          visuel(n, 10, "clusteredColumnChart", 20, 140, 740, 280, "Encaissements et décaissements par jour (EUR)",
                 {"Category": [colonne("dim_date", "date_jour", "Date")],
                  "Y": [mesure("Encaissements (EUR)"), mesure("Décaissements (EUR)")]}),
          visuel(n, 11, "clusteredColumnChart", 20, 430, 740, 270, "Profil horaire du solde net (EUR)",
                 {"Category": [colonne("fct_flux_tresorerie_horaire", "heure", "Heure")],
                  "Y": [mesure("Solde net (EUR)")]}),
          visuel(n, 12, "clusteredBarChart", 780, 140, 480, 560, "Décaissements par type d'opération (EUR)",
                 {"Category": [colonne("dim_type_transaction", "libelle_type", "Type")],
                  "Y": [mesure("Décaissements (EUR)")]})]
    p.append((n, "Flux de trésorerie", vs))

    # 3. Prévisions
    n = "p3_prevision"
    vs = [segment(n, 1, 20, 10, 300, 60, colonne("dim_filiale", "nom_filiale", "Filiale"), "Filiale"),
          carte(n, 2, 340, 10, "Probabilité de passer sous le besoin de liquidité %", "Probabilité de passer sous 100 % (J+7)"),
          carte(n, 3, 560, 10, "WAPE du modèle champion %", "Erreur du modèle champion (WAPE)"),
          visuel(n, 10, "lineChart", 20, 140, 740, 560, "Position réalisée puis prévue : P5 / P50 / P95 (EUR)",
                 {"Category": [colonne("mart_prevision_tresorerie", "date_jour", "Date")],
                  "Y": [mesure("Position prévue P05 (EUR)", libelle="P5 (pessimiste)"),
                        mesure("Position prévue P50 (EUR)", libelle="P50 (médiane)"),
                        mesure("Position prévue P95 (EUR)", libelle="P95 (optimiste)")]}),
          visuel(n, 11, "tableEx", 780, 140, 480, 330, "Backtest : précision des modèles",
                 {"Values": [colonne("mart_qualite_prevision", "code_filiale", "Filiale"),
                             colonne("mart_qualite_prevision", "serie", "Série"),
                             colonne("mart_qualite_prevision", "modele", "Modèle"),
                             colonne("mart_qualite_prevision", "est_champion", "Champion"),
                             colonne("mart_qualite_prevision", "wape_pct", "WAPE %")]}),
          visuel(n, 12, "clusteredColumnChart", 780, 480, 480, 220, "Réel vs prévu (choisir une filiale)",
                 {"Category": [colonne("mart_backtest_journalier", "date_jour", "Date")],
                  "Y": [somme("mart_backtest_journalier", "reel_devise", "Réel"),
                        somme("mart_backtest_journalier", "prevu_devise", "Prévu")],
                  "Series": [colonne("mart_backtest_journalier", "modele", "Modèle")]})]
    p.append((n, "Prévisions", vs))

    # 4. Change & couverture
    n = "p4_change"
    vs = [segment(n, 1, 20, 10, 300, 60, colonne("dim_devise", "code_devise", "Devise"), "Devise"),
          carte(n, 2, 340, 10, "Exposition au change (EUR)", "Exposition au change"),
          carte(n, 3, 560, 10, "Part de la position en devises %", "Part de la position en devises"),
          carte(n, 4, 780, 10, "VaR change 95 % 10 j (EUR)", "VaR 95 % 10 j"),
          carte(n, 5, 1000, 10, "Coût annuel de couverture de change (EUR)", "Coût annuel si tout est couvert"),
          visuel(n, 10, "lineChart", 20, 140, 620, 560, "Taux de change : historique, fourchette prévue et réalisé",
                 {"Category": [colonne("mart_prevision_change", "date_jour", "Date")],
                  "Y": [mesure("Taux de change prévu P05", libelle="P5"),
                        mesure("Taux de change prévu P50", libelle="P50"),
                        mesure("Taux de change prévu P95", libelle="P95"),
                        mesure("Taux de change réalisé", libelle="Réalisé")]}),
          visuel(n, 11, "tableEx", 660, 140, 600, 300, "Décision de couverture par devise",
                 {"Values": [colonne("dim_devise", "code_devise", "Devise"),
                             mesure("Exposition au change (EUR)", libelle="Exposition"),
                             mesure("VaR change 95 % 10 j (EUR)", libelle="VaR 10 j"),
                             mesure("Rapport coût / risque de la couverture", libelle="Coût / risque"),
                             mesure("Recommandation de couverture", libelle="Recommandation")]}),
          visuel(n, 12, "clusteredBarChart", 660, 450, 600, 250, "Exposition au change par devise (EUR)",
                 {"Category": [colonne("dim_devise", "code_devise", "Devise")],
                  "Y": [mesure("Exposition au change (EUR)")]})]
    p.append((n, "Change & couverture", vs))

    # 5. Simulateur de stress
    n = "p5_stress"
    vs = [segment(n, 1, 20, 10, 240, 60, colonne("Choc retraits %", "Choc retraits %"), "Choc de retraits (% des dépôts)", True),
          segment(n, 2, 270, 10, 240, 60, colonne("Choc change %", "Choc change %"), "Choc de change (%)", True),
          segment(n, 3, 520, 10, 240, 60, colonne("Devises choquées", "Cible"), "Devises choquées", True),
          segment(n, 4, 770, 10, 240, 60, colonne("Multiplicateur sorties", "Multiplicateur sorties"), "Multiplicateur des sorties", True),
          segment(n, 5, 1020, 10, 240, 60, colonne("Choc taux (pb)", "Choc taux (pb)"), "Choc de taux (pb)", True),
          carte(n, 6, 20, 80, "Position stressée (EUR)", "Position stressée"),
          carte(n, 7, 330, 80, "Horizon de survie (jours)", "Horizon de survie (jours)"),
          carte(n, 8, 640, 80, "Besoin de refinancement stressé (EUR)", "Besoin de refinancement"),
          carte(n, 9, 950, 80, "Coût du refinancement stressé (EUR/an)", "Coût du refinancement / an"),
          visuel(n, 10, "tableEx", 20, 200, 560, 500, "Simulation par filiale",
                 {"Values": [colonne("dim_filiale", "nom_filiale", "Filiale"),
                             mesure("Position stressée (EUR)", libelle="Position stressée"),
                             mesure("Horizon de survie (jours)", libelle="Survie (jours)"),
                             mesure("Statut de résilience", libelle="Statut")]}),
          visuel(n, 11, "pivotTable", 600, 200, 660, 500, "Scénarios historiques : horizon de survie (jours)",
                 {"Rows": [colonne("dim_scenario_stress", "libelle_scenario", "Scénario")],
                  "Columns": [colonne("dim_filiale", "code_filiale", "Filiale")],
                  "Values": [somme("mart_stress_test", "horizon_survie_jours", "Jours")]})]
    p.append((n, "Simulateur de stress", vs))

    # 6. Qualité des données
    n = "p6_qualite"
    vs = [carte(n, 1, 20, 10, "Taux de détection actuel %", "Fraudes détectées par le système actuel"),
          carte(n, 2, 240, 10, "Rappel de la règle « vide le compte » %", "Fraudes détectées par la règle « vide le compte »"),
          visuel(n, 10, "clusteredColumnChart", 20, 140, 820, 300, "Transactions par jour de simulation : retenus / exclus",
                 {"Category": [colonne("mart_qualite_donnees", "jour_simulation", "Jour")],
                  "Y": [somme("mart_qualite_donnees", "nb_transactions", "Transactions")],
                  "Series": [colonne("mart_qualite_donnees", "statut", "Statut")]}),
          visuel(n, 11, "clusteredColumnChart", 20, 450, 820, 250, "Fraudes par jour : constantes alors que le volume s'effondre",
                 {"Category": [colonne("mart_qualite_donnees", "jour_simulation", "Jour")],
                  "Y": [somme("mart_qualite_donnees", "nb_fraudes", "Fraudes")]}),
          visuel(n, 12, "tableEx", 860, 140, 400, 560, "Détail par jour",
                 {"Values": [colonne("mart_qualite_donnees", "jour_simulation", "Jour"),
                             colonne("mart_qualite_donnees", "statut", "Statut"),
                             somme("mart_qualite_donnees", "nb_transactions", "Transactions"),
                             colonne("mart_qualite_donnees", "volume_vs_median_pct", "% du volume médian")]})]
    p.append((n, "Qualité des données", vs))
    return p


def ecrire_json(chemin: Path, contenu: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ecrire_projet(sortie: Path, modele: dict, tomtool: Path) -> list[Path]:
    """Écrit le projet complet ; renvoie la liste des fichiers JSON du rapport (pour validation)."""
    if sortie.exists():
        shutil.rmtree(sortie)
    dossier_sm = sortie / f"{NOM}.SemanticModel"
    dossier_rp = sortie / f"{NOM}.Report"

    # --- raccourci .pbip
    ecrire_json(sortie / f"{NOM}.pbip", {
        "$schema": f"{SCHEMA_URL}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NOM}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })

    # --- modèle sémantique : TMSL -> TMDL via la bibliothèque Microsoft
    with tempfile.TemporaryDirectory() as tmp:
        bim = Path(tmp) / "model.bim"
        bim.write_text(json.dumps(modele, ensure_ascii=False, indent=2), encoding="utf-8")
        res = subprocess.run(["dotnet", str(tomtool), str(bim), str(dossier_sm / "definition")],
                             capture_output=True, text=True)
        print(res.stdout.strip())
        if res.returncode != 0:
            raise SystemExit(f"Échec de la conversion TMDL :\n{res.stderr}")
    ecrire_json(dossier_sm / "definition.pbism", {
        "$schema": f"{SCHEMA_URL}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {}})
    ecrire_json(dossier_sm / ".platform", {
        "$schema": f"{SCHEMA_URL}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NOM},
        "config": {"version": "2.0", "logicalId": str(uuid.UUID(gid("logical", "sm") + "000000000000"))}})

    # --- rapport
    fichiers = []
    def rp(chemin_rel: str, contenu: dict):
        chemin = dossier_rp / chemin_rel
        ecrire_json(chemin, contenu)
        fichiers.append(chemin)
    rp("definition.pbir", {
        "$schema": f"{SCHEMA_URL}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NOM}.SemanticModel"}}})
    ecrire_json(dossier_rp / ".platform", {
        "$schema": f"{SCHEMA_URL}/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NOM},
        "config": {"version": "2.0", "logicalId": str(uuid.UUID(gid("logical", "rp") + "000000000000"))}})
    rp("definition/version.json", {
        "$schema": f"{SCHEMA_URL}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"})
    rp("definition/report.json", {
        "$schema": f"{SCHEMA_URL}/item/report/definition/report/{V_REPORT}/schema.json",
        "themeCollection": {"customTheme": {"name": "theme_cresus.json", "reportVersionAtImport": "5.55",
                                            "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": "theme_cresus.json", "path": "theme_cresus.json",
                                         "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True},
    })
    theme = dossier_rp / "StaticResources" / "RegisteredResources" / "theme_cresus.json"
    theme.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(DOSSIER_PBI / "theme_cresus.json", theme)

    pages = pages_rapport()
    rp("definition/pages/pages.json", {
        "$schema": f"{SCHEMA_URL}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [n for n, _, _ in pages], "activePageName": pages[0][0]})
    for nom_page, titre, visuels in pages:
        rp(f"definition/pages/{nom_page}/page.json", {
            "$schema": f"{SCHEMA_URL}/item/report/definition/page/{V_PAGE}/schema.json",
            "name": nom_page, "displayName": titre, "displayOption": "FitToPage",
            "height": 720, "width": 1280})
        for v in visuels:
            rp(f"definition/pages/{nom_page}/visuals/{v['name']}/visual.json", v)
    return fichiers


# --------------------------------------------------------------- validation
def valider_rapport(fichiers: list[Path], dossier_schemas: Path) -> None:
    """Valide chaque fichier JSON du rapport contre le schéma Microsoft qu'il déclare."""
    from jsonschema import Draft7Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7

    base = dossier_schemas / "fabric"
    def charger(uri: str):
        chemin = base / uri.split("/json-schemas/fabric/", 1)[1]
        return Resource.from_contents(json.loads(chemin.read_text(encoding="utf-8")), default_specification=DRAFT7)
    registre = Registry(retrieve=charger)
    erreurs = 0
    for f in fichiers:
        doc = json.loads(f.read_text(encoding="utf-8"))
        schema = charger(doc["$schema"]).contents
        for e in Draft7Validator(schema, registry=registre).iter_errors(doc):
            erreurs += 1
            print(f"  ✗ {f.relative_to(DOSSIER_PBI)} : {e.message[:200]} ({'/'.join(map(str, e.path))})")
    print(f"Validation des schémas Microsoft : {len(fichiers)} fichiers, {erreurs} erreur(s)")
    if erreurs:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tomtool", required=True, type=Path, help="chemin de TomTool.dll (outil .NET)")
    parser.add_argument("--schemas", type=Path, help="clone local de github.com/microsoft/json-schemas")
    args = parser.parse_args()

    modele = construire_modele(lire_colonnes())
    fichiers = ecrire_projet(DOSSIER_PBI / NOM, modele, args.tomtool)
    if args.schemas:
        valider_rapport(fichiers, args.schemas)
    print(f"Projet Power BI écrit dans {DOSSIER_PBI / NOM} : ouvrir {NOM}.pbip avec Power BI Desktop.")


if __name__ == "__main__":
    main()
