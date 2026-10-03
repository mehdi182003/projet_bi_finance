# 01 — Cadrage AMOA

## 1. Contexte
ZF Banque est un groupe de banques de détail : une dizaine de filiales, plus de 2 800 agences et environ 5 000 collaborateurs, présentes en France métropolitaine, en Europe du Nord, en Afrique (Côte d'Ivoire, Cameroun) et en Amérique du Nord (Canada, États-Unis). Le plan quinquennal du nouveau Directeur Général (M. PAUL) lance le projet **Crésus** (octobre 2017) : moderniser les outils de gestion de la trésorerie du groupe. Le Directeur Financier (M. LETANG) nous mandate pour étudier l'opportunité d'un outil d'**analyse prédictive**.

## 2. Besoin exprimé → questions de pilotage

| # | Objectif du sujet | Question de pilotage | Indicateur(s) | Table dbt |
|---|---|---|---|---|
| O1 | Anticiper les entrées/sorties de cash par devise et par filiale | Quelle sera ma position à J+7 et avec quelle incertitude ? | Solde net quotidien, position P5/P50/P95, probabilité de passer sous le besoin | `fct_position_tresorerie_quotidienne`, `mart_prevision_tresorerie` |
| O2 | Stratégie de couverture selon des scénarios de change | Quelle perte possible sur mes devises ? Que coûte la couverture ? | Exposition, VaR 95 % 10 j, fourchette de change, coût de couverture | `mart_exposition_change`, `mart_prevision_change`, `mart_liquidite_placement` |
| O3 | Optimiser refinancement et placement | Où dort de la liquidité ? Où faut-il se refinancer ? | Ratio de couverture, liquidité excédentaire, gain de placement, coût de refinancement | `mart_liquidite_placement` |
| O4 | Scénarios de stress à partir de données réelles | Combien de temps chaque filiale tient-elle en cas de crise ? | Position stressée, horizon de survie, statut | `mart_stress_test` + simulateur Power BI |

Enjeux transverses : **hétérogénéité** des données (10 filiales, 8 devises, 3 régimes de change) et **intégration de données externes** (cours BCE, taux directeurs).

## 3. Périmètre du POC

| Dimension | Périmètre retenu |
|---|---|
| Filiales | 10 : France, Benelux, Finlande, Suède, Danemark, Norvège, Côte d'Ivoire, Cameroun, Canada, États-Unis |
| Devises de filiales | EUR, SEK, DKK, NOK, XOF, XAF, CAD, USD |
| Devises de surveillance | JPY, RUB (citées par le sujet) |
| Période rejouée | 743 heures à partir du 01/09/2025 (variable dbt `date_debut_paysim`) |
| Horizon de prévision | 7 jours pour les flux, 30 jours pour le change |
| Hors périmètre | Crédits, titres, dérivés ; données nominatives (RGPD) |

**Remarque d'expert** : la Côte d'Ivoire utilise le **franc CFA de l'UEMOA (XOF, BCEAO)**, et non le XAF, qui est celui de la CEMAC (Cameroun, BEAC). Les deux ont la même parité fixe (655,957 XOF ou XAF pour 1 €), mais deux banques centrales et deux taux directeurs différents.

## 4. Recensement et validation des sources (webographie)

| Source | Type | Contenu | Accès | Qualité / limites | Décision |
|---|---|---|---|---|---|
| Kaggle — PaySim (ealaxi/paysim1) | Interne (proxy) | 6,36 M de transactions mobiles simulées, 743 h, 11 colonnes | CSV, compte Kaggle gratuit | Synthétique ; volume qui chute après ~400 h ; 1 seul mois | **Retenue** comme proxy des flux de la banque de détail |
| Banque de France — Webstat (série EXR, cours BCE) | Externe | Cours de référence quotidiens, 30 devises, 1999-2026 | Export CSV gratuit | Officiel ; pas de cotation le week-end ; RUB arrêté au 01/03/2022 ; pas de XOF/XAF | **Retenue** |
| BCE — eurofxref-hist.zip | Externe | Même contenu que Webstat | Téléchargement direct | Idem | Retenue en **secours** (code prévu) |
| Banques centrales (BCE, Fed, BdC, Riksbank, Norges Bank, Danmarks Nationalbank, BCEAO, BEAC) | Externe | Taux directeurs | Sites officiels | Saisie manuelle, à mettre à jour | **Retenue** (seed `ref_taux_directeurs`) |
| EBA — EU-wide Transparency Exercise | Externe | Bilans et liquidité de banques européennes | XLSX | Données annuelles agrégées, pas de flux | Écartée pour le POC ; utile pour calibrer les taux de réserve |
| Benchmark DAF-Mag 2026 | Marché | Comparatif des plateformes BI et EPM | Article | Qualitatif | Utilisée pour le choix d'outils |

## 5. Choix des outils (benchmark simplifié)

| Critère | Power BI | Tableau | dbt + PostgreSQL | Talend |
|---|---|---|---|---|
| Coût POC | Gratuit (Desktop) | Licence | Gratuit (open source) | Version libre arrêtée |
| Simulation What-if | Paramètres natifs + DAX | Paramètres | — | — |
| Transformations versionnées et testées | Power Query (peu testable) | Prep | **Oui (SQL + Git + tests)** | Graphique |
| Intégration au SI Microsoft d'une banque | **Forte** | Moyenne | — | — |

Choix : **Python + PostgreSQL + dbt + Power BI**. NB : la fiche d'expertise mentionne Tableau à l'étape 5 ; il faut la mettre à jour pour Power BI.

## 6. Prérequis identifiés
1. **Données** : historique de flux d'au moins 2 ans par filiale (saisonnalités de fin de mois et annuelles) ; référentiel unique des filiales, devises et comptes.
2. **Qualité** : contrôles automatisés (dbt tests) ; un propriétaire métier (*data owner*) par source ; règles de gestion documentées et validées par la Trésorerie.
3. **Technique** : entrepôt central, ordonnanceur (cron, Airflow, dbt Cloud), flux de marché quotidiens.
4. **Organisation** : un sponsor à la DAF, des trésoriers formés à lire des intervalles de confiance (et pas seulement un chiffre).
