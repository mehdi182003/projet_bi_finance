# Partie 5 : modèle en étoile et Power BI

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **comment les données propres deviennent un modèle lisible par Power BI**, et **comment le rapport calcule et affiche les KPI**. Tu maîtrises le schéma en étoile (dimensions, faits, grain, additivité), le calcul de la position et du ratio de liquidité, le dictionnaire Excel, le modèle Power BI et les mesures DAX. La partie 3 explique comment Power BI se branche sur la base : import, actualisation, sécurité par filiale. C'est aussi la partie qui a été revue après la remarque du prof sur les dimensions et les faits.

**Diapo :** 12 (arbitrer : le cockpit). Tu fais la démonstration de Power BI.

**Fichiers :** `dbt/models/marts/dimensions/`, `dbt/models/marts/faits/`, `dbt/models/marts/analyses/mart_liquidite_placement.sql`, `dbt/models/marts/schema.yml`, `dbt/tests/assert_dimensions_sans_mesure.sql`, `docs/dictionnaire/`, `livrables/05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_…xlsx`, `powerbi/mesures_dax.dax`, `powerbi/Cresus/`, `powerbi/generer_pbip.py`.

## À savoir dire en une minute

> Le schéma `marts` suit une modélisation en étoile, à la Kimball. Il a 5 dimensions qui décrivent le contexte : quand (la date), qui et où (la filiale), quoi (la devise, le type d'opération, le scénario de crise). Il a 15 tables de faits qui contiennent les chiffres : combien. Chaque table a un grain documenté, c'est-à-dire ce que représente une ligne, par exemple un jour et une filiale. Après la remarque du prof, plus aucune dimension ne contient de montant, et un test dbt l'empêche. La position de trésorerie est un stock : on lit le dernier jour, on ne l'additionne jamais dans le temps. Dans Power BI, chaque KPI est écrit une seule fois en DAX, puis repris par tous les visuels.

## 1. Les notions à maîtriser

### Modélisation dimensionnelle

| Notion | En clair | Exemple |
|---|---|---|
| **Dimension** | Une table de contexte : qui, quoi, quand, où. Elle sert à filtrer et à regrouper | `dim_filiale` : nom, pays, région, devise |
| **Fait** | Une table de chiffres : combien. Elle contient des mesures et des clés vers les dimensions | `fct_position_tresorerie_quotidienne` |
| **Mesure** | Un nombre que l'on additionne, compare ou moyenne | `position_cloture_eur` |
| **Grain** | Ce que représente une ligne d'une table. C'est la première chose à définir | 1 ligne = 1 jour × 1 filiale |
| **Additive** | S'additionne sur toutes les dimensions | Les décaissements |
| **Semi-additive** | Un stock : s'additionne entre filiales (en euros), pas dans le temps. On lit le dernier jour | La position, l'encours |
| **Non additive** | Ne s'additionne jamais : ratio, taux, pourcentage | Le ratio de liquidité |
| **Schéma en étoile** | Un fait au centre, relié directement à ses dimensions | |
| **Constellation** | Plusieurs faits qui partagent les mêmes dimensions. C'est notre cas, au sens strict | |
| **Dimension conforme** | Une seule table pour un même contexte, partagée par tous les faits. Un filtre sur la France agit sur tous les chiffres | `dim_filiale`, `dim_date` |
| **Clé primaire** | Identifie une ligne de façon unique | `code_filiale` dans `dim_filiale` |
| **Clé étrangère** | Dans un fait, la colonne qui pointe vers une dimension | `code_filiale` dans un fait |
| **Clé métier** | Un code déjà utilisé par le métier (`FR`, `EUR`). Une clé technique serait un numéro créé exprès | Nous utilisons des clés métier stables |
| **SCD (Slowly Changing Dimension)** | La façon de gérer un attribut qui change. **Type 1** : on écrase l'ancienne valeur. **Type 2** : on garde l'historique avec des dates de validité | Type 1 ici, car les référentiels ne changent pas sur 3 ans |
| **Periodic snapshot** | Un fait « photo » pris à intervalle régulier | La position chaque jour |
| **Fait transactionnel agrégé** | Des opérations résumées à un grain plus large | Les flux à l'heure |

### Power BI

| Notion | En clair |
|---|---|
| **Modèle sémantique** | Les tables importées, leurs relations et les mesures : c'est la « couche sémantique » qui donne un sens métier aux chiffres |
| **Relation 1 → \*** | Une ligne de dimension est reliée à plusieurs lignes de fait. Le filtre va de la dimension vers le fait |
| **DAX** | Le langage des formules de Power BI |
| **Mesure DAX** | Une formule calculée à la volée selon les filtres du visuel. Toutes nos KPI sont des mesures |
| **Contexte de filtre** | L'ensemble des filtres actifs (filiale choisie, année, ligne du tableau). Une mesure se calcule dans ce contexte |
| **Paramètre What-if** | Un curseur que l'utilisateur règle, dont la valeur est lue par les mesures |

## 2. Le modèle en étoile

La figure 2 du MOE (page 6) montre l'extrait principal du schéma : `dim_date` en haut, relié à tous les faits datés ; `dim_filiale` au centre ; `dim_devise`, `dim_type_transaction` et `dim_scenario_stress` autour.

### La règle du prof : dimensions et faits

Le prof a dit : « quand il y a des sommes qui traînent dans les dimensions, c'est jamais bon ». Une dimension décrit le contexte ; elle ne doit pas contenir de chiffre à additionner. C'est devenu la règle **RG-MOD-01**.

**Ce qui a été corrigé :**
- `dim_filiale` contenait la part de marché, le taux de réserve, le nombre de clients, l'encours et la réserve de départ. Ces chiffres sont passés dans un fait, `fct_situation_initiale_filiale`. Le nombre de clients, qui ne servait à aucun indicateur, a été retiré.
- `dim_scenario_stress` contenait les chocs chiffrés : ils sont dans le fait `mart_stress_test`, tels qu'appliqués à chaque filiale.
- À l'inverse, le libellé du scénario et le régime de change ne sont plus recopiés dans les faits : on les lit dans la dimension.
- Le test `assert_dimensions_sans_mesure` échoue si une colonne numérique apparaît dans une dimension.

**Les nombres qui restent dans les dimensions**, et pourquoi ce n'est pas une erreur : la parité fixe du franc CFA (655,957, une constante de définition), le sens d'un type d'opération (+1 ou −1, un code), l'ordre d'affichage (une clé de tri) et les numéros du calendrier (année, mois). On ne les additionne jamais. Le test les autorise explicitement :

```sql
where table_schema = 'marts' and table_name like 'dim\_%'
  and data_type in ('numeric', 'double precision', 'integer', 'bigint', 'smallint', 'real')
  and (table_name, column_name) not in (
      ('dim_date', 'id_date'), ('dim_date', 'annee'), …,
      ('dim_devise', 'parite_fixe_par_eur'), ('dim_type_transaction', 'sens_jambe_emetteur'))
```

### Les 5 dimensions

| Dimension | Lignes | Répond à | Contenu |
|---|---|---|---|
| `dim_date` | 2 458 | Quand ? | Jour, mois, trimestre, année, jour de semaine, libellés en français, période d'analyse ou de prévision |
| `dim_filiale` | 10 | Qui ? Où ? | Nom, pays, région, devise, système source, fuseau horaire, source des dépôts |
| `dim_devise` | 10 | Quoi ? (monnaie) | Libellé, régime de change (flottant, fixe, référence), parité fixe, banque centrale, zone |
| `dim_type_transaction` | 6 | Quoi ? (opération) | Libellé, catégorie (encaissement ou décaissement), sens |
| `dim_scenario_stress` | 7 | Quoi ? (crise) | Nom du scénario, ordre d'affichage, crise historique de référence |

`dim_date` couvre plus que 2023-2025 : l'historique de change nécessaire à la volatilité et l'horizon de prévision de janvier 2026.

**Comment `dim_date` est construite.**

```sql
with jours as (select distinct date_cours as date_jour from {{ ref('int_taux_change_journalier') }})
select date_jour,
       extract(isodow from date_jour)::int                                   as jour_semaine,
       (array['lundi','mardi', …])[extract(isodow from date_jour)::int]      as libelle_jour,
       extract(isodow from date_jour) in (6, 7)                              as est_week_end,
       …
```

On part de la grille quotidienne des cours de change, qui contient chaque jour sans trou, de 2020 à 2026. Pour chaque jour, on calcule l'année, le trimestre, le mois, la semaine, le jour de la semaine (`isodow` : 1 = lundi), les libellés en français, pris dans un tableau, et trois indicateurs : week-end, période d'analyse, horizon de prévision. `dim_devise` et `dim_type_transaction` reprennent simplement les référentiels `ref_devises.csv` et `ref_types_transaction.csv`.

### Les 15 tables de faits

Le préfixe `fct_` désigne un fait de base, `mart_` un fait calculé à partir des autres. Tous sont des tables de faits.

| Table de faits | Lignes (gros volume) | Grain | Mesures |
|---|---|---|---|
| `fct_flux_tresorerie_horaire` | 756 193 | heure × filiale × type × fraude × gros ticket | Encaissements, décaissements, flux net, nombre d'opérations (additifs) |
| `fct_position_tresorerie_quotidienne` | 10 960 | jour × filiale | Position et encours (semi-additifs), flux du jour, opérations de fin de mois |
| `fct_situation_initiale_filiale` | 10 | filiale au 31/12/2022 | Part de marché, taux de réserve, encours et réserve de départ |
| `fct_taux_change` | 24 580 | jour × devise | Cours, variation, volatilité (non additifs) |
| `mart_liquidite_placement` | 10 960 | jour × filiale | Ratio de liquidité, excédent à placer, besoin de refinancement |
| `mart_exposition_change` | 7 672 | jour × devise | Exposition, VaR, coût de couverture, décision |
| `mart_stress_test` | 70 | scénario × filiale | Chocs appliqués, position stressée, survie, besoin |
| `mart_prevision_tresorerie` | 11 270 | jour × filiale | Réalisé et fourchette prévue, probabilité sous le besoin |
| `mart_prevision_change` | 1 260 | jour × devise | Fourchette de cours et cours réalisé |
| `mart_backtest_journalier` | 5 520 | origine × filiale × série × modèle × jour | Réel et prévu |
| `mart_reserve_optimale` | 10 | filiale | Réserve requise, liquidité libérable, gain annuel |
| `mart_controle_a_posteriori` | 9 | filiale | Dépôts prévus et réels de janvier 2026 |
| `mart_qualite_ancrage` | 481 | filiale × date publiée | Encours réel et reconstitué, écart |
| `mart_qualite_sources` | 360 | système × filiale × mois | Lignes reçues et retenues, défauts |
| `mart_qualite_defauts` | 2 484 | système × filiale × mois × défaut | Lignes par type de défaut |

La partie 2 explique le mart de change, la partie 4 les marts de qualité et la partie 6 ceux de prévision et de stress. Ici, tu dois connaître en détail les deux faits principaux et le mart de liquidité.

## 3. Le code des faits principaux

### `fct_flux_tresorerie_horaire` : le fait principal, incrémental

```sql
{{ config(materialized='incremental', unique_key='id_flux', incremental_strategy='delete+insert', …) }}
select
    md5(concat_ws('|', heure_operation, code_filiale, code_type, est_fraude, est_gros_ticket)) as id_flux,
    …
    sum(nb_operations)                                         as nb_mouvements,
    sum(case when sens > 0 then montant_devise else 0 end)     as encaissements_devise,
    sum(case when sens < 0 then montant_devise else 0 end)     as decaissements_devise,
    sum(sens * montant_devise)                                 as flux_net_devise,
    …
from {{ ref('int_mouvements_tresorerie') }}
{% if is_incremental() %}
where date_operation >= (select max(date_operation) - 35 from {{ this }})
{% endif %}
group by heure_operation, date_operation, code_filiale, code_devise, code_type, est_fraude, est_gros_ticket
```

- **Le grain** est donné par le `group by` : une ligne par heure, filiale, type, fraude oui ou non, gros ticket oui ou non. 40,7 M d'opérations deviennent 756 193 lignes.
- **L'identifiant** `id_flux` est un MD5 des colonnes du grain : la même combinaison donne toujours le même identifiant.
- **L'incrémental** : au premier lancement, dbt construit toute la table. Ensuite, seuls les 35 derniers jours sont recalculés ; les lignes de même `id_flux` sont supprimées puis réinsérées (`delete+insert`). Les 35 jours absorbent les fichiers arrivés en retard ou renvoyés. Si des données plus anciennes changent, il faut `--full-refresh`.

### `fct_position_tresorerie_quotidienne` : la trésorerie gérée

C'est le calcul le plus important du projet. Il suit les règles RG-POS.

**Étape 1 : un calendrier sans trou.**

```sql
select d.date_position, f.code_filiale, f.code_devise
from (select cast(generate_series(min(date_position), max(date_position), interval '1 day') as date) …) d
cross join {{ ref('ref_filiales') }} f
```

`generate_series` crée tous les jours de la période, et le `cross join` les croise avec les 10 filiales : 1 096 jours × 10 filiales = 10 960 lignes. Un jour sans opération existe quand même, avec des flux à 0.

**Étape 2 : les cumuls.**

```sql
sum(flux_net_devise) over (partition by code_filiale order by date_position rows unbounded preceding)
    as flux_net_cumule_devise,
sum(flux_net_devise) over (partition by code_filiale, date_trunc('month', date_position)
                           order by date_position rows unbounded preceding)
    as flux_net_cumule_mois_devise
```

Ce sont des **fonctions de fenêtre** : pour chaque ligne, on additionne les flux de toutes les lignes précédentes de la même filiale. La première donne le cumul depuis le début, la seconde le cumul depuis le 1er du mois.

**Étape 3 : l'encours et la position.**

```
encours de dépôts      = encours initial réel + cumul des flux nets               (RG-POS-04)
cible de réserve       = taux de réserve × encours de fin du mois précédent
position de clôture    = cible de réserve du mois + cumul des flux du mois        (RG-POS-06)
opération de fin de mois = cible du mois suivant − position de clôture            (RG-POS-07)
```

**Exemple simple.** La France a 10 Md€ de dépôts fin janvier et un taux de réserve de 15 % : sa cible de février est 1,5 Md€. Pendant février, le flux net cumulé atteint −200 M€ : la position de clôture du 28 février vaut 1,3 Md€. Si l'encours fin février est de 9,8 Md€, la cible de mars est 1,47 Md€. L'opération de fin de mois vaut 1,47 − 1,3 = **+170 M€ : un refinancement**. Une valeur négative serait un placement.

**Pourquoi « gérée ».** Sans ce rééquilibrage mensuel, la vraie baisse des dépôts de la zone euro en 2023 rendait la position négative, ce qui n'a pas de sens pour une banque qui pilote sa trésorerie.

**Étape 4 : les euros et l'effet de change.**

```sql
c.position_cloture_devise / t.taux_eur                                       as position_cloture_eur,
c.position_cloture_devise / t.taux_eur - c.position_cloture_devise / c.taux_reference as effet_change_eur,
```

La position est convertie au cours du jour (**RG-POS-05**). L'effet de change est la différence avec une conversion au cours du premier jour : ce que le seul mouvement du cours a fait gagner ou perdre.

### `mart_liquidite_placement` : le ratio et les décisions

```sql
p.encours_depots_eur * {{ var('taux_fuite_depots_lcr_pct') }} / 100   as besoin_liquidite_30j_eur,   -- RG-LIQ-01
100 * position_cloture_eur / nullif(besoin_liquidite_30j_eur, 0)      as ratio_couverture_liquidite_pct,  -- RG-LIQ-02
greatest(position_cloture_eur - cible_pilotage_eur, 0)                as liquidite_excedentaire_eur,  -- RG-LIQ-03
greatest(cible_pilotage_eur - position_cloture_eur, 0)                as besoin_refinancement_eur,    -- RG-LIQ-04
```

- Le besoin à 30 jours vaut 10 % des dépôts ; la cible de pilotage vaut 110 % de ce besoin.
- Le ratio est la position divisée par le besoin. `nullif(…, 0)` évite une division par zéro.
- `greatest(x, 0)` garde la valeur si elle est positive, sinon 0 : on a soit un excédent, soit un besoin, jamais les deux.
- Le taux directeur en vigueur chaque jour est cherché dans `ref_taux_directeurs` (le dernier dont la date d'effet est passée). Il sert à chiffrer le gain d'un placement et le coût d'un refinancement (taux + 0,5 point).
- Les jours avant de passer sous 100 % = (position − besoin) / sortie nette moyenne sur 30 jours (**RG-LIQ-06**).

## 4. Le dictionnaire de données Excel

Le prof a demandé un Excel qui décrit toutes les tables, une ligne par colonne. C'est `livrables/05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_BI-predictive-Finance_G5.xlsx` : les 20 tables du schéma en étoile, soit 255 colonnes.

| Onglet | Contenu |
|---|---|
| Lisez-moi | La légende, la règle des dimensions et des faits, les nombres restants dans les dimensions |
| Tables | Une ligne par table : type, question à laquelle elle répond, grain, nombre de colonnes et de lignes, import dans Power BI |
| Faits x dimensions | Pour chaque fait, les dimensions auxquelles il est relié et son nombre de mesures |
| Dictionnaire | Une ligne par colonne : type de donnée, rôle (clé primaire, clé étrangère, attribut, mesure), additivité, unité, description, exemple |

Il est produit par `python docs/dictionnaire/generer_dictionnaire.py`, qui lit la structure réelle de la base et les descriptions de `docs/dictionnaire/descriptions.py`. Si une colonne change dans dbt, il faut compléter les descriptions et relancer le script.

## 5. Power BI

### Le modèle

- **15 tables importées**, environ 10 Mo : leur import et leur actualisation sont expliqués en [partie 3](03_architecture_chargement.md).
- **20 relations**, toutes de type 1 → \* entre une dimension et un fait, avec un filtre qui va de la dimension vers le fait. Exemple : `dim_filiale[code_filiale]` → `fct_position_tresorerie_quotidienne[code_filiale]`. Une seule relation relie deux dimensions : `dim_filiale` → `dim_devise`.
- **45 mesures**, dont 4 créées par les paramètres What-if. Elles sont toutes écrites dans `powerbi/mesures_dax.dax`.
- **4 paramètres What-if** pour le simulateur : retraits (0 à 30 %), change (−50 à +20 %), multiplicateur des sorties (1 à 3), taux (0 à 300 points de base).

### Les mesures DAX à savoir expliquer

**La date d'arrêté et la position (semi-additive).**

```dax
Date d'arrêté = CALCULATE ( MAX ( fct_position_tresorerie_quotidienne[date_position] ) )

Position de trésorerie (EUR) =
VAR DerniereDate = [Date d'arrêté]
RETURN
    CALCULATE (
        SUM ( fct_position_tresorerie_quotidienne[position_cloture_eur] ),
        dim_date[date_jour] = DerniereDate
    )
```

1. `Date d'arrêté` trouve le dernier jour de la période filtrée.
2. `VAR` garde cette date dans une variable.
3. `CALCULATE` additionne la position **seulement ce jour-là**. Si on filtre l'année 2024, on obtient la position du 31/12/2024 ; si on filtre la France, celle de la France.

C'est le motif d'une mesure semi-additive : on additionne les filiales, pas les jours.

**Le ratio de liquidité.**

```dax
Ratio de couverture liquidité % = DIVIDE ( [Position de trésorerie (EUR)], [Besoin de liquidité 30 j (EUR)] )
```

`DIVIDE` divise sans planter si le dénominateur vaut zéro. On divise deux sommes, on ne fait jamais la moyenne des ratios des filiales.

**Le refinancement et les placements.**

```dax
Refinancement levé (EUR) =
CALCULATE ( SUM ( fct_position_tresorerie_quotidienne[operation_tresorerie_eur] ),
            fct_position_tresorerie_quotidienne[operation_tresorerie_eur] > 0 )
```

On additionne les opérations de fin de mois positives. Les placements additionnent les négatives, avec le signe inversé. Ce sont des flux : ils s'additionnent sur la période.

**La VaR, devise par devise.**

```dax
VaR change 95 % 10 j (EUR) =
VAR DerniereDate = CALCULATE ( MAX ( mart_exposition_change[date_position] ) )
RETURN
    SUMX ( VALUES ( dim_filiale[code_devise] ),
        VAR Devise = dim_filiale[code_devise]
        RETURN CALCULATE ( SUM ( mart_exposition_change[var_95_10j_eur] ),
                           dim_date[date_jour] = DerniereDate,
                           mart_exposition_change[code_devise] = Devise ) )
```

`mart_exposition_change` est par devise, pas par filiale. `SUMX` parcourt les devises des filiales filtrées et additionne leur VaR. Si on filtre la France, la seule devise est l'euro, qui n'a pas de VaR : la carte est vide. Une première version ignorait le filtre filiale ; c'est ce qui a été corrigé.

**Le WAPE, calculé en euros.**

```dax
WAPE du modèle champion % =
CALCULATE ( DIVIDE ( SUMX ( mart_backtest_journalier, ABS ( [reel_eur] - [prevu_eur] ) ),
                     SUM ( mart_backtest_journalier[reel_eur] ) ),
            mart_backtest_journalier[est_champion] = TRUE () )
```

Somme des écarts absolus divisée par la somme du réel, seulement pour le modèle retenu. En euros, pour ne pas additionner des francs CFA et des couronnes. En devise locale, le résultat était faux : 17,1 % au lieu de 14,5 %.

**Une valeur par défaut quand rien n'est filtré.**

```dax
Encours réel publié (devise) =
VAR Filiale = SELECTEDVALUE ( dim_filiale[code_filiale], "FR" )
RETURN CALCULATE ( SUM ( mart_qualite_ancrage[encours_reel_devise] ),
                   REMOVEFILTERS ( dim_filiale ), dim_filiale[code_filiale] = Filiale )
```

Additionner des encours en devises différentes n'a pas de sens. `SELECTEDVALUE` prend la filiale choisie, ou la France par défaut. Les cours de change prévus utilisent le même principe, avec le dollar par défaut.

Les mesures du simulateur de stress sont expliquées dans la [partie 6](06_prevision_risques.md).

### Les 45 mesures du rapport

| Groupe | Mesures | Ce qu'elles font |
|---|---|---|
| Flux | Encaissements (EUR), Décaissements (EUR) | Les sommes des flux en euros |
| Position | Date d'arrêté, Position de trésorerie (EUR), Encours de dépôts (EUR) | Le dernier jour filtré, puis le stock ce jour-là |
| Liquidité | Besoin de liquidité 30 j (EUR), Ratio de couverture liquidité %, Jours sous 100 %, Refinancement levé (EUR), Excédent placé (EUR) | Le ratio et ses deux termes ; le nombre de jours-filiales sous 100 % ; les opérations de fin de mois |
| Change | Coût annuel de couverture de change (EUR), Effet de change cumulé (EUR), Exposition au change (EUR), VaR change 95 % 10 j (EUR), Recommandation de couverture | Lues au dernier jour ; la VaR additionne les devises filtrées ; la recommandation renvoie le texte du mart |
| Prévision | Position prévue P05, P50 et P95 (EUR), Probabilité de passer sous le besoin de liquidité %, WAPE du modèle champion %, Taux de change prévu P05, P50 et P95, Taux de change réalisé | La fourchette de position ; la plus forte probabilité parmi les filiales ; l'erreur en euros ; le cours de la devise choisie, le dollar par défaut |
| Simulateur | Facteur choc change, Position stressée (EUR), Flux net quotidien stressé (EUR), Horizon de survie (jours), Besoin de refinancement stressé (EUR), Coût du refinancement stressé (EUR/an), Statut de résilience, Filiales critiques | Les formules des stress tests, rejouées avec les curseurs (partie 6) |
| Curseurs | Valeur Choc retraits %, Valeur Choc change %, Valeur Multiplicateur sorties, Valeur Choc taux (pb) | Créées avec les paramètres What-if : elles renvoient la valeur choisie |
| Qualité | Lignes brutes reçues, Lignes retenues après nettoyage, Taux de rejet %, Doublons supprimés, Libellés corrigés, Devises corrigées, Opérations annulées, tests et extournes écartés, Encours réel publié (devise), Encours reconstitué (devise) | Les sommes des comptages de `mart_qualite_sources` ; les encours de la filiale choisie, la France par défaut |

### Les 5 pages

| Page | Contenu |
|---|---|
| Cockpit DAF | Filtres filiale et année ; cartes position, ratio, refinancement, placement ; refinancement et placements par mois ; tableau par filiale |
| Prévisions | Risque de passer sous 100 %, WAPE ; position réalisée puis prévue avec sa fourchette ; flux par mois ; réserve requise ; dépôts réels de janvier 2026 |
| Change & couverture | Exposition, VaR, coût de couverture ; cours prévu et réalisé ; décision par devise ; effet de change cumulé |
| Simulateur de stress | 4 curseurs ; position après choc, survie, besoin, coût ; simulation par filiale ; les 7 scénarios |
| Qualité des données | Lignes reçues, taux de rejet ; défauts corrigés par système ; encours réel et reconstitué |

En tout, 37 visuels. Une carte vide (« (Vide) ») a un sens : pas de limite de survie, ou pas de risque de change pour l'euro.

## 6. Les chiffres à connaître

| Indicateur (gros volume, sans filtre) | Valeur |
|---|---|
| Position de trésorerie | 5 534 752 700 € (5,53 Md€) |
| Ratio de liquidité | 157,6 % |
| Refinancement levé sur 3 ans | 6 937 250 563 € (6,94 Md€) |
| Excédent placé sur 3 ans | 5 600 088 166 € (5,60 Md€) |
| Passages sous 100 % | 175, dont 60 en janvier |
| France | 1 837 213 487 €, 162,6 %, 23 jours sous 100 % |
| États-Unis | 572 269 201 €, 119,7 %, 44 jours sous 100 % |

## 7. Les questions probables du prof

**Quelle différence entre une dimension et un fait ?**
Une dimension décrit le contexte : qui, quoi, quand, où. Un fait contient les chiffres : combien. On filtre avec les dimensions, on calcule avec les faits.

**Pourquoi y avait-il des chiffres dans `dim_filiale`, et qu'avez-vous fait ?**
Nous y avions rangé les paramètres de départ de chaque filiale. Ce sont des chiffres, donc nous les avons déplacés dans le fait `fct_situation_initiale_filiale`, supprimé le nombre de clients qui ne servait pas, et ajouté un test qui bloque tout retour en arrière.

**Il reste pourtant des nombres dans vos dimensions ?**
Oui : la parité du franc CFA, le sens +1 ou −1, l'ordre d'affichage et les numéros du calendrier. Ce sont des constantes ou des codes ; on ne les additionne jamais.

**Qu'est-ce que le grain, et pourquoi est-ce important ?**
C'est ce que représente une ligne. Sans grain clair, on additionne des choses qui ne s'additionnent pas, ou on compte deux fois la même chose.

**Pourquoi la position est-elle semi-additive ?**
C'est un stock. On peut additionner les filiales à une même date, en euros, mais pas les jours : 100 € lundi et 100 € mardi, ce n'est pas 200 €. La mesure DAX prend donc le dernier jour.

**Pourquoi SCD de type 1 ?**
Les référentiels ne changent pas sur la période : un historique n'apporterait rien. Dans un vrai projet, on passerait en type 2 les attributs dont l'historique compte, avec une clé technique.

**Pourquoi des clés métier plutôt que des clés techniques ?**
Les codes `FR`, `EUR` sont stables et connus de tous. Une clé technique deviendrait nécessaire avec un historique de type 2.

**Est-ce vraiment une étoile ?**
Au sens strict, c'est une constellation : plusieurs faits partagent les mêmes dimensions conformes. Et `dim_filiale` est reliée à `dim_devise`, car chaque filiale a une devise.

**Comment garantissez-vous qu'un KPI est calculé partout de la même façon ?**
Chaque KPI est une seule mesure DAX, réutilisée par tous les visuels. Une correction se fait à un seul endroit, comme pour le WAPE.

## 8. Les limites à assumer

- Le modèle est en SCD type 1 : pas d'historique des référentiels.
- Le ratio de liquidité est simplifié (10 % de fuite pour tous les dépôts).

## 9. Pour t'entraîner

1. Ouvre `Cresus.pbip`, clique sur **Actualiser**, puis fais la démonstration des 5 pages en 3 minutes.
2. Filtre la France sur le Cockpit et retrouve 1,84 Md€ et 162,6 %.
3. Dans la vue Modèle de Power BI, retrouve les 20 relations et le sens des filtres.
4. Dans pgAdmin, vérifie le grain du fait de position :
   ```sql
   select date_position, code_filiale, count(*) from marts.fct_position_tresorerie_quotidienne
   group by 1, 2 having count(*) > 1;   -- doit ne rien renvoyer
   ```
5. Refais à la main l'exemple de la France (cible, position, opération de fin de mois).
6. Ouvre l'Excel et retrouve, pour `mart_stress_test`, ses clés étrangères et ses mesures.

## 10. Avec qui tu travailles

| Partie | La frontière |
|---|---|
| 1. Besoin et KPI | Tu calcules les KPI qu'elle présente : position, ratio, refinancement, placement |
| 3. Architecture | Elle branche Power BI sur tes tables : import, actualisation, sécurité, format PBIP ; la macro `numeric` → `double precision` ; le `--full-refresh` du fait incrémental |
| 2. Données et change | Ta page Change & couverture et ta mesure de VaR affichent son mart `mart_exposition_change` |
| 4. Nettoyage | Tes faits partent de ses tables intermediate ; son test protège tes dimensions |
| 6. Prévision | Tu affiches ses marts de prévision et le simulateur ; Python lit ton fait de position |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| `dbt/models/marts/dimensions/dim_date.sql` et les 4 autres `dim_*` | Les 5 dimensions |
| `dbt/models/marts/faits/fct_flux_tresorerie_horaire.sql` | Le fait principal, incrémental |
| `dbt/models/marts/faits/fct_position_tresorerie_quotidienne.sql` | La position gérée et l'encours |
| `dbt/models/marts/faits/fct_situation_initiale_filiale.sql` | La situation de départ de chaque filiale |
| `dbt/models/marts/analyses/mart_liquidite_placement.sql` | Le ratio, le refinancement et les placements |
| `dbt/models/marts/schema.yml` | Le grain, le type et les tests de chaque table du schéma `marts` |
| `dbt/tests/assert_dimensions_sans_mesure.sql`, `assert_marts_sans_numeric.sql` | Les tests de la règle des dimensions et du format pour Power BI |
| `dbt/seeds/ref_devises.csv`, `ref_types_transaction.csv`, `ref_scenarios_stress.csv` | Les référentiels repris par les dimensions |
| `docs/dictionnaire/descriptions.py`, `generer_dictionnaire.py` | Le dictionnaire Excel : les descriptions et le script qui l'écrit |
| `livrables/05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_…` | Le dictionnaire livré |
| `powerbi/mesures_dax.dax` | Les 41 mesures écrites à la main (les 4 mesures « Valeur » viennent des curseurs) |
| `powerbi/Cresus/Cresus.SemanticModel/definition/tables/` | Une table du modèle par fichier, dont `_Mesures.tmdl` |
| `powerbi/Cresus/Cresus.SemanticModel/definition/relationships.tmdl` | Les 20 relations |
| `powerbi/Cresus/Cresus.Report/definition/pages/` | Les 5 pages et leurs 37 visuels |
| [docs/04](../04_guide_power_bi.md) | Le guide du rapport |
