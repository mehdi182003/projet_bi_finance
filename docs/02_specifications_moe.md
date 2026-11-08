# 02 — Spécifications MOE

## 1. Architecture technique

| Couche | Schéma PostgreSQL | Matérialisation | Responsable |
|---|---|---|---|
| Brute (bronze) | `raw` | tables en texte (COPY), chargement incrémental par fichier | Python `etl/chargement_sources_internes.py`, `etl/chargement_raw.py` |
| Référentiels | `referentiel` | tables (dbt seed) | dbt `seeds/` |
| Nettoyage par système source (silver) | `staging` | vues | dbt `models/staging` (`stg_sab__`, `stg_nordic__`, `stg_americore__`, `stg_delta__operations`) |
| Union, dédoublonnage, rejets, règles métier (silver) | `intermediate` | vues / tables | dbt `models/intermediate` |
| Restitution : schéma en étoile (gold) | `marts` | tables (fait principal incrémental) | dbt `models/marts` |
| Prédictif | `ml` | tables | Python `etl/prevision.py` |

Ordonnancement (`pipeline.py`) : `extract → load → dbt build (hors prévision) → prévision Python → dbt build (tag prevision)`.
Le pipeline est **rejouable** : un fichier inchangé est ignoré (empreinte MD5), un fichier modifié est rechargé, un fichier absent du dossier actif est retiré de `raw`. Durée mesurée : ~6 min pour le jeu versionné (4,3 M de lignes brutes), ~1 h 10 pour le gros volume (42,7 M de lignes).

## 2. Règles de gestion

Les règles de **nettoyage des exports bruts** (RG-NET-01 à 11), le dictionnaire des 4 systèmes sources et la description du modèle dimensionnel (grain, additivité) sont détaillés dans [docs/08_etl_sources_et_nettoyage.md](08_etl_sources_et_nettoyage.md). Les règles **métier** sont ci-dessous.


| Code | Règle | Modèle |
|---|---|---|
| RG-CHG-01 | EUR = 1 (devise de consolidation) | `int_taux_change_journalier` |
| RG-CHG-02 | XOF / XAF = parité fixe 655,957 | idem |
| RG-CHG-03 | Jour sans cotation → dernier cours publié (au plus 7 jours) | idem |
| RG-CHG-04 | Au-delà de 7 jours → NULL = rupture de série (RUB) | idem |
| RG-GEN-01 | Flux 2023-2025 générés par filiale ; leur cumul égale l'encours réel publié (banque centrale) × part de marché à chaque date de publication | `etl/generateur_flux.py`, test `assert_ancrage_depots_reels` |
| RG-VOL-01 | Une ligne = `poids` opérations (échantillon pondéré) : montant total = montant unitaire × poids | `int_mouvements_tresorerie` |
| RG-VAL-02 | Contre-valeur EUR = montant devise / cours BCE du jour | idem |
| RG-SEN-01 | CASH_IN = +1 ; CASH_OUT, DEBIT, PAYMENT, TRANSFER (émetteur) = −1 | `ref_types_transaction` |
| RG-QUA-01 | Transactions de montant nul exclues | idem |
| RG-QUA-02 | Seule la fenêtre d'activité stable de PaySim (steps 121 à 408 = jours 6 à 17) sert de « texture » | `etl/generateur_flux.py` |
| RG-POS-01 (v2) | Encours initial = encours réel au 31/12/2022 × part de marché (la v1 utilisait les soldes PaySim, jugés peu fiables) | `int_encours_initial` |
| RG-POS-02 | Réserve initiale = encours × taux de réserve de la filiale | idem |
| RG-POS-04 | Encours de dépôts = encours initial + cumul des flux nets | `fct_position_tresorerie_quotidienne` |
| RG-POS-06 | Trésorerie gérée : au 1er du mois, la réserve est ramenée à sa cible (taux de réserve × dépôts de fin de mois précédent) ; dans le mois, position = cible + cumul des flux du mois | idem |
| RG-POS-07 | Opération de trésorerie de fin de mois = cible du mois suivant − position de clôture (> 0 : refinancement ; < 0 : placement) | idem |
| RG-POS-05 | Position EUR réévaluée chaque jour ; effet de change = écart avec le cours du 1er jour | idem |
| RG-RIS-01 | Volatilité = écart-type des 60 dernières variations publiées × √252 | `fct_taux_change` |
| RG-RIS-02/03 | VaR 95 % = 1,645 × vol. quotidienne × exposition ; 10 j = × √10 | `mart_exposition_change` |
| RG-LIQ-01 (v2) | Besoin 30 j = 10 % des dépôts (Bâle III). La v1 y ajoutait la tendance des flux : double comptage, ratio figé sous 100 % | `mart_liquidite_placement` |
| RG-LIQ-02..04 | Ratio = position / besoin ; excédent / déficit par rapport à la cible de pilotage de 110 % → gain au taux directeur / coût au taux + 0,5 pt | idem |
| RG-LIQ-05 | Consommation quotidienne = − flux net moyen 30 j / position | idem |
| RG-LIQ-06 | Jours avant 100 % = (position − besoin) / sortie nette moyenne | idem |
| RG-COU-02 | Rapport coût / risque de la couverture = (taux local − taux BCE) / volatilité ; recommandation par devise | `mart_exposition_change` |
| RG-COU-01 | Coût de couverture ≈ exposition × (taux local − taux BCE) (parité des taux d'intérêt) | idem |
| RG-STR-01..05 | Chocs de change, de retraits, de sorties et de taux → horizon de survie | `mart_stress_test` |
| RG-MOD-01 | Une dimension décrit le contexte (qui, quoi, quand, où) et ne porte aucune mesure ; les nombres sont dans les tables de faits | `dim_*`, test `assert_dimensions_sans_mesure` |
| RG-PRV-01 | Projection convertie en EUR au cours d'arrêté (change constant) | `mart_prevision_tresorerie` |

Toutes les hypothèses numériques sont des **variables dbt** (`dbt_project.yml`) ou des **seeds CSV** : on les modifie sans toucher au code.

## 3. Dictionnaire des principales tables (`marts`)

Dictionnaire complet, une ligne par colonne (52 tables, 627 colonnes) : `livrables/05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_BI-predictive-Finance_G5.xlsx` (`python docs/dictionnaire/generer_dictionnaire.py`).

### Dimensions : le contexte (qui, quoi, quand, où), sans aucune mesure (RG-MOD-01)
`dim_date` (quand), `dim_filiale` (qui, où : identité, pays, région, devise, système source, fuseau horaire, source des dépôts), `dim_devise` (quelle monnaie), `dim_type_transaction` (quelle opération), `dim_scenario_stress` (quelle crise : nom, crise de référence).

### fct_flux_tresorerie_horaire — grain : heure × filiale × type × fraude × gros ticket
| Colonne | Description |
|---|---|
| horodatage, date_operation, heure | Moment de l'opération |
| code_filiale, code_devise, code_type | Clés vers les dimensions |
| est_fraude, est_gros_ticket | Indicateurs (fraude ; opération ≥ 10 k€) |
| nb_mouvements | Nombre d'opérations |
| encaissements_*, decaissements_* | Montants bruts (positifs), en devise et en EUR |
| flux_net_devise, flux_net_eur | Encaissements − décaissements |

### fct_position_tresorerie_quotidienne — grain : jour × filiale (semi-additive)
Flux du jour, `cible_reserve_mois_devise`, `position_ouverture_devise`, `position_cloture_devise`, `operation_tresorerie_devise/_eur` (fin de mois), `encours_reel_publie_devise`, `position_cloture_eur`, `position_cloture_eur_taux_constant`, `effet_change_eur`, `encours_depots_*`, `taux_eur_jour`, `decaissements_frauduleux_eur`, `decaissements_gros_tickets_eur`.

### fct_taux_change — grain : jour × devise
`taux_eur` (unités pour 1 €), `valeur_eur_par_unite`, `est_taux_publie`, `jours_depuis_publication`, `variation_jour_pct`, `volatilite_annualisee_pct`, `est_rupture_serie`.

### fct_situation_initiale_filiale — grain : filiale au 31/12/2022
`part_de_marche_depots_pct`, `taux_reserve_liquidite_pct`, `nb_clients`, `taux_eur_reference`, `encours_depots_initial_devise/_eur`, `reserve_liquidite_initiale_devise/_eur`. Ces nombres étaient dans `dim_filiale` avant la revue du 05/11/2026.

### Faits dérivés (`mart_`)
Ce sont aussi des tables de faits : `mart_exposition_change` (jour × devise), `mart_liquidite_placement` (jour × filiale), `mart_stress_test` (scénario × filiale), `mart_qualite_ancrage` (réel publié vs reconstitué), `mart_prevision_tresorerie`, `mart_prevision_change`, `mart_backtest_journalier`, `mart_reserve_optimale` (réserve requise P99), `mart_controle_a_posteriori` (prévision vs dépôts réels de janvier 2026).

Le graphe de lineage s'obtient avec `dbt docs generate && dbt docs serve`.

## 4. Plan de tests (104 tests dbt)

| Famille | Exemples |
|---|---|
| Structure | `unique` / `not_null` sur toutes les clés |
| Intégrité référentielle | faits → `dim_date`, `dim_filiale`, `dim_type_transaction` |
| Domaines de valeurs | types d'opération, sens ±1, statuts de résilience, bornes des montants |
| ETL | complétude des fichiers (lignes et totaux de contrôle) ; **rapprochement comptable jour par jour** (10 960 jours-filiales) ; unicité des opérations nettoyées ; alerte sur rejets inattendus |
| Métier | **ancrage : encours reconstitué = encours réel publié à chaque date (481 dates contrôlées)** ; conservation des volumes (aucune ligne perdue) ; taux disponibles sur toute la période |
| Restitution | faits incrémentaux à jour par rapport à leur source (`assert_fct_flux_a_jour`) ; aucune colonne `numeric` dans les marts, que Power BI ne saurait pas lire (`assert_marts_sans_numeric`) |
| Alertes (non bloquantes) | rupture de série de change (RUB) ; vraisemblance de l'encours (décaissements / dépôts entre 0,05 % et 5 % par jour) ; fraîcheur des cours BCE (> 10 jours) |
