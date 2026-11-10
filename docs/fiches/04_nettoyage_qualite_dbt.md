# Partie 4 : nettoyage et qualité avec dbt

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **comment les données sales des 4 systèmes deviennent des données propres et fiables**, et **comment on le prouve**. Tu maîtrises dbt, le SQL de nettoyage, les 11 règles RG-NET, les 104 tests et la recette. C'est la partie la plus technique en SQL, et le prof interroge souvent sur la qualité des données. Tu présentes aussi la méthodologie du projet : la démarche, les priorités et l'organisation.

**Diapos :** 5 (méthodologie), 15 (la recette, décision GO). Tu fais aussi une courte démonstration des tests et du lineage (`dbt docs`).

**Fichiers :** `dbt/dbt_project.yml`, `dbt/profiles.yml`, `dbt/macros/`, `dbt/models/staging/`, `dbt/models/intermediate/`, `dbt/seeds/ref_correspondance_*.csv`, `dbt/tests/`, `dbt/models/marts/analyses/mart_qualite_*.sql`.

## À savoir dire en une minute

> Les 4 systèmes envoient des fichiers dans des formats différents, avec des défauts : doublons, dates en plusieurs formats, montants mal écrits, encodage cassé, opérations annulées. Le nettoyage est écrit en SQL avec dbt, en deux couches. La couche staging a un modèle par système : elle remet chaque colonne au bon type et au même format, sans rien supprimer. La couche intermediate réunit les 4 systèmes, applique 11 règles de nettoyage numérotées RG-NET, et donne à chaque ligne écartée un motif. Rien n'est supprimé en silence. Sur le gros volume, 42,7 M de lignes deviennent 40,7 M d'opérations : 4,5 % de rejets, presque tous des doublons. Nous le prouvons avec 104 tests automatiques, dont deux essentiels : chaque jour et pour chaque filiale, les crédits, les débits et le nombre d'opérations égalent le grand livre, et l'encours reconstitué égale les vrais dépôts publiés.

## 1. La méthodologie du projet (diapo 5)

La diapo 5 montre comment le projet relie le besoin à la restitution. Le cours note la capacité à relier ces maillons.

| Maillon | Ce que nous avons fait | Partie |
|---|---|---|
| Besoin | Les objectifs du sujet traduits en 6 KPI définis | 1 |
| Données | Sources validées d'abord : PaySim seul ne suffit pas | 2 |
| Architecture | ELT en couches, de `raw` à `marts` | 3 |
| Modèle | Étoile, grain documenté, position semi-additive | 5 |
| Alimentation | Python et dbt, tests automatiques | 3 et 4 |
| Restitution | 5 pages Power BI, simulateur, sécurité par filiale | 5 et 3 |

### La démarche

- **Les données d'abord, les KPI ensuite.** C'est la consigne du cours. Un KPI calculé sur des données fausses fait prendre de mauvaises décisions.
- **Le profilage a changé le projet.** Il a montré que PaySim seul était inexploitable : 12 jours normaux, fraude constante, soldes incohérents. Nous sommes passés à 3 ans de flux ancrés sur les dépôts réels.
- **Chaque décision est tracée dans Git.** L'historique est dans `CLAUDE.md`, section 7 : le passage à 3 ans, la trésorerie gérée, l'effet « mois » ajouté après le contrôle de janvier 2026, la séparation des dimensions et des faits.
- **AMOA puis MOE.** De la fiche d'expertise, qui décrit le besoin, au rendu POC et à sa recette, qui prouvent la solution.

### Les priorités (MoSCoW)

| Priorité | Contenu |
|---|---|
| Must (indispensable) | KPI justes, traçabilité, rapprochement au grand livre, sécurité par filiale |
| Should (important) | Prévision, scénarios de stress, recommandation de couverture |
| Could (bonus) | Catalogue détaillé des défauts dans le rapport, alertes automatiques |
| Won't now (plus tard) | Temps réel, entrepôt cloud, compensation entre filiales |

### L'organisation

Rôles proposés pour l'équipe projet : un Product Owner, qui porte le besoin de la Direction Financière ; un Business Analyst, qui traduit le besoin en règles et en KPI ; un Lead Dev, qui choisit l'architecture ; des développeurs ; un Scrum Master, qui anime le travail par itérations. **À décider en groupe :** qui a tenu quel rôle, car le prof peut le demander.

## 2. Les notions à maîtriser

### dbt

dbt (data build tool) **ne stocke rien et ne déplace aucune donnée** : il prend des fichiers SQL, les complète, les exécute dans PostgreSQL dans le bon ordre, puis lance les tests.

| Notion dbt | En clair |
|---|---|
| **Modèle** | Un fichier `.sql` qui contient un seul `select`. dbt en fait une vue ou une table du même nom |
| **`ref('modele')`** | Fait référence à un autre modèle. dbt en déduit l'ordre d'exécution et le lineage |
| **`source('raw', 'table')`** | Fait référence à une table chargée par un autre outil, ici Python |
| **Seed** | Un petit fichier CSV de référence (filiales, devises, correspondances) que dbt charge en table |
| **Matérialisation** | La façon de créer le modèle : `view` (vue, rien n'est stocké), `table` (recalculée en entier), `incremental` (seules les nouvelles lignes sont ajoutées) |
| **Test générique** | Un test prêt à l'emploi déclaré dans un `schema.yml` : `unique`, `not_null`, `relationships`, `accepted_values` |
| **Test singulier** | Une requête SQL écrite à la main dans `dbt/tests/`. Le test échoue si la requête renvoie au moins une ligne |
| **Sévérité** | `error` bloque le pipeline ; `warn` affiche seulement une alerte |
| **Macro** | Une fonction réutilisable en Jinja, qui produit du SQL |
| **Jinja** | Le langage de modèles entre `{{ }}` et `{% %}` que dbt remplace avant d'exécuter le SQL |
| **Variable (`var`)** | Un paramètre défini dans `dbt_project.yml`, par exemple les dates de la période |
| **`dbt build`** | Charge les seeds, construit les modèles et lance les tests, dans l'ordre des dépendances |
| **Lineage** | Le graphe qui montre, de la source au rapport, quel modèle dépend de quel autre. Il s'affiche avec `dbt docs` |
| **Tag** | Une étiquette pour lancer un groupe de modèles, ici `prevision` |
| **Adaptateur** | Le module qui permet à dbt de parler à une base précise : ici `dbt-postgres`, pour PostgreSQL |

### Les techniques SQL utilisées

| Technique | À quoi elle sert | Exemple dans le projet |
|---|---|---|
| `with … as (…)` (CTE) | Découper une requête en étapes nommées, lisibles | Toutes les requêtes |
| `case when … then … end` | Choisir une valeur selon une condition | Le sens `C` → +1, `D` → −1 |
| `cast(x as type)` ou `x::type` | Changer le type d'une valeur | Texte → nombre |
| `trim`, `upper`, `translate` | Retirer les espaces, mettre en majuscules, remplacer des caractères | Retirer les accents d'un libellé |
| `regexp_replace` | Remplacer selon un motif (expression régulière) | Garder seulement les chiffres d'un montant |
| `nullif`, `coalesce` | Transformer une valeur en vide, ou remplacer un vide | `nullif(trim(x), '')` |
| `to_timestamp(texte, format)` | Lire une date écrite dans un format donné | `'DD/MM/YYYY HH24:MI:SS'` |
| `at time zone` | Convertir une heure d'un fuseau à un autre | UTC → heure de Stockholm |
| `union all` | Empiler les lignes de plusieurs requêtes | Réunir les 4 systèmes |
| `left join` | Relier deux tables en gardant toutes les lignes de gauche | Trouver le type d'opération d'un libellé |
| `row_number() over (partition by … order by …)` | Numéroter les lignes dans chaque groupe | Repérer les doublons |
| `md5(…)` | Fabriquer un identifiant à partir de plusieurs colonnes | `id_ligne_source` |
| `full outer join` | Relier deux tables en gardant les lignes des deux côtés | Comparer au grand livre |

## 3. Le projet dbt

### `dbt_project.yml`

```yaml
models:
  cresus:
    staging:
      +schema: staging
      +materialized: view
    intermediate:
      +schema: intermediate
      +materialized: view
    marts:
      +schema: marts
      +materialized: table
      +post-hook: "{{ convertir_numeric_en_double() }}"
```

Chaque dossier de modèles va dans son schéma, avec sa matérialisation par défaut. Les modèles lourds de la couche intermediate sont forcés en table (`{{ config(materialized='table') }}`) pour ne pas être recalculés à chaque lecture.

**Les variables** du projet rassemblent les paramètres métier : période (`2023-01-01` à `2025-12-31`), report maximal d'un cours de change (7 jours), taux de fuite du ratio de liquidité (10 %), cible de pilotage (110 %), seuil d'un gros ticket (10 000 €), etc.

### `profiles.yml`

```yaml
host: "{{ env_var('POSTGRES_HOST', 'localhost') }}"
```

dbt lit les mêmes réglages de connexion que Python, depuis le fichier `.env`.

### Les macros

- `normaliser_libelle` : majuscules, sans accents, espaces réduits. Utilisée pour comparer des libellés écrits différemment.
- `normaliser_client` et `client_manquant` : un identifiant client devient `<FILIALE>-<7 chiffres>`, ou `<FILIALE>-INCONNU` s'il est vide ou codé `NULL`, `N/A`, `?`, `0000000`.
- `generate_schema_name` : garde les noms de schéma tels quels (`staging` au lieu de `public_staging`).
- `entre_bornes`, `unicite_combinee` : deux tests génériques écrits par nous, pour ne pas dépendre de bibliothèques externes.

Les macros sont rangées dans `dbt/macros/` : `normalisation.sql` (libellés et clients), `tests_generiques.sql` (les deux tests), `compatibilite_power_bi.sql` (la conversion pour Power BI, partie 3) et `generate_schema_name.sql`.

### Les sources et leur fraîcheur (`models/sources.yml`)

Ce fichier déclare les tables que dbt n'a pas créées : celles de `raw`, chargées par Python, et celles de `ml`, écrites par la prévision. C'est ce qui permet d'écrire `{{ source('raw', 'src_sab') }}` dans un modèle. On y teste aussi les tables brutes : clés non vides, encours positifs, pas deux encours pour la même date.

```yaml
- name: bce_taux_change
  loaded_at_field: "cast(date_cours as timestamp)"
  freshness:
    warn_after: {count: 10, period: day}
```

`dbt source freshness`, lancé au début de l'étape dbt, vérifie que le dernier cours BCE a moins de 10 jours. Sinon, il affiche une alerte (`WARN freshness`) : l'export Webstat est à mettre à jour avant une présentation. C'est une alerte et non une erreur, car les données de 2023 à 2025 restent justes.

### L'exposition (`models/exposures.yml`)

Elle déclare le rapport Power BI comme utilisateur de 15 marts. Le rapport apparaît alors au bout du lineage dans `dbt docs` : avant de modifier une table, on voit qu'elle alimente le rapport.

### Les commandes dbt utiles

| Commande | Ce qu'elle fait |
|---|---|
| `dbt build --profiles-dir .` | Les référentiels, les modèles et les tests, dans l'ordre |
| `dbt run`, `dbt test`, `dbt seed` | Seulement les modèles, les tests ou les référentiels |
| `dbt build --select tag:prevision` | Seulement les marts de prévision |
| `dbt build --exclude tag:prevision` | Tout sauf la prévision |
| `dbt build --full-refresh` | Reconstruit aussi le fait incrémental |
| `dbt source freshness` | Vérifie la fraîcheur des cours BCE |
| `dbt docs generate`, puis `dbt docs serve` | La documentation et le lineage, dans le navigateur |

## 4. La couche staging : un modèle par système

Chaque modèle `stg_<systeme>__operations` lit la table brute et produit **les mêmes colonnes pour les 4 systèmes**. Il ne supprime aucune ligne : il type, il normalise et il signale.

### Exemple détaillé : SAB

```sql
case when trim(s.date_ope) ~ '^\d{4}-\d{2}-\d{2}$'
     then to_timestamp(trim(s.date_ope) || ' ' || trim(s.heure_ope), 'YYYY-MM-DD HH24:MI:SS')
     else to_timestamp(trim(s.date_ope) || ' ' || trim(s.heure_ope), 'DD/MM/YYYY HH24:MI:SS')
end::timestamp                                                         as horodatage,
```

SAB a changé de format de date en juillet 2024. Si la date ressemble à `2024-07-15` (motif `~ '^\d{4}-\d{2}-\d{2}$'`), on la lit en format ISO ; sinon en `jj/mm/aaaa`. On colle la date et l'heure, puis on obtient un horodatage (**RG-NET-02**).

```sql
replace(nullif(translate(s.montant, ' ' || chr(160), ''), ''), ',', '.')::numeric(18, 2)
```

On lit cette ligne de l'intérieur vers l'extérieur (**RG-NET-04**) :
1. `translate(s.montant, ' ' || chr(160), '')` retire les espaces et l'espace insécable (`chr(160)`) des fichiers retouchés sous Excel : `1 234,56` devient `1234,56`.
2. `nullif(…, '')` transforme un texte vide en valeur vide.
3. `replace(…, ',', '.')` remplace la virgule décimale française par un point.
4. `::numeric(18, 2)` convertit en nombre à 2 décimales.

```sql
case upper(trim(s.sens)) when 'C' then 1 when 'D' then -1 end          as sens_source,
trim(s.ref_ope)                                                        as ref_operation,
left join filiales f on f.code_entite_source = upper(trim(s.code_etab))
```

Le sens `C` (crédit) devient +1, `D` (débit) devient −1. Les références saisies avec des espaces sont nettoyées, sinon des doublons passeraient (**RG-NET-07**). La filiale est retrouvée grâce à son code entité dans `ref_filiales`.

### Les particularités des autres systèmes

| Système | Ce que fait son modèle staging |
|---|---|
| **NORDIC** | Heure UTC convertie en heure locale avec le fuseau de la filiale : `cast(booking_ts as timestamptz) at time zone fuseau_horaire` (**RG-NET-03**). Montant en öre divisé par 100 si `amount_unit = 'MINOR'`. Montant signé : la valeur absolue donne le montant, le signe donne le sens. Code entité remis en majuscules |
| **AMERICORE** | Le montant est dans `DebitAmount` ou `CreditAmount` : la colonne remplie donne le sens. `regexp_replace` ne garde que les chiffres et le point, ce qui retire `,`, `(`, `)` et `US$`. Dates `MM/JJ/AAAA` avec AM/PM |
| **DELTA** | La filiale est lue dans le nom du fichier. Dates `aaaammjj`. Montants entiers, car le franc CFA n'a pas de centimes. Indicateur de fraude vide traité comme « non suspect » (**RG-NET-11**). Le sens est déduit du type d'opération |

### Les deux modèles staging des données réelles

- **`stg_bce__taux_change`** met le code devise en majuscules sans espaces, renomme `taux` en `taux_eur`, écarte les cours nuls et ne garde que 3 ans d'historique avant 2023, pour la volatilité. Un test vérifie qu'il n'y a qu'un cours par date et par devise.
- **`stg_zf__ancrages`** reprend les dépôts réels ramenés à la taille de ZF Banque, aux dates de publication. Il sert au contrôle d'ancrage (`mart_qualite_ancrage`) et au point de départ de chaque filiale (`int_encours_initial`).

## 5. La couche intermediate : les règles de nettoyage

### `int_operations_controlees` : le cœur du nettoyage

Ce modèle est une table de 42,7 M de lignes sur le gros volume. **Il garde toutes les lignes**, avec leurs indicateurs de qualité et un motif de rejet quand il y en a un.

**Étape 1 : réunir les 4 systèmes.**

```sql
with sources as (
    select * from {{ ref('stg_sab__operations') }}
    union all select * from {{ ref('stg_nordic__operations') }}
    union all select * from {{ ref('stg_americore__operations') }}
    union all select * from {{ ref('stg_delta__operations') }}
),
```

C'est possible parce que les 4 modèles staging produisent exactement les mêmes colonnes.

**Étape 2 : repérer les écritures annulées par une extourne.**

```sql
extournees as (
    select distinct systeme_source, reference_extournee as ref_operation
    from sources
    where reference_extournee is not null
),
```

Une extourne NORDIC indique la référence de l'écriture qu'elle annule. On garde la liste de ces écritures : l'extourne et l'écriture annulée seront toutes les deux écartées.

**Étape 3 : enrichir chaque ligne.**

```sql
left join {{ ref('ref_correspondance_libelles') }} l
    on l.systeme_source = s.systeme_source and l.libelle_normalise = s.libelle_normalise
left join {{ ref('ref_correspondance_devises') }} d on d.valeur_normalisee = upper(trim(s.devise_source))
...
row_number() over (partition by s.systeme_source, s.ref_operation
                   order by s.nom_fichier, s.num_ligne)                       as rang_occurrence
```

- **Libellés (RG-NET-05).** Le libellé normalisé (`VIR RECU SEPA`, `DÃ‰PÃ”T`…) est cherché dans une table de correspondance de 42 lignes, qui donne le type d'opération officiel (`VIREMENT_RECU`, `CASH_IN`…). Elle contient aussi les libellés à l'encodage cassé.
- **Devises (RG-NET-06).** `€`, `eur`, ` EUR` deviennent `EUR` grâce à une autre table de correspondance. `FCFA` devient XOF ou XAF selon la filiale.
- **Clients (RG-NET-09).** La macro `normaliser_client` remet les identifiants au même format.
- **Doublons (RG-NET-07).** `row_number()` numérote les lignes qui ont la même référence dans le même système, dans l'ordre des fichiers et des lignes. La première reçoit 1, les copies 2, 3… Toute ligne de rang supérieur à 1 est un doublon. C'est ainsi qu'on attrape les lignes renvoyées, les fichiers mensuels qui se chevauchent et les fichiers renvoyés `_v2`.

**Étape 4 : donner un motif de rejet.**

```sql
case
    when code_filiale is null                         then 'Filiale inconnue'
    when rang_occurrence > 1                          then 'Doublon'
    when statut_source = 'ANNULE'                     then 'Opération annulée'
    when est_compte_test                              then 'Compte de test'
    when statut_source = 'REVERSAL'                   then 'Extourne'
    when est_ecriture_extournee                       then 'Écriture extournée'
    when statut_source = 'PENDING'                    then 'Autorisation en attente'
    when code_type is null                            then 'Libellé inconnu'
    when horodatage is null or … not between …        then 'Date invalide'
    when montant_unitaire_devise = 0                  then 'Opération à montant nul'
    when montant_unitaire_devise is null or … < 0     then 'Montant invalide'
    when code_devise is distinct from devise_filiale  then 'Devise incohérente'
    when sens_source is not null and sens_source <> sens_attendu then 'Sens incohérent'
end                                                   as motif_rejet
```

Le `case` s'arrête à la première condition vraie : **l'ordre compte**. Une ligne sans motif (`null`) est retenue. Les 6 premiers motifs sont les exclusions métier (**RG-NET-08**) ; les suivants sont les contrôles de validité (**RG-NET-10**).

### Les autres modèles intermediate

| Modèle | Rôle |
|---|---|
| `int_operations_nettoyees` | Les lignes sans motif de rejet, au format unique du groupe. Le montant total = montant unitaire × nombre d'opérations du lot |
| `int_operations_rejetees` | Les lignes écartées, avec leur motif : la liste à renvoyer aux filiales |
| `int_mouvements_tresorerie` | Chaque opération retenue devient un mouvement : sens +1 ou −1 selon son type (**RG-SEN-01**), montant converti en euros au cours du jour (**RG-VAL-02**), repère des gros tickets de plus de 10 000 € |
| `int_taux_change_journalier` | Un cours pour chaque jour et chaque devise, y compris les week-ends : EUR = 1, franc CFA = 655,957, sinon le dernier cours publié reporté au plus 7 jours ; au-delà, le cours reste vide et signale une rupture, comme pour le rouble (**RG-CHG-01 à 04**) |
| `int_encours_initial` | L'encours et la réserve de chaque filiale au 31/12/2022, calculés à partir des dépôts réels (**RG-POS-01 et 02**) |

### Les 11 règles de nettoyage

| Code | Règle | Où |
|---|---|---|
| RG-NET-01 | Lire le format physique : encodage, séparateur, titre, total, en-têtes répétés, nouvelles colonnes. Codes entité en majuscules | Python (partie 3) et staging |
| RG-NET-02 | Dates multi-formats → horodatage | staging |
| RG-NET-03 | Heures UTC → heure locale de la filiale | `stg_nordic__operations` |
| RG-NET-04 | Montants : virgule, milliers, format comptable, symbole, unités mineures, sens | staging |
| RG-NET-05 | Libellés → type d'opération normalisé, y compris l'encodage cassé | `int_operations_controlees` |
| RG-NET-06 | Devises → code ISO ; `FCFA` → XOF ou XAF ; contrôle de la devise | `int_operations_controlees` |
| RG-NET-07 | Doublons : même référence dans le même système, on garde la première | `int_operations_controlees` |
| RG-NET-08 | Exclusions : annulées, comptes de test, extournes, écritures extournées, pré-autorisations | `int_operations_controlees` |
| RG-NET-09 | Client → `<FILIALE>-<7 chiffres>`, ou `<FILIALE>-INCONNU` | `int_operations_controlees` |
| RG-NET-10 | Validité : filiale, date, montant > 0, sens cohérent | `int_operations_controlees` |
| RG-NET-11 | Indicateur de fraude vide → non suspect | `stg_delta__operations` |

## 6. Les résultats du nettoyage (gros volume)

| Système | Lignes reçues | Lignes retenues | Rejetées |
|---|---|---|---|
| SAB | 21 460 324 | 20 272 872 | 5,53 % |
| NORDIC | 7 628 016 | 7 143 211 | 6,36 % |
| AMERICORE | 7 590 087 | 7 472 003 | 1,56 % |
| DELTA | 5 990 929 | 5 861 243 | 2,16 % |
| **Total** | **42 669 356** | **40 749 329** | **4,5 %** |

**Les lignes écartées (1 920 027)**, par motif :

| Motif | Lignes |
|---|---|
| Doublon | 1 761 689 |
| Autorisation en attente | 91 029 |
| Opération annulée | 42 001 |
| Opération à montant nul | 7 433 |
| Extourne | 7 086 |
| Écriture extournée | 7 086 |
| Compte de test | 3 703 |
| Motif inattendu (libellé inconnu, devise incohérente…) | **0** |

**Les valeurs corrigées** (la ligne est gardée) : 1 973 738 libellés, 1 136 325 formats (date, montant, entité, encodage), 990 287 devises, 586 197 indicateurs de fraude vides, 284 761 clients manquants ou codés nuls.

**Deux façons de compter, à ne pas confondre.** Le catalogue `mart_qualite_defauts` compte les corrections sur les lignes **retenues** : 1 973 738 libellés. `mart_qualite_sources`, affiché dans Power BI, compte les défauts sur **toutes les lignes reçues**, y compris celles qui sont ensuite écartées : 2 059 616 libellés. L'écart vient des lignes qui ont deux défauts, par exemple un doublon dont le libellé est aussi non standard.

NORDIC et SAB rejettent le plus : SAB à cause des fichiers mensuels qui se chevauchent, NORDIC à cause des pré-autorisations et des extournes. Le catalogue complet est dans `marts.mart_qualite_defauts`, consultable dans pgAdmin.

## 7. Les tests : comment on prouve la qualité

`dbt build` lance **104 tests** : 93 tests génériques et 11 tests métier écrits en SQL.

### Les tests génériques (93)

Déclarés dans les fichiers `schema.yml` : 24 `unique` (pas de doublon de clé), 45 `not_null` (pas de valeur vide), 9 `relationships` (chaque clé existe dans sa dimension), 4 `accepted_values` (valeurs autorisées), 2 `unicite_combinee`, plus 9 tests sur les tables brutes.

### Les 11 tests métier

| Test | Ce qu'il vérifie | Bloquant |
|---|---|---|
| `assert_rapprochement_comptable` | Chaque jour et pour chaque filiale, crédits, débits et nombre d'opérations nettoyés = grand livre | Oui |
| `assert_ancrage_depots_reels` | L'encours reconstitué = les vrais dépôts publiés, à 0,01 % près | Oui |
| `assert_completude_fichiers` | Lignes en base = lignes lues ; pour DELTA, = lignes et total annoncés en pied de fichier | Oui |
| `assert_conservation_volumes` | Aucune opération perdue lors des jointures (filiale, type, cours) | Oui |
| `assert_fct_flux_a_jour` | Le fait incrémental est à jour par rapport à sa source | Oui |
| `assert_taux_disponibles_periode` | Chaque devise de filiale a un cours chaque jour de la période | Oui |
| `assert_dimensions_sans_mesure` | Aucune dimension ne contient de nombre à additionner (partie 5) | Oui |
| `assert_marts_sans_numeric` | Aucune colonne `numeric` dans les marts, pour Power BI | Oui |
| `alerte_rejets_inattendus` | Aucun rejet hors des cas connus | Alerte |
| `alerte_vraisemblance_encours` | Les sorties quotidiennes restent entre 0,05 % et 5 % des dépôts | Alerte |
| `alerte_rupture_serie_change` | Aucune devise suivie n'a de série interrompue | Alerte : le rouble la déclenche, c'est attendu |

### Le test le plus important : le rapprochement

```sql
with operations as (
    select o.code_filiale, o.date_operation as date_comptable,
           sum(case when t.sens_jambe_emetteur > 0 then o.montant_devise else 0 end) as total_credits,
           sum(case when t.sens_jambe_emetteur < 0 then o.montant_devise else 0 end) as total_debits,
           sum(o.nb_operations) as nb_operations
    from {{ ref('int_operations_nettoyees') }} o
    join {{ ref('ref_types_transaction') }} t on t.code_type = o.code_type
    group by 1, 2
),
comptabilite as (select … from {{ source('raw', 'soldes_comptables') }})
select …
from operations o
full outer join comptabilite c using (code_filiale, date_comptable)
where o.code_filiale is null or c.code_filiale is null
   or abs(o.total_credits - c.total_credits) > 1
   or abs(o.total_debits - c.total_debits) > 1
   or o.nb_operations <> c.nb_operations
```

1. On additionne, par filiale et par jour, les crédits, les débits et le nombre d'opérations **après nettoyage**.
2. On les compare au grand livre, qui est une source indépendante des exports.
3. Le `full outer join` garde aussi les jours présents d'un seul côté.
4. La requête renvoie les jours en écart. **Le test réussit s'il ne renvoie rien.**

Un doublon oublié, une extourne mal traitée, une erreur de fuseau, d'unité ou de signe fait apparaître un écart. Le test passe sur les 10 960 jours-filiales.

**Attention :** le grand livre vient lui aussi de notre générateur. Le test prouve donc que **le nettoyage ne perd et n'ajoute rien**, pas que les opérations sont réelles.

### Les marts de qualité

```sql
count(*)                                              as nb_lignes_brutes,
count(*) filter (where motif_rejet is null)           as nb_lignes_retenues,
count(*) filter (where motif_rejet = 'Doublon')       as nb_doublons,
```

- **`mart_qualite_sources`** compte, par système, filiale et mois, les lignes reçues, les lignes retenues et chaque type de défaut. `count(*) filter (where …)` compte seulement les lignes qui remplissent la condition. Il alimente la page Qualité de Power BI.
- **`mart_qualite_defauts`** détaille chaque type de défaut et son traitement : ligne écartée ou valeur corrigée. Il se consulte dans pgAdmin.
- **`mart_qualite_ancrage`** compare, à chaque date publiée, l'encours réel et l'encours reconstitué. Le test d'ancrage lit ce mart.

## 8. La recette

La recette vérifie que le système est juste, de la source au tableau de bord. Elle suit le format du cours : **5 tests et 1 réconciliation**, avec précondition, action, attendu et preuve.

| ID | Test | Attendu | Constaté |
|---|---|---|---|
| T1 | Complétude | Lignes de raw = lignes des fichiers | 42 669 356 = 42 669 356 |
| T2 | Rejets tracés | Tout rejet a un motif connu | 1 920 027 rejets, 0 inattendu |
| T3 | Unicité et volumes | Une ligne par clé, opérations conservées | OK |
| T4 | Rapprochement | Crédits, débits et opérations = grand livre, jour par jour | 10 960 jours-filiales |
| T5 | Ancrage sur le réel | Encours reconstitué = encours publié | 481 dates, écart max 0,00001 % |
| R1 | Réconciliation | Aucune perte de la source à Power BI, couche par couche | OK |

Les lignes A1 à A8 du MOE vérifient ensuite les valeurs du rapport et la sécurité (parties 5 et 6). Le dernier passage sur le gros volume, le 09/11/2026, donne 127 + 15 contrôles réussis, 0 erreur et 1 alerte attendue.

**Décision : GO.** Les critères sont remplis : aucun test bloquant en échec, réconciliation exacte, valeurs du rapport égales à la base, sécurité conforme.

## 9. Les questions probables du prof

**Pourquoi avoir commencé par les données et pas par les KPI ?**
C'est la consigne du cours, et le profilage nous a donné raison : PaySim ne permettait aucun KPI fiable sur la durée. Nous avons d'abord construit des données solides, puis choisi les KPI qu'elles permettaient de calculer juste.

**Comment avez-vous priorisé le travail ?**
Avec la méthode MoSCoW : d'abord les KPI justes, la traçabilité, le rapprochement et la sécurité, ensuite la prévision et les stress tests. Le temps réel et le cloud sont pour plus tard.

**Que fait dbt exactement ?**
dbt transforme des fichiers SQL en vues et en tables dans PostgreSQL, dans le bon ordre, puis lance les tests. Il ne stocke aucune donnée : tout se passe dans la base.

**Pourquoi séparer staging et intermediate ?**
Staging corrige le format de chaque système séparément, sans rien supprimer. Intermediate applique les règles communes aux 4 systèmes. Si une filiale change son format, on ne touche que son modèle staging.

**Comment détectez-vous les doublons ?**
Avec `row_number()` sur la référence d'opération dans un même système : la première occurrence est gardée, les autres sont écartées avec le motif « Doublon ».

**Pourquoi ne pas supprimer directement les mauvaises lignes ?**
Pour la traçabilité. Chaque ligne écartée garde son motif et sa provenance (fichier, ligne) : on peut renvoyer la liste à la filiale et prouver ce qu'on a retiré.

**Comment prouvez-vous que le nettoyage est juste ?**
Par le rapprochement avec le grand livre, jour par jour et filiale par filiale, et par l'ancrage sur les vrais dépôts publiés. Les deux passent.

**Que se passe-t-il si une filiale envoie un nouveau libellé ?**
La ligne est écartée avec le motif « Libellé inconnu », et l'alerte `alerte_rejets_inattendus` le signale. Il suffit d'ajouter le libellé à `ref_correspondance_libelles.csv`.

**Pourquoi une alerte sur le rouble ?**
La BCE ne publie plus son cours depuis mars 2022. Le test signale une série interrompue : c'est attendu, et le rouble est exclu des prévisions.

**104 tests, ce n'est pas trop pour un POC ?**
La plupart sont des contrôles simples de clés (unicité, valeurs non vides). Les 11 tests métier sont ceux qui comptent. Dans une banque, un chiffre non contrôlé n'est pas utilisable.

## 10. Les limites à assumer

- Les défauts sont injectés par nous : de vrais exports en auraient d'autres, qu'il faudrait découvrir au pilote.
- Le grand livre vient du même générateur que les opérations : le rapprochement prouve le nettoyage, pas la réalité des opérations.
- Les tables de correspondance sont tenues à la main.
- Les alertes ne sont pas envoyées automatiquement : il faut lire le journal.

## 11. Pour t'entraîner

1. Lance les tests seuls et lis le résultat :
   ```bash
   cd dbt
   dbt test --profiles-dir .
   ```
2. Affiche le lineage :
   ```bash
   dbt docs generate --profiles-dir .
   dbt docs serve --profiles-dir .
   ```
3. Dans pgAdmin, compte les rejets par motif :
   ```sql
   select motif_rejet, count(*) from intermediate.int_operations_rejetees group by 1 order by 2 desc;
   ```
4. Trouve un doublon et ses deux occurrences :
   ```sql
   select systeme_source, ref_operation, nom_fichier, num_ligne, motif_rejet
   from intermediate.int_operations_controlees
   where ref_operation in (select ref_operation from intermediate.int_operations_rejetees
                           where motif_rejet = 'Doublon' limit 1);
   ```
5. Lis `stg_sab__operations.sql` et explique chaque colonne à voix haute.
6. Prépare une démonstration de 2 minutes : `dbt test`, puis le lineage dans `dbt docs`, de `raw.src_sab` jusqu'à `fct_position_tresorerie_quotidienne`.

## 12. Avec qui tu travailles

| Partie | La frontière |
|---|---|
| 2. Données | Chaque défaut injecté a sa règle RG-NET ; le grand livre vient du générateur |
| 3. Chargement | Tu pars des tables `raw` ; le test de complétude compare `raw` au journal de chargement |
| 5. Modèle | Tes tables intermediate alimentent les faits ; `assert_dimensions_sans_mesure` protège son modèle |
| 1. Besoin | La recette et la décision GO sont reprises dans la conclusion ; tes priorités MoSCoW complètent son pilotage du projet |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| `dbt/dbt_project.yml` | La configuration : schémas, matérialisations, variables, référentiels |
| `dbt/profiles.yml` | La connexion à PostgreSQL |
| `dbt/models/sources.yml` | Les tables de `raw` et de `ml`, leurs tests et la fraîcheur des cours |
| `dbt/models/exposures.yml` | Le rapport Power BI au bout du lineage |
| `dbt/models/staging/stg_sab__operations.sql` et les 3 autres `stg_*__operations` | Le nettoyage du format de chaque système |
| `dbt/models/staging/stg_bce__taux_change.sql`, `stg_zf__ancrages.sql` | Les cours BCE et les dépôts réels |
| `dbt/models/staging/schema.yml`, `dbt/models/intermediate/schema.yml` | Les descriptions et les tests des modèles |
| `dbt/models/intermediate/int_operations_controlees.sql` | L'union des 4 systèmes et les règles de nettoyage |
| `dbt/models/intermediate/int_operations_nettoyees.sql`, `int_operations_rejetees.sql` | Les lignes retenues et les lignes écartées |
| `dbt/models/intermediate/int_mouvements_tresorerie.sql` | Les mouvements en devise et en euros |
| `dbt/models/intermediate/int_taux_change_journalier.sql` | Un cours pour chaque jour, avec le report et la rupture de série |
| `dbt/models/intermediate/int_encours_initial.sql` | Le point de départ de chaque filiale |
| `dbt/macros/normalisation.sql`, `tests_generiques.sql`, `generate_schema_name.sql` | Les macros |
| `dbt/seeds/ref_correspondance_libelles.csv`, `ref_correspondance_devises.csv`, `ref_types_transaction.csv` | Les tables de correspondance et les types d'opération |
| `dbt/tests/` | Les 11 tests métier |
| `dbt/models/marts/analyses/mart_qualite_sources.sql`, `mart_qualite_defauts.sql`, `mart_qualite_ancrage.sql` | Les marts de qualité |
| [docs/08](../08_etl_sources_et_nettoyage.md), [docs/02](../02_specifications_moe.md) | Les règles de nettoyage et le plan de tests |
