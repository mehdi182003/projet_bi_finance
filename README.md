# Projet Crésus — BI prédictive pour la trésorerie de ZF Banque

> **Problématique** : *« Comment l'analyse prédictive et la simulation peuvent-elles être des facteurs de gains dans la gestion de trésorerie d'une banque ? »*
> Étude de cas IBI — Sujet 3 (BI prédictive Finance).

Ce dépôt contient le **POC complet** : une chaîne de données de bout en bout, des sources officielles jusqu'au cockpit Power BI de la Direction Financière, sur **3 ans (2023-2025) et 10 filiales**.

| Brique | Outil | Rôle |
|---|---|---|
| Sources | Fichiers versionnés | **Exports bruts (« sales ») des 4 systèmes bancaires des filiales** sur 2023-2025 (`data/sources_internes/`, 360 fichiers, 2,9 M de lignes) + séries réelles des banques centrales et cours BCE (`data/sources/`) |
| Extract + Load | **Python** (pandas, psycopg) | Chargement tel quel dans la zone brute de PostgreSQL : incrémental, idempotent, tracé (fichier, ligne, MD5) |
| Entrepôt de données | **PostgreSQL 16** | Architecture en couches : `raw` (bronze) → `staging` / `intermediate` (argent) → `marts` (or, schéma en étoile) + `ml` |
| Transform + qualité | **dbt** | Nettoyage (11 règles RG-NET), dédoublonnage, rejets tracés, schéma en étoile, 111 tests (rapprochement comptable, complétude, ancrage sur les dépôts réels), lignage |
| Analyse prédictive | **Python** (statsmodels, numpy) | Champion/challenger au pas quotidien, simulation Monte-Carlo, réserve optimale, contrôle sur des données réelles postérieures |
| Restitution | **Power BI** | Projet `.pbip` prêt à ouvrir : 6 pages, 73 mesures DAX, simulateur What-if |

---

## 1. Architecture

```mermaid
flowchart LR
    subgraph Sources
        F[Exports bruts des filiales<br/>SAB · NORDIC · AMERICORE · DELTA<br/>360 fichiers 2023-2025]
        GL[Soldes comptables<br/>journaliers]
        BC[Banques centrales<br/>dépôts + taux réels]
        W[Webstat<br/>cours BCE]
    end
    subgraph PostgreSQL [PostgreSQL = data warehouse · transformations SQL exécutées par dbt]
        RAW[(raw<br/>bronze)] --> STG[(staging<br/>argent)] --> INT[(intermediate<br/>argent)] --> MARTS[(marts<br/>or : étoile)]
        MARTS --> ML[(ml)] --> MARTS
    end
    F -- Python : load --> RAW
    GL -- Python --> RAW
    BC -- Python --> RAW
    W -- Python --> RAW
    MARTS --> PBI[Power BI]
```

*Le générateur `etl/generateur_flux.py` + `etl/systemes_sources.py` a produit les exports bruts une fois pour toutes, à partir des dépôts réels et de PaySim ; ils sont versionnés. Le pipeline, lui, part de ces fichiers comme d'un vrai SI.*

---

## 2. Démarrage rapide

### Prérequis
- Python 3.10+ ; Docker Desktop (ou PostgreSQL 15/16) ; Power BI Desktop (Windows).
- Un compte Kaggle (gratuit) **ou** le CSV PaySim téléchargé à la main.

### Installation (PowerShell, Windows)
```powershell
git clone <url-du-depot> ; cd claude-cloud
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # puis éditer si besoin (identifiants Kaggle, PostgreSQL)
docker compose up -d            # lance PostgreSQL sur localhost:5432 (base "cresus")
```
*(macOS / Linux : `source .venv/bin/activate` et `cp .env.example .env`.)*

### Données
- **Tout est déjà dans le dépôt** : exports bruts des filiales (`data/sources_internes/`), séries des banques centrales et cours BCE (`data/sources/`). Rien à télécharger.
- **PaySim est facultatif** : il ne sert qu'à la page « Qualité » (et à `--regenerer`). Pour l'avoir : `KAGGLE_USERNAME` / `KAGGLE_KEY` dans `.env`, ou déposer `PS_20174392719_1491204439457_log.csv` dans `data/raw/`.

### Lancement
```powershell
python pipeline.py              # chaîne complète (~3,5 min) : load → dbt (nettoyage, étoile, tests) → prévision
python pipeline.py --etapes dbt prevision dbt_prev   # relancer certaines étapes
```

### Gros volume en local (plusieurs Go, non versionné)
Le jeu versionné regroupe les opérations par **lots de 100** (2,9 M de lignes, 286 Mo). Pour travailler sur un volume réaliste, on génère le même jeu sur son PC avec des lots plus petits. Cela nécessite le CSV PaySim dans `data/raw/`.
```powershell
python pipeline.py --regenerer --taille-lot 10     # ~29 M de lignes, ~3 Go de CSV : génération ~20 min, puis load + dbt
# lancements suivants : ajouter DOSSIER_SOURCES_INTERNES=data/generees/lot_10 dans .env
```
Les fichiers vont dans `data/generees/lot_10/` (ignoré par Git). Les montants, les ancrages et les tests sont identiques quel que soit le lot : seul le nombre de lignes change.

**Reprise du projet** : le contexte complet (décisions, état, reste à faire) est dans [`CLAUDE.md`](CLAUDE.md), chargé automatiquement par Claude Code.
Puis ouvrir **`powerbi/Cresus/Cresus.pbip`** dans Power BI Desktop → *Actualiser* (identifiants PostgreSQL `postgres` / `postgres`). Détails : [docs/04_guide_power_bi.md](docs/04_guide_power_bi.md).

Lignage et dictionnaire de données (idéal en soutenance) : `cd dbt ; dbt docs generate --profiles-dir . ; dbt docs serve --profiles-dir .`

---

## 3. La démarche pas à pas

### Étape 1 — Cadrage AMOA
Les 4 objectifs du sujet sont traduits en questions de pilotage : *quelle sera ma position le mois prochain ? combien je risque sur le change ? où dort de la liquidité, où faut-il se refinancer ? combien de temps tient-on en cas de crise ?* → [docs/01_cadrage_amoa.md](docs/01_cadrage_amoa.md)

### Étape 2 — Sourcing, puis profilage des données
1. **Premier choix** : PaySim (Kaggle) comme proxy des transactions d'une banque de détail, et les cours BCE (Webstat).
2. **Profilage du vrai PaySim** (skill `data:explore-data`). Il révèle des limites rédhibitoires :
   - seuls 12 jours sur 31 ont une activité normale ;
   - la fraude est injectée à rythme constant ;
   - les soldes sont incohérents ;
   - il n'y a pas de flux entrants interbancaires.
   → [docs/06](docs/06_profil_donnees_et_choix_kpi.md)
3. **Décision** : construire **3 ans de données fiables** à partir de **séries réelles publiées par les banques centrales** (dépôts, taux directeurs), en ne gardant de PaySim que la texture des opérations. → [docs/07_donnees_3_ans.md](docs/07_donnees_3_ans.md)

Points d'attention métier relevés au passage :
- le **rouble** n'est plus coté par la BCE depuis le 01/03/2022 (rupture détectée par un test) ;
- les **francs CFA** (XOF pour la Côte d'Ivoire, XAF pour le Cameroun) ont une parité fixe : leur risque est une **dévaluation** (−50 % en 1994), pas la volatilité.

### Étape 3 — Dix filiales ancrées sur la réalité de leur pays
| Filiale | Devise | Dépôts à vue réels utilisés | Part de marché (hypothèse) |
|---|---|---|---|
| France / Benelux / Finlande | EUR | BCE | 1 % / 2 % / 2 % |
| Suède / Danemark / Norvège | SEK / DKK / NOK | SCB / Danmarks Nationalbank / FMI | 1 % chacune |
| Côte d'Ivoire / Cameroun | XOF / XAF | FMI / BEAC | 8 % chacune |
| Canada / États-Unis | CAD / USD | Banque du Canada / Fed (hebdo) | 0,2 % / 0,03 % |

Les opérations de chaque filiale, une fois nettoyées, retombent **exactement** sur les dépôts réels à chaque date publiée : 491 points de contrôle, écart maximal de 0,000007 %, vérifié par un test dbt.

### Étape 4 — ETL et data warehouse (Python → PostgreSQL → dbt)
Les filiales n'ont pas le même système bancaire. On reçoit donc **4 formats d'exports bruts, avec leurs défauts** :

| Système | Filiales | Principales difficultés |
|---|---|---|
| SAB | France, Benelux, Finlande | `;`, cp1252, virgule décimale, sens D/C, libellés français variables, fichiers mensuels qui se chevauchent, opérations annulées |
| NORDIC | Suède, Danemark, Norvège | Heures en UTC, montants signés, öre (centimes) en Suède, extournes |
| AMERICORE | Canada, États-Unis | Dates MM/JJ/AAAA AM/PM, colonnes débit / crédit, séparateur de milliers, comptes de test, zéros de tête perdus |
| DELTA | Côte d'Ivoire, Cameroun | Ligne de titre et ligne de total, dates aaaammjj, libellés sans norme, « FCFA » au lieu du code ISO |

1. **Load (Python)** : chaque fichier est déposé **tel quel en texte** dans `raw` (bronze), avec fichier, ligne et date de chargement. Le chargement est incrémental et idempotent (empreinte MD5).
2. **Staging (dbt)** : un modèle par système (typage, formats, fuseaux, unités, sens).
3. **Intermediate (dbt)** : union des 4 systèmes, correspondances de libellés et de devises, dédoublonnage, exclusions, identifiants clients, et **table des rejets avec motif** (rien n'est supprimé en silence).
4. **Marts (dbt)** : **schéma en étoile** (dimensions conformes, faits au grain documenté, fait principal incrémental), puis marts d'analyse.
5. **Contrôles** : complétude des fichiers, **rapprochement comptable jour par jour**, ancrage sur les dépôts réels. Résultat : 2 896 020 lignes brutes → 2 788 404 opérations retenues (3,7 % écartées), **exactement** le nombre d'opérations réelles de chaque filiale.

→ [docs/08_etl_sources_et_nettoyage.md](docs/08_etl_sources_et_nettoyage.md) (dictionnaire des sources, règles RG-NET, modèle dimensionnel) · [docs/02_specifications_moe.md](docs/02_specifications_moe.md)

### Étape 5 — Choix des KPI à partir des données
Chaque KPI a été **testé statistiquement**. On n'a gardé que ceux qui varient, sont mesurés, résistent aux artefacts et éclairent une décision. → [docs/06](docs/06_profil_donnees_et_choix_kpi.md)

| KPI retenu | Décision éclairée |
|---|---|
| Position de trésorerie, solde net, encaissements et décaissements | Pilotage quotidien |
| **Ratio de liquidité** (Bâle III simplifié : position / 10 % des dépôts) et **jours sous 100 %** | Conformité ; janvier concentre 40 % des jours sous 100 % |
| **Opérations de trésorerie** : refinancement levé / excédent placé | Combien emprunter ou placer chaque mois |
| **Réserve requise à 99 %** (prévision) vs réserve actuelle | Où libérer de la liquidité, où en lever |
| Prévision P5 / P50 / P95 et probabilité de passer sous 100 % | Anticipation |
| Exposition, **VaR 95 % 10 j**, **effet de change** (−57 M€ sur l'USD en 3 ans) | Risque de change |
| **Rapport coût / risque de la couverture** et recommandation par devise | Quelles devises couvrir |
| Horizon de survie sous stress | Résilience (7 scénarios historiques + simulateur) |
| Part des gros décaissements | Pré-notification des gros retraits |

KPI **écartés après analyse** :
- l'ancien ratio de liquidité (double comptage) ;
- le taux de netting (simple reflet d'une hypothèse) ;
- le taux de fraude dans le temps (artefact) ;
- le pic intrajournalier (redondant).

### Étape 6 — Analyse prédictive et simulation
- **Trois modèles en concurrence** au pas quotidien : naïf hebdomadaire, Holt-Winters, régression calendaire. Cette dernière utilise les jours ouvrés et fériés, le début et la fin de mois, et le **mois de l'année** ; elle gagne sur 19 séries sur 20. Erreur journalière (WAPE) : 12 à 16 % sur les décaissements, 12 à 23 % sur les encaissements, contre 46 % pour le naïf sur les encaissements.
- **Monte-Carlo** : 1 000 trajectoires pour janvier 2026 (erreurs du backtest rééchantillonnées par blocs, plus un choc mensuel).
- **Contrôle sur données réelles postérieures** : les dépôts de janvier 2026, publiés après la date d'arrêté, tombent dans la fourchette à 90 % pour 7 filiales sur 9 (erreur médiane de −3,7 % à +2,0 %). La fourchette de change contient le cours réel 94 % des jours.
- **Ce que le contrôle a appris** : la première version ignorait la **baisse saisonnière des dépôts en janvier** (−3,4 % en France en moyenne), d'où une fourchette trop étroite (4 filiales sur 9). Ajouter l'effet « mois » et un choc mensuel l'a corrigée.

→ [docs/03_analyse_predictive_et_simulation.md](docs/03_analyse_predictive_et_simulation.md)

### Étape 7 — Restitution Power BI
`powerbi/Cresus/Cresus.pbip`, prêt à ouvrir, compte 6 pages : Cockpit DAF · Flux · Prévisions · Change & couverture · Simulateur de stress · Qualité des données.
- Le modèle (26 tables, 73 mesures) est validé et converti par la bibliothèque officielle Microsoft (TOM).
- Les 69 fichiers du rapport respectent les schémas JSON Microsoft.

→ [docs/04_guide_power_bi.md](docs/04_guide_power_bi.md)

### Étape 8 — Synthèse, SWOT et recommandations
→ [docs/05_synthese_swot_recommandations.md](docs/05_synthese_swot_recommandations.md)

---

## 4. Modèle en étoile (schéma `marts`)

```mermaid
erDiagram
    dim_date ||--o{ fct_flux_tresorerie_horaire : date_operation
    dim_date ||--o{ fct_position_tresorerie_quotidienne : date_position
    dim_date ||--o{ fct_taux_change : date_cours
    dim_filiale ||--o{ fct_flux_tresorerie_horaire : code_filiale
    dim_filiale ||--o{ fct_position_tresorerie_quotidienne : code_filiale
    dim_filiale ||--o{ mart_liquidite_placement : code_filiale
    dim_filiale ||--o{ mart_stress_test : code_filiale
    dim_filiale ||--o{ mart_prevision_tresorerie : code_filiale
    dim_filiale ||--o{ mart_reserve_optimale : code_filiale
    dim_filiale ||--o{ mart_qualite_ancrage : code_filiale
    dim_devise ||--o{ dim_filiale : code_devise
    dim_devise ||--o{ fct_taux_change : code_devise
    dim_devise ||--o{ mart_exposition_change : code_devise
    dim_type_transaction ||--o{ fct_flux_tresorerie_horaire : code_type
    dim_scenario_stress ||--o{ mart_stress_test : code_scenario
```

## 5. Structure du dépôt

```
├── pipeline.py                 orchestrateur (extract → générer → load → dbt → prévision → dbt)
├── etl/
│   ├── chargement_sources_internes.py  load des exports bruts dans raw (incrémental, idempotent)
│   ├── sources_reelles.py      dépôts et taux directeurs réels (API des banques centrales)
│   ├── generateur_flux.py      « vérité » 2023-2025 ancrée sur les dépôts réels (pour --regenerer)
│   ├── systemes_sources.py     écrit les exports bruts des 4 systèmes, avec leurs défauts
│   ├── prevision.py            champion/challenger, Monte-Carlo, réserve optimale, change
│   ├── controle_a_posteriori.py prévision vs dépôts réels publiés ensuite (janvier 2026)
│   ├── extraction_paysim.py / extraction_bce.py / chargement_raw.py
│   └── donnees_demo.py         transactions synthétiques au format PaySim (tests hors Kaggle)
├── data/sources_internes/      exports bruts des filiales (SAB, NORDIC, AMERICORE, DELTA) + soldes comptables
├── data/sources/               séries réelles des banques centrales, cours BCE (versionnées)
├── dbt/                        seeds (référentiels), staging, intermediate, marts, tests, macros
├── powerbi/Cresus/             projet Power BI prêt à ouvrir (Cresus.pbip)
├── powerbi/                    générateur du projet, mesures DAX, thème, outil .NET TomTool
└── docs/                       livrables AMOA / MOE (01 à 08)
```

## 6. Hypothèses et limites (à assumer en soutenance)
- **Les transactions individuelles et leurs exports bruts sont simulés** (aucune banque ne publie les siennes) ; les défauts des exports sont injectés volontairement et documentés (docs/08). Sont réels : les niveaux de dépôts (mensuels, hebdomadaires aux États-Unis), les taux directeurs, le change et les jours fériés.
- **Le profil à l'intérieur du mois et les parts de marché sont des hypothèses documentées.** La précision journalière du modèle en découle en partie ; le contrôle sur janvier 2026 réel, lui, n'en dépend pas.
- **Le LCR est simplifié** : un seul taux de fuite de 10 %, pas de pondération des actifs liquides.
- **Cameroun** : 10 mois interpolés. **BCEAO** : le taux de décembre 2022 est déduit (marqué `a_verifier`).
- **Prévision du groupe** : c'est la somme des quantiles des filiales, une borne prudente.
