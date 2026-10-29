# 02 — Spécifications MOE

## 1. Architecture technique

| Couche | Schéma PostgreSQL | Matérialisation | Responsable |
|---|---|---|---|
| Brute | `raw` | tables (COPY) | Python `etl/chargement_raw.py` |
| Référentiels | `referentiel` | tables (dbt seed) | dbt `seeds/` |
| Nettoyage | `staging` | vues | dbt `models/staging` |
| Règles métier | `intermediate` | vues / tables | dbt `models/intermediate` |
| Restitution | `marts` | tables | dbt `models/marts` |
| Prédictif | `ml` | tables | Python `etl/prevision.py` |

Ordonnancement (`pipeline.py`) : `extract → load → dbt build (hors prévision) → prévision Python → dbt build (tag prevision)`.
Le pipeline est **rejouable** : les tables brutes sont vidées puis rechargées, et dbt reconstruit tout. Durée mesurée : environ 3 min pour 6,4 M de lignes.

## 2. Règles de gestion

| Code | Règle | Modèle |
|---|---|---|
| RG-CHG-01 | EUR = 1 (devise de consolidation) | `int_taux_change_journalier` |
| RG-CHG-02 | XOF / XAF = parité fixe 655,957 | idem |
| RG-CHG-03 | Jour sans cotation → dernier cours publié (au plus 7 jours) | idem |
| RG-CHG-04 | Au-delà de 7 jours → NULL = rupture de série (RUB) | idem |
| RG-AFF-01 | Client → filiale par hachage déterministe, au prorata des poids | `int_mouvements_tresorerie` |
| RG-AFF-02 | Bénéficiaire d'un virement : même filiale à 85 %, sinon filiale tirée au prorata | idem |
| RG-VAL-01 | Montant devise = montant PaySim × 0,01 € × cours du 1er jour | idem |
| RG-VAL-02 | Contre-valeur EUR = montant devise / cours BCE du jour | idem |
| RG-SEN-01 | CASH_IN = +1 ; CASH_OUT, DEBIT, PAYMENT, TRANSFER (émetteur) = −1 | `ref_types_transaction` |
| RG-SEN-02 | Un virement intragroupe génère 2 jambes (débit émetteur, crédit bénéficiaire) | `int_mouvements_tresorerie` |
| RG-SEN-03 | Un virement interne à une filiale est neutre → exclu | idem |
| RG-QUA-01 | Transactions de montant nul exclues | idem |
| RG-QUA-02 | Seule la fenêtre d'activité stable (steps 121 à 408 = jours 6 à 17) est retenue | `stg_paysim__transactions` (drapeau), `int_*` (filtre) |
| RG-POS-01 | Encours initial = somme des soldes d'ouverture des clients à leur 1ʳᵉ apparition | `int_encours_initial` |
| RG-POS-02 | Réserve initiale = encours × taux de réserve de la filiale | idem |
| RG-POS-03/04 | Position et encours = valeur initiale + cumul des flux nets | `fct_position_tresorerie_quotidienne` |
| RG-POS-05 | Position EUR réévaluée chaque jour ; effet de change = écart avec le cours du 1er jour | idem |
| RG-RIS-01 | Volatilité = écart-type des 60 dernières variations publiées × √252 | `fct_taux_change` |
| RG-RIS-02/03 | VaR 95 % = 1,645 × vol. quotidienne × exposition ; 10 j = × √10 | `mart_exposition_change` |
| RG-LIQ-01 (v2) | Besoin 30 j = 10 % des dépôts (Bâle III). La v1 y ajoutait la tendance des flux : double comptage, ratio figé sous 100 % | `mart_liquidite_placement` |
| RG-LIQ-02..04 | Ratio = position / besoin ; excédent / déficit par rapport à la cible de pilotage de 110 % → gain au taux directeur / coût au taux + 0,5 pt | idem |
| RG-LIQ-05 | Consommation quotidienne = − flux net moyen 7 j / position | idem |
| RG-LIQ-06 | Jours avant 100 % = (position − besoin) / sortie nette moyenne | idem |
| RG-COU-02 | Rapport coût / risque de la couverture = (taux local − taux BCE) / volatilité ; recommandation par devise | `mart_exposition_change` |
| RG-COU-01 | Coût de couverture ≈ exposition × (taux local − taux BCE) (parité des taux d'intérêt) | idem |
| RG-STR-01..05 | Chocs de change, de retraits, de sorties et de taux → horizon de survie | `mart_stress_test` |
| RG-PRV-01 | Projection convertie en EUR au cours d'arrêté (change constant) | `mart_prevision_tresorerie` |

Toutes les hypothèses numériques sont des **variables dbt** (`dbt_project.yml`) ou des **seeds CSV** : on les modifie sans toucher au code.

## 3. Dictionnaire des principales tables (`marts`)

### fct_flux_tresorerie_horaire — grain : heure × filiale × type × jambe × intragroupe × fraude
| Colonne | Description |
|---|---|
| horodatage, date_operation, heure | Moment de l'opération |
| code_filiale, code_devise, code_type | Clés vers les dimensions |
| role_jambe | EMETTEUR / BENEFICIAIRE |
| est_intragroupe, est_fraude | Indicateurs |
| nb_mouvements | Nombre d'opérations |
| encaissements_*, decaissements_* | Montants bruts (positifs), en devise et en EUR |
| flux_net_devise, flux_net_eur | Encaissements − décaissements |

### fct_position_tresorerie_quotidienne — grain : jour × filiale (semi-additive)
Flux du jour, `position_ouverture_devise`, `position_cloture_devise`, `position_cloture_eur`, `position_cloture_eur_taux_constant`, `effet_change_eur`, `encours_depots_*`, `taux_eur_jour`, `decaissements_frauduleux_eur`, `flux_net_intragroupe_eur`.

### fct_taux_change — grain : jour × devise
`taux_eur` (unités pour 1 €), `valeur_eur_par_unite`, `est_taux_publie`, `jours_depuis_publication`, `variation_jour_pct`, `volatilite_annualisee_pct`, `est_rupture_serie`.

### Tables d'analyse
`mart_exposition_change` (jour × devise), `mart_liquidite_placement` (jour × filiale), `mart_stress_test` (scénario × filiale), `mart_prevision_tresorerie`, `mart_prevision_change`, `mart_qualite_prevision`, `mart_backtest_journalier`.

Le dictionnaire complet et le graphe de lignage s'obtiennent avec `dbt docs generate && dbt docs serve`.

## 4. Plan de tests (78 tests dbt)

| Famille | Exemples |
|---|---|
| Structure | `unique` / `not_null` sur toutes les clés |
| Intégrité référentielle | faits → `dim_date`, `dim_filiale`, `dim_type_transaction` |
| Domaines de valeurs | types PaySim, sens ±1, statuts de résilience, bornes du step et des montants |
| Métier | somme des poids = 100 % ; conservation des volumes (aucune transaction perdue) ; flux intragroupe équilibrés chaque jour ; taux disponibles sur toute la période |
| Alertes (non bloquantes) | rupture de série de change (RUB) ; jour atypique dans la fenêtre d'analyse ; vraisemblance de l'encours (décaissements / dépôts entre 0,05 % et 5 % par jour) ; fraîcheur des cours BCE (> 10 jours) |
