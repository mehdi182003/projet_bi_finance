# 08 — ETL : sources brutes des filiales, nettoyage et entrepôt de données

## 1. Architecture de la chaîne (Python → PostgreSQL → dbt → Power BI)

| Couche | Où | Outil | Contenu | Principe |
|---|---|---|---|---|
| Sources | `data/sources_internes/` (Git, 360 fichiers mensuels compressés, 49 Mo) | — | Exports bruts des 4 systèmes bancaires des filiales | Données « sales », hétérogènes |
| **Bronze** | PostgreSQL, schéma `raw` | Python (`etl/chargement_sources_internes.py`) | Lignes brutes **en texte**, telles que reçues + fichier, ligne, date de chargement | Zone immuable, traçabilité, chargement incrémental idempotent (empreinte MD5) |
| **Argent** | PostgreSQL, schémas `staging` puis `intermediate` | dbt (SQL) | `staging` : un modèle par système (typage, formats, fuseaux, unités, sens). `intermediate` : union, normalisation, dédoublonnage, exclusions, rejets tracés | Une règle = un commentaire `RG-NET-xx` + un test |
| **Or** | PostgreSQL, schéma `marts` | dbt (SQL) | **Schéma en étoile** : dimensions conformes + faits au grain défini, marts d'analyse | Modèle dimensionnel (Kimball) |
| Prédictif | PostgreSQL, schéma `ml` | Python | Prévisions, réserve optimale, contrôle a posteriori | Résultats réinjectés dans des marts dbt |
| Restitution | `powerbi/Cresus/Cresus.pbip` | Power BI | Import du schéma `marts` | Mesures DAX centralisées |

**dbt ne stocke rien** : il compile du SQL et l'exécute **dans** PostgreSQL, qui est le data warehouse. dbt apporte en plus les dépendances entre modèles, les tests, la documentation et le lignage (`dbt docs serve`).

## 2. Les 4 systèmes sources (dictionnaire des données brutes)

### SAB — France, Benelux, Finlande (`data/sources_internes/sab/<filiale>/SAB_<entité>_<aaaamm>.csv.gz`)
CSV séparé par `;`, encodage **cp1252**, **virgule décimale**.

| Colonne | Format | Exemple |
|---|---|---|
| REF_OPE | référence unique d'opération, parfois avec espaces de bord | `FR20240103-000652`, ` FR20240103-000652  ` |
| CODE_ETAB | entité (à traduire en filiale) | `ZF-FR`, `ZF-BE`, `ZF-FI` |
| DATE_OPE / HEURE_OPE | `jj/mm/aaaa` puis, **après la migration de juillet 2024**, `aaaa-mm-jj` / `hh:mm:ss` | `31/12/2023`, `2024-07-01` / `08:02:57` |
| NUM_CLIENT | sans tiret, parfois vide ou codé `NULL`, `N/A`, `?`, `0000000` | `FR0002840` |
| LIBELLE_OPE | texte libre français, variantes | `PAIEMENT CB`, `Paiement CB`, `PRLV SEPA` |
| NB_OPE | opérations du lot | `50` |
| MONTANT | positif, virgule décimale ; espace insécable comme séparateur de milliers dans les fichiers retouchés sous Excel | `1392,08`, `1 392,08` |
| SENS | `C` crédit (entrée) / `D` débit (sortie) | `C` |
| DEVISE | code non normalisé | `EUR`, `€`, `eur`, ` EUR` |
| IND_FRAUDE | `O` / `N` | `N` |
| STATUT | `VALIDE` / `ANNULE` | `ANNULE` |

Lignes en plus : vérifications de carte à `0,00` (contrôle de validité au TPE, sans effet comptable).

### NORDIC — Suède, Danemark, Norvège (`nordic/<filiale>/NCB_<entité>_<aaaa-mm>.csv.gz`)
CSV séparé par `,`, **UTF-8 avec BOM**, point décimal.
- `booking_ts` : ISO 8601 en **UTC** (`2024-01-01T07:05:53Z`).
- `amount` : montant **signé** ; `amount_unit` = `MINOR` en Suède (montant en **öre**, ×100).
- `txn_type` : codes anglais, parfois en minuscules.
- `entity` : parfois en minuscules ou avec des espaces (`se01`, ` SE01`).
- `record_status` : `BOOKED` / `REVERSAL` / **`PENDING`** ; `reversal_of` donne l'écriture extournée. `PENDING` = pré-autorisation carte (montant estimé, jusqu'à +30 %) émise quelques minutes avant l'opération comptabilisée.
- **Dérive de schéma** : à partir de janvier 2025, une colonne `channel` (`CARD`, `ATM`, `BATCH`, `ONLINE`, `BRANCH`) est insérée au milieu du fichier.

### AMERICORE — Canada, États-Unis (`americore/<filiale>/AMC_<entité>_<aaaamm>.csv.gz`)
CSV séparé par `,`, UTF-8.
- `TxnDate` au format **MM/JJ/AAAA** ; `TxnTime` en **hh:mm:ss AM/PM**.
- Montant dans **`DebitAmount` OU `CreditAmount`**, avec **séparateur de milliers** (`"1,669.35"`), parfois au **format comptable** (`"(1,669.35)"` en débit) ou avec le **symbole** de la devise (`"US$1,669.35"`, `"C$…"`).
- `TxnCode` numérique (100 dépôt, 110 virement reçu, 200 retrait, 210 paiement carte, 220 prélèvement, 230 virement émis).
- `AccountNo` : zéros de tête parfois perdus (`US-209963`), valeurs nulles codées ; comptes `TEST-…` mêlés à la production.
- `Entity` : parfois en minuscules ou avec des espaces.
- **Données tardives** : les opérations du dernier jour du mois passées après la clôture de 18 h sont livrées dans le fichier du mois suivant (y compris un fichier de janvier 2026 pour le 31/12/2025).

### DELTA — Côte d'Ivoire, Cameroun (`delta/<filiale>/DELTA_<entité>_<aaaamm>.csv.gz`)
CSV séparé par `;`, cp1252.
- **Ligne de titre** avant l'en-tête, et **ligne `TOTAL;<nb lignes>;<somme des montants>`** en pied de fichier.
- `DATEOPE` au format `aaaammjj`, `HEUREOPE` au format `hhmmss`.
- `MONTANT` entier (pas de centimes en franc CFA), toujours positif : le sens se déduit de la nature.
- `NATURE` sans norme : accents, abréviations, casse (`DÉPÔT ESPÈCES`, `DEP ESP`, `Retrait gab `), et **encodage cassé** sur une partie des lignes (texte UTF-8 relu en cp1252 par un maillon de la chaîne : `DÃ‰PÃ”T ESPÃˆCES`).
- `DEVISE` : `XOF`, `XAF`, `FCFA`, `F CFA`, `F.CFA`.
- `SUSPICION` : `1`, `0` ou **vide**.
- La filiale n'est pas une colonne : elle se lit dans le nom du fichier.
- État « paginé » : l'**en-tête est répété** toutes les 5 000 lignes.
- Lignes en plus : vérifications de carte à `0` FCFA.

### Défauts communs aux 4 systèmes
- **Fichiers renvoyés** : environ 3 % des fichiers mensuels sont livrés une seconde fois (`…_v2.csv.gz`), avec le même contenu.
- Doublons de lignes, valeurs nulles codées de plusieurs façons dans l'identifiant client.

### Référence comptable
`comptabilite/soldes_comptables_journaliers.csv` donne les crédits, débits et nombre d'opérations par filiale et par jour, issus du grand livre. C'est une source **indépendante** qui sert au rapprochement.

## 3. Règles de nettoyage

| Code | Règle | Couche / modèle |
|---|---|---|
| RG-NET-01 | Lecture du format physique : encodage, séparateur, ligne de titre, ligne de total, **en-têtes répétés** écartés, **colonnes nouvelles** ajoutées à la table brute (dérive de schéma) ; tout est chargé en texte. Codes entité comparés en majuscules sans espaces de bord | Python, `chargement_sources_internes.py` ; `stg_*__operations` |
| RG-NET-02 | Dates et heures multi-formats → horodatage (`jj/mm/aaaa` et `aaaa-mm-jj` après migration, `MM/JJ/AAAA AM/PM`, `aaaammjj`) | `stg_*__operations` |
| RG-NET-03 | Horodatages UTC → heure locale de la filiale (fuseau de `ref_filiales`) | `stg_nordic__operations` |
| RG-NET-04 | Montants : virgule décimale, séparateurs de milliers (virgule, espace, espace insécable), format comptable `(…)`, symbole de devise, unités mineures (÷100), sens (C/D, signe, colonnes débit/crédit, nature) | `stg_*__operations` |
| RG-NET-05 | Libellés → type d'opération normalisé (majuscules, sans accents, espaces réduits, puis table `ref_correspondance_libelles`, qui contient aussi les libellés à l'encodage cassé) | `int_operations_controlees` |
| RG-NET-06 | Devises → code ISO (`ref_correspondance_devises`) ; `FCFA` → XOF ou XAF selon la filiale ; contrôle devise = devise de la filiale | idem |
| RG-NET-07 | Doublons (même référence, après `trim`, dans le même système : renvois de lignes, chevauchement des fichiers mensuels, fichiers renvoyés `_v2`) → on garde la 1ʳᵉ occurrence | idem |
| RG-NET-08 | Exclusions métier : opérations annulées, comptes de test, extournes et écritures extournées, pré-autorisations carte en attente (`PENDING`) | idem |
| RG-NET-09 | Identifiant client → `<FILIALE>-<7 chiffres>` (zéros restaurés) ; absent ou codé `NULL`, `N/A`, `?`, `0000000` → `<FILIALE>-INCONNU` | idem |
| RG-NET-10 | Validité : filiale connue, date dans la période, montant > 0 (vérifications de carte à 0 : motif connu « Opération à montant nul »), sens cohérent avec le type | idem |
| RG-NET-11 | Indicateur de fraude vide → non suspect (compté comme valeur manquante) | `stg_delta__operations` |

**Aucune suppression silencieuse** : chaque ligne brute reste dans `intermediate.int_operations_controlees`, avec son `motif_rejet`. Les rejets sont consultables dans `int_operations_rejetees`.

## 4. Contrôles de l'ETL (tests dbt)

| Test | Ce qu'il garantit | Résultat |
|---|---|---|
| `assert_completude_fichiers` | Lignes en base = lignes lues ; pour DELTA, lignes et total = pied de fichier | ✅ |
| `assert_rapprochement_comptable` | Pour chaque filiale et chaque jour, crédits, débits et nombre d'opérations nettoyés = grand livre (10 960 jours-filiales) | ✅ |
| `assert_ancrage_depots_reels` | Encours reconstitué = encours réel publié par les banques centrales (491 dates) | ✅ |
| `unique` sur `ref_operation` nettoyée | Plus aucun doublon | ✅ |
| `alerte_rejets_inattendus` (alerte) | Signale tout libellé inconnu, devise ou sens incohérent (changement de format chez une filiale) | 0 cas |

**Vérification finale** : après nettoyage, le nombre d'opérations retenues égale exactement celui des opérations réelles, filiale par filiale (écart nul pour les 10).

## 5. Ce que l'ETL a détecté et corrigé (2023-2025)

Gros volume local (`--taille-lot 50`, `data/generees/lot_50/`, 374 fichiers mensuels, 586 Mo compressés), mesuré le 31/10/2026 :

| Système | Lignes brutes | Retenues | Rejetées | Principaux défauts traités |
|---|---|---|---|---|
| SAB | 21 460 324 | 20 272 872 | 5,5 % | 1 138 811 doublons (chevauchement des fichiers mensuels, fichiers renvoyés), 42 001 annulations, 6 640 vérifications de carte à 0 ; corrigés : 810 902 libellés, 405 887 devises, 497 388 formats (espaces insécables Excel, références avec espaces), 141 748 clients manquants ou codés nuls |
| NORDIC | 7 628 016 | 7 143 211 | 6,4 % | 379 604 doublons (dont 6 fichiers renvoyés), 91 029 pré-autorisations `PENDING`, 7 086 extournes + 7 086 écritures extournées ; corrigés : 285 212 libellés, 142 987 devises, 142 024 codes entité, heures UTC, montants en öre |
| AMERICORE | 7 590 087 | 7 472 003 | 1,6 % | 114 381 doublons, 3 703 comptes de test ; corrigés : 494 576 formats (montants comptables `(…)`, symboles `US$` / `C$`, codes entité), 149 274 devises, 52 152 clients |
| DELTA | 5 990 929 | 5 861 243 | 2,2 % | 128 893 doublons, 793 vérifications de carte à 0 ; corrigés : 877 624 libellés (dont 2 337 à l'encodage cassé), 292 139 devises, 586 197 indicateurs de fraude vides, en-têtes répétés écartés au chargement |
| **Total** | **42 669 356** | **40 749 329** | **4,5 %** | |

Les lignes retenues égalent **exactement** les opérations réelles générées (écart nul pour chaque système). Ces indicateurs sont dans `marts.mart_qualite_sources`, `marts.mart_qualite_defauts` (catalogue par type de défaut) et sur la page « Qualité des données » du Power BI.

Cas réel rencontré pendant la mise au point : le passage à l'heure d'hiver suédois (29/10/2023 et 27/10/2024) rend l'heure 02:00-03:00 ambiguë. Deux paiements sortaient sans horodatage UTC et cassaient le rapprochement de ces deux jours. Le générateur rattache désormais l'heure en double à l'heure d'été, comme le ferait un système stockant en UTC.

## 6. Modèle dimensionnel (schéma en étoile, couche or)

| Table | Type | Grain | Additivité |
|---|---|---|---|
| `dim_date` | dimension conforme | 1 jour | — |
| `dim_filiale` | dimension conforme (SCD type 1, clé métier stable) | 1 filiale | — |
| `dim_devise` | dimension conforme (code ISO 4217) | 1 devise | — |
| `dim_type_transaction` | dimension conforme | 1 type normalisé | — |
| `dim_scenario_stress` | dimension de référence | 1 scénario | — |
| `fct_flux_tresorerie_horaire` | fait transactionnel agrégé, **incrémental** | heure × filiale × type × fraude × gros ticket | additif |
| `fct_position_tresorerie_quotidienne` | fait instantané périodique | jour × filiale | **semi-additif** (on ne somme pas une position dans le temps : DAX « dernier jour ») |
| `fct_taux_change` | fait instantané périodique | jour × devise | non additif |
| `mart_*` | marts d'analyse (agrégats, prévisions, qualité) | défini dans `models/marts/schema.yml` | — |

Choix de modélisation :
- **Clés métier stables comme clés de dimension** (codes ISO, codes filiale) : elles ne changent pas et n'ont pas besoin d'historisation sur la période. Une clé de substitution s'imposerait avec un historique de type 2.
- **Dimensions conformes** : la même `dim_date` et la même `dim_filiale` filtrent tous les faits, ce qui permet de croiser flux, positions, prévisions et qualité.
- **Grain documenté** dans `models/marts/schema.yml` (`meta.grain`), visible dans `dbt docs`.
- **Exposition** : le tableau de bord Power BI est déclaré dans `models/exposures.yml` et apparaît en bout de lignage dans `dbt docs`.

## 7. Exploitation
- `python pipeline.py` : chargement incrémental (seuls les fichiers nouveaux ou modifiés sont rechargés), puis transformations, tests et prévisions.
- **Nouveau mois** : déposer les exports des filiales dans `data/sources_internes/` et relancer.
- **Fichier corrigé renvoyé par une filiale** : il est rechargé automatiquement (son empreinte MD5 a changé). S'il porte sur un mois ancien : `dbt build --full-refresh --select fct_flux_tresorerie_horaire`.
- **Reconstruire les exports** à partir des séries réelles : `python pipeline.py --regenerer` (nécessite PaySim). À graine égale, le contenu est identique au jeu versionné (vérifié sur les 360 fichiers et les soldes comptables).
- **Gros volume** : `python pipeline.py --regenerer --taille-lot 10` → `data/generees/lot_10/` (~29 M de lignes, non versionné). Le chargeur lit les fichiers par paquets de 500 000 lignes et le générateur traite une filiale à la fois, pour borner la mémoire.
