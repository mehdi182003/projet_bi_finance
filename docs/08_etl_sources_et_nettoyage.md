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
| REF_OPE | référence unique d'opération | `FR20240103-000652` |
| CODE_ETAB | entité (à traduire en filiale) | `ZF-FR`, `ZF-BE`, `ZF-FI` |
| DATE_OPE / HEURE_OPE | `jj/mm/aaaa` / `hh:mm:ss` | `31/12/2023` / `08:02:57` |
| NUM_CLIENT | sans tiret, parfois vide | `FR0002840` |
| LIBELLE_OPE | texte libre français, variantes | `PAIEMENT CB`, `Paiement CB`, `PRLV SEPA` |
| NB_OPE | opérations du lot | `100` |
| MONTANT | positif, virgule décimale | `1392,08` |
| SENS | `C` crédit (entrée) / `D` débit (sortie) | `C` |
| DEVISE | code non normalisé | `EUR`, `€`, `eur`, ` EUR` |
| IND_FRAUDE | `O` / `N` | `N` |
| STATUT | `VALIDE` / `ANNULE` | `ANNULE` |

### NORDIC — Suède, Danemark, Norvège (`nordic/<filiale>/NCB_<entité>_<aaaa-mm>.csv.gz`)
CSV séparé par `,`, **UTF-8 avec BOM**, point décimal.
- `booking_ts` : ISO 8601 en **UTC** (`2024-01-01T07:05:53Z`).
- `amount` : montant **signé** ; `amount_unit` = `MINOR` en Suède (montant en **öre**, ×100).
- `txn_type` : codes anglais, parfois en minuscules.
- `record_status` : `BOOKED` / `REVERSAL` ; `reversal_of` donne l'écriture extournée.

### AMERICORE — Canada, États-Unis (`americore/<filiale>/AMC_<entité>_<aaaamm>.csv.gz`)
CSV séparé par `,`, UTF-8.
- `TxnDate` au format **MM/JJ/AAAA** ; `TxnTime` en **hh:mm:ss AM/PM**.
- Montant dans **`DebitAmount` OU `CreditAmount`**, avec **séparateur de milliers** (`"1,669.35"`).
- `TxnCode` numérique (100 dépôt, 110 virement reçu, 200 retrait, 210 paiement carte, 220 prélèvement, 230 virement émis).
- `AccountNo` : zéros de tête parfois perdus (`US-209963`) ; comptes `TEST-…` mêlés à la production.

### DELTA — Côte d'Ivoire, Cameroun (`delta/<filiale>/DELTA_<entité>_<aaaamm>.csv.gz`)
CSV séparé par `;`, cp1252.
- **Ligne de titre** avant l'en-tête, et **ligne `TOTAL;<nb lignes>;<somme des montants>`** en pied de fichier.
- `DATEOPE` au format `aaaammjj`, `HEUREOPE` au format `hhmmss`.
- `MONTANT` entier (pas de centimes en franc CFA), toujours positif : le sens se déduit de la nature.
- `NATURE` sans norme : accents, abréviations, casse (`DÉPÔT ESPÈCES`, `DEP ESP`, `Retrait gab `).
- `DEVISE` : `XOF`, `XAF`, `FCFA`, `F CFA`, `F.CFA`.
- `SUSPICION` : `1`, `0` ou **vide**.
- La filiale n'est pas une colonne : elle se lit dans le nom du fichier.

### Référence comptable
`comptabilite/soldes_comptables_journaliers.csv` donne les crédits, débits et nombre d'opérations par filiale et par jour, issus du grand livre. C'est une source **indépendante** qui sert au rapprochement.

## 3. Règles de nettoyage

| Code | Règle | Couche / modèle |
|---|---|---|
| RG-NET-01 | Lecture du format physique : encodage, séparateur, ligne de titre et ligne de total ; tout est chargé en texte | Python, `chargement_sources_internes.py` |
| RG-NET-02 | Dates et heures multi-formats → horodatage (`jj/mm/aaaa`, `MM/JJ/AAAA AM/PM`, `aaaammjj`) | `stg_*__operations` |
| RG-NET-03 | Horodatages UTC → heure locale de la filiale (fuseau de `ref_filiales`) | `stg_nordic__operations` |
| RG-NET-04 | Montants : virgule décimale, séparateur de milliers, unités mineures (÷100), sens (C/D, signe, colonnes débit/crédit, nature) | `stg_*__operations` |
| RG-NET-05 | Libellés → type d'opération normalisé (majuscules, sans accents, espaces réduits, puis table `ref_correspondance_libelles`) | `int_operations_controlees` |
| RG-NET-06 | Devises → code ISO (`ref_correspondance_devises`) ; `FCFA` → XOF ou XAF selon la filiale ; contrôle devise = devise de la filiale | idem |
| RG-NET-07 | Doublons (même référence dans le même système : renvois, chevauchement des fichiers mensuels) → on garde la 1ʳᵉ occurrence | idem |
| RG-NET-08 | Exclusions métier : opérations annulées, comptes de test, extournes et écritures extournées | idem |
| RG-NET-09 | Identifiant client → `<FILIALE>-<7 chiffres>` (zéros restaurés) ; absent → `<FILIALE>-INCONNU` | idem |
| RG-NET-10 | Validité : filiale connue, date dans la période, montant > 0, sens cohérent avec le type | idem |
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

| Système | Lignes brutes | Retenues | Rejetées | Principaux défauts traités |
|---|---|---|---|---|
| SAB | 1 551 086 | 1 450 088 | 6,5 % | 97 971 doublons (chevauchement des fichiers mensuels), 3 027 annulations, 61 461 libellés et 31 226 devises corrigés |
| NORDIC | 629 499 | 625 909 | 0,6 % | 2 456 doublons, 567 extournes + 567 écritures extournées, 629 499 heures UTC converties, 293 039 montants en öre |
| AMERICORE | 579 625 | 577 100 | 0,4 % | 2 273 doublons, 252 comptes de test, 11 652 devises corrigées, zéros de tête restaurés |
| DELTA | 135 810 | 135 307 | 0,4 % | 503 doublons, 20 140 libellés et 6 741 devises corrigés, 13 456 indicateurs de fraude vides |
| **Total** | **2 896 020** | **2 788 404** | **3,7 %** | |

Ces indicateurs sont dans `marts.mart_qualite_sources` et sur la page « Qualité des données » du Power BI.

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
- **Reconstruire les exports** à partir des séries réelles : `python pipeline.py --regenerer` (nécessite PaySim).
