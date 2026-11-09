# Partie 3 : architecture, PostgreSQL et chargement

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **comment le projet est organisé techniquement** : pourquoi cette solution plutôt qu'une autre (la grille de choix et le SWOT), comment les données traversent les couches de l'entrepôt, comment Python charge les fichiers bruts dans PostgreSQL, et comment Power BI se branche sur l'entrepôt en toute sécurité. Tu es aussi la personne qui sait installer et lancer le projet.

**Diapos :** 4 (analyse du marché), 7 (la solution choisie, la grille de choix et les optimisations), 9 (SWOT).

**Fichiers :** `pipeline.py`, `etl/config.py`, `etl/db.py`, `etl/chargement_raw.py`, `etl/chargement_sources_internes.py`, `etl/sql/create_raw.sql`, `.env.example`, `docker-compose.yml`, `requirements.txt`, `powerbi/Cresus/` (connexion, rôles, format PBIP), `powerbi/generer_pbip.py`.

## À savoir dire en une minute

> Nous avons choisi une architecture ELT en couches. ELT veut dire qu'on charge d'abord les données telles quelles dans l'entrepôt, puis qu'on les transforme à l'intérieur. L'entrepôt est une base PostgreSQL organisée en couches : Bronze pour les données brutes, Silver pour les données nettoyées, Gold pour le schéma en étoile que lit Power BI. Python charge les 374 fichiers des filiales sans rien modifier, en texte, avec pour chaque ligne le fichier et le numéro de ligne d'origine. Le chargement est incrémental : un fichier déjà chargé et inchangé est ignoré grâce à son empreinte MD5. Ensuite, dbt transforme les données dans PostgreSQL. Un seul script, `pipeline.py`, enchaîne toutes les étapes. Sur le gros volume, 42,7 M de lignes se chargent en 11 minutes sur un simple PC. Power BI se branche ensuite sur le schéma `marts` : il importe seulement 15 tables, environ 10 Mo, et chaque responsable de filiale ne voit que sa filiale.

## 1. Les notions à maîtriser

### Bases de données

| Notion | En clair |
|---|---|
| **Base de données relationnelle** | Des données rangées en tables (lignes et colonnes) que l'on interroge en SQL |
| **SGBD** | Le logiciel qui gère la base : ici PostgreSQL |
| **Table** | Un tableau stocké sur disque : chaque ligne est un enregistrement, chaque colonne a un type |
| **Vue** | Une requête enregistrée sous un nom. Elle ne stocke rien : elle se recalcule à chaque lecture |
| **Schéma** | Un dossier qui regroupe des tables dans une base. Ici, un schéma par couche : `raw`, `staging`, `intermediate`, `marts`, `ml`, `referentiel` |
| **Type de colonne** | `text` (texte), `integer` et `bigint` (entiers), `numeric` (décimal exact), `double precision` (décimal à virgule flottante), `date`, `timestamp` (date et heure), `boolean` (vrai ou faux) |
| **Clé primaire** | La colonne qui identifie une ligne de façon unique, par exemple `nom_fichier` dans le journal de chargement |
| **SQL** | Le langage des bases de données. `select` lit, `where` filtre, `group by` regroupe, `join` relie deux tables |
| **Transaction** | Un groupe d'opérations validé en bloc : soit tout passe, soit rien |
| **`COPY`** | La commande PostgreSQL qui charge un fichier en masse, beaucoup plus vite que des `insert` ligne par ligne |
| **`ANALYZE`** | Met à jour les statistiques d'une table pour que PostgreSQL choisisse de bons plans de calcul |

### Entrepôt de données

| Notion | En clair |
|---|---|
| **Entrepôt de données (data warehouse)** | Une base conçue pour l'analyse : elle rassemble les données de plusieurs sources, nettoyées et historisées |
| **ETL** | Extract, Transform, Load : on transforme les données avant de les charger |
| **ELT** | Extract, Load, Transform : on charge d'abord les données brutes, puis on les transforme dans l'entrepôt. C'est notre choix |
| **Architecture médaillon** | Trois couches de qualité croissante : **Bronze** (brut), **Silver** (nettoyé), **Gold** (prêt pour l'analyse) |
| **Idempotence** | Relancer le traitement donne le même résultat, sans doublon |
| **Chargement incrémental (DELTA)** | On ne recharge que ce qui a changé. Le contraire est un rechargement complet (FULL) |
| **Empreinte MD5** | Un code calculé à partir du contenu d'un fichier. Si un seul octet change, l'empreinte change |
| **Traçabilité** | Pouvoir retrouver d'où vient chaque donnée : fichier, ligne, date de chargement |
| **Lineage** | Le chemin d'une donnée de la source au rapport, affiché par dbt |
| **Orchestration** | Lancer les étapes dans le bon ordre, et s'arrêter si l'une échoue |

### Environnement technique

| Notion | En clair |
|---|---|
| **Environnement virtuel Python (venv)** | Un dossier `.venv` qui contient les bibliothèques du projet, séparées du reste de l'ordinateur |
| **`requirements.txt`** | La liste des bibliothèques à installer avec `pip install -r requirements.txt` |
| **Variable d'environnement, `.env`** | Un réglage lu au lancement, par exemple le mot de passe de la base. `.env` n'est jamais mis dans Git |
| **Docker** | Un outil qui lance un logiciel (ici PostgreSQL) dans un conteneur, sans l'installer. Prévu mais non testé |

### Power BI côté technique

| Notion | En clair |
|---|---|
| **Mode Import** | Power BI copie les données dans le fichier. Rapide, mais il faut cliquer sur **Actualiser** pour avoir les nouvelles données |
| **RLS (Row-Level Security)** | Sécurité au niveau des lignes : chaque rôle ne voit que certaines lignes |
| **PBIP** | Le format projet de Power BI : un dossier de fichiers texte, versionnable dans Git |
| **TMDL** | Le format texte du modèle (tables, colonnes, relations, mesures, rôles) |
| **PBIR** | Le format texte du rapport (pages et visuels) |

## 2. L'architecture en couches

```
data/sources_internes/  374 fichiers CSV compressés des filiales (et data/sources/ pour le réel)
        │  Python : chargement tel quel, en texte (etl/chargement_sources_internes.py)
        ▼
PostgreSQL, base « cresus »
  raw           Bronze  8 tables   lignes brutes + fichier, ligne, date de chargement, journal   6,5 Go
  referentiel           7 tables   filiales, devises, taux, scénarios, correspondances (seeds dbt)
  staging       Silver  6 vues     un modèle par système : formats, fuseaux, unités, sens
  intermediate  Silver  3 tables, 3 vues   union, dédoublonnage, exclusions, rejets tracés   11 Go
  marts         Gold    20 tables  5 dimensions + 15 tables de faits                         137 Mo
  ml                    5 tables   sorties Python : prévisions, réserve, contrôle a posteriori
        ▼
Power BI : importe 15 tables de marts (environ 10 Mo)
```

**Qui écrit quoi :**
- Python écrit dans `raw` (chargement) et dans `ml` (prévisions).
- dbt écrit dans `referentiel`, `staging`, `intermediate` et `marts`.
- Power BI ne lit que `marts`.

**Pourquoi des couches.** Chaque couche a un rôle clair. Si un chiffre est faux, on remonte couche par couche jusqu'à la source. On peut tout reconstruire depuis la couche brute sans retoucher les fichiers. C'est aussi ce qu'attend BCBS 239 : des données de risque traçables.

**Pourquoi ELT.** PostgreSQL est très efficace pour transformer de gros volumes en SQL. Charger d'abord en brut garde une copie exacte de ce que les filiales ont envoyé : on peut toujours prouver ce qu'on a reçu.

## 3. Pourquoi ces outils

| Outil | Rôle | Pourquoi lui |
|---|---|---|
| **Python 3.13** | Extraction, génération, chargement, prévision, orchestration | Bibliothèques de données (pandas, numpy, statsmodels), gratuit, connu du groupe |
| **PostgreSQL 15** | L'entrepôt de données | Gratuit, robuste, traite 42,7 M de lignes sur un PC, SQL standard donc portable vers un entrepôt cloud |
| **dbt 1.12** | Les transformations SQL, les tests, la documentation | Versionne le SQL, gère l'ordre des modèles, teste, affiche le lineage (partie 4) |
| **Power BI Desktop** | Le tableau de bord | Déjà présent dans l'écosystème Microsoft de la banque, sécurité par filiale (partie 5) |

**L'analyse du marché (diapo 4).** Les grandes alternatives sont les entrepôts cloud (Snowflake, BigQuery, Synapse), le streaming et le calcul distribué (Kafka, Spark), et les outils de BI. Beaucoup d'outils savent afficher des chiffres : la vraie différence vient de la fiabilité des données.

### La grille de choix (diapo 7)

Trois solutions ont été comparées. Le **Must** est un critère éliminatoire : pouvoir tracer chaque opération et retomber sur le grand livre.

| Critère | Poids | A. Entrepôt + dbt + Power BI | B. Lakehouse + streaming (Spark, Kafka) | C. Power BI branché sur les exports |
|---|---|---|---|---|
| Must : traçabilité et rapprochement | Bloquant | Oui | Oui | Non |
| Fonctionnel | 25 % | 4 | 4 | 2 |
| Data / intégration | 25 % | 5 | 4 | 1 |
| Sécurité / gouvernance | 20 % | 4 | 3 | 2 |
| Performance / run | 15 % | 3 | 5 | 2 |
| TCO | 15 % | 5 | 1 | 4 |
| **Note pondérée sur 5** | | **4,25 : retenue** | 3,50 | Éliminée par le Must |

Calcul pour A : 4 × 0,25 + 5 × 0,25 + 4 × 0,20 + 3 × 0,15 + 5 × 0,15 = 4,25.

**Pourquoi A.** Le volume tient sur un poste, et les décisions de trésorerie sont quotidiennes : le temps réel (option B) coûterait cher sans rien apporter. L'option C, Power BI branché directement sur les fichiers, ne trace ni les rejets ni le rapprochement. Le SQL et les fichiers restent portables, donc un passage vers un entrepôt cloud reste possible.

### Le SWOT (diapo 9)

| Forces | Faiblesses |
|---|---|
| Sources officielles et gratuites (BCE, banques centrales) | 10 filiales aux systèmes différents (3 continents, 8 devises) |
| Outils open source peu coûteux, Power BI déjà dans l'écosystème Microsoft | Historique interne court ou différent selon les filiales |
| Règles versionnées et testées, donc traçables | Peu de compétences data science à la Trésorerie |
| Simulation interactive au lieu de tableurs figés | Modèles sensibles aux changements brutaux de situation |

| Opportunités | Menaces |
|---|---|
| Placer la liquidité qui dort : 1 M€ placé à 2 % rapporte 20 000 € par an | Rupture de série (rouble non coté depuis 2022) |
| Réduire le coût de couverture en ne couvrant que l'exposition nette | Réglementation (Bâle III, BCBS 239, RGPD, contrôle des changes en zone CFA) |
| Compensation entre filiales (netting, cash pooling) | Confiance excessive dans un chiffre unique : toujours montrer la fourchette |
| Stress tests attendus par le superviseur | Dévaluation du franc CFA, invisible dans l'historique |

### Les bibliothèques Python (`requirements.txt`)

| Bibliothèque | À quoi elle sert | Où |
|---|---|---|
| `pandas` | Lire et transformer des tableaux de données | Partout en Python |
| `numpy` | Le calcul numérique et les tirages aléatoires | Génération, prévision |
| `psycopg[binary]` | Se connecter à PostgreSQL et lancer `COPY` | Chargement |
| `SQLAlchemy` | Permettre à pandas de lire et d'écrire des tables | Prévision (`read_sql`, `to_sql`) |
| `statsmodels` | Le modèle de Holt-Winters | Prévision |
| `holidays` | Les jours fériés de chaque pays | Génération, prévision |
| `requests` | Appeler les API des banques centrales | Extraction |
| `python-dotenv` | Lire le fichier `.env` | `etl/config.py` |
| `kaggle` | Télécharger PaySim | Extraction, seulement avec `--regenerer` |
| `openpyxl` | Écrire le dictionnaire Excel | `docs/dictionnaire/` |
| `dbt-core`, `dbt-postgres` | dbt et son adaptateur pour PostgreSQL | Transformations (partie 4) |

## 4. L'orchestrateur : `pipeline.py`

Un seul script enchaîne toutes les étapes, dans cet ordre :

| Étape | Ce qu'elle fait | Code |
|---|---|---|
| `extract` | Lit les cours BCE et vérifie le cache des séries réelles | `etl/extraction_bce.py`, `etl/sources_reelles.py` |
| `generer` | Seulement avec `--regenerer` : recrée les exports des filiales | `etl/generateur_flux.py` (partie 2) |
| `load` | Charge les fichiers bruts dans `raw` | `etl/chargement_raw.py`, `etl/chargement_sources_internes.py` |
| `dbt` | Référentiels, modèles et tests | `dbt build --exclude tag:prevision` (partie 4 et 5) |
| `prevision` | Prévisions Python vers `ml`, puis contrôle sur janvier 2026 | `etl/prevision.py`, `etl/controle_a_posteriori.py` (partie 6) |
| `dbt_prev` | Marts de prévision et leurs tests | `dbt build --select tag:prevision` |

**Le code important :**

```python
def executer_dbt(*arguments: str, bloquant: bool = True) -> None:
    executable = shutil.which("dbt")
    ...
    if subprocess.run(commande, cwd=DOSSIER_DBT).returncode != 0:
        if bloquant:
            raise SystemExit(...)
```

Python lance dbt comme un programme externe. Si dbt échoue (un test bloquant en erreur), le pipeline s'arrête : on ne calcule pas de prévision sur des données fausses.

```python
options = ["--full-refresh"] if args.full_refresh or "generer" in args.etapes else []
```

Le fait principal est incrémental (partie 5). Après une régénération des données, il faut le reconstruire entièrement : c'est l'option `--full-refresh`.

```python
try:
    from etl.controle_a_posteriori import controler
    controler()
except Exception as exc:
    log.warning("Contrôle a posteriori ignoré : %s", exc)
```

Le contrôle sur janvier 2026 ne bloque pas le pipeline : s'il échoue, on est prévenu, mais le reste continue.

**Les commandes à connaître :**

```bash
python pipeline.py                                  # tout, sur le jeu léger (environ 7 min)
python pipeline.py --etapes dbt prevision dbt_prev  # seulement certaines étapes
python pipeline.py --regenerer --taille-lot 50      # gros volume (environ 1 h 10)
python pipeline.py --full-refresh                   # reconstruire aussi le fait incrémental
```

## 5. La configuration

`etl/config.py` lit le fichier `.env` et rassemble tous les réglages :

```python
PG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    ...
}
DOSSIER_SOURCES_INTERNES_ACTIF = RACINE / os.getenv("DOSSIER_SOURCES_INTERNES", ...)
```

- Les paramètres de connexion à PostgreSQL sont lus dans `.env`, avec des valeurs par défaut. dbt lit les mêmes variables dans `dbt/profiles.yml`.
- `DOSSIER_SOURCES_INTERNES` choisit le jeu de données : le jeu léger par défaut, ou `data/generees/lot_50` pour le gros volume.
- `etl/db.py` ouvre deux types de connexion : `psycopg` pour la commande `COPY`, et SQLAlchemy pour que pandas lise et écrive des tables.

## 6. Le chargement des fichiers bruts, ligne par ligne

C'est `etl/chargement_sources_internes.py`. Son principe : **aucune règle métier**, seulement le format physique de chaque système.

### Le format de chaque système

```python
FORMATS = {   # systeme : (sous-dossier, encodage, séparateur, ligne de titre, ligne de total)
    "SAB": ("sab", "cp1252", ";", False, False),
    "NORDIC": ("nordic", "utf-8-sig", ",", False, False),
    "AMERICORE": ("americore", "utf-8", ",", False, False),
    "DELTA": ("delta", "cp1252", ";", True, True),
}
```

`utf-8-sig` lit l'UTF-8 en retirant le BOM de NORDIC. DELTA a une ligne de titre au début et une ligne de total à la fin.

### Le journal de chargement

```sql
create table if not exists raw.journal_chargement (
    systeme_source text, nom_fichier text primary key, empreinte_md5 text,
    nb_lignes_lues integer, nb_lignes_annoncees integer, total_annonce numeric(24, 2), ...
);
```

Une ligne par fichier chargé, avec son empreinte MD5 et le nombre de lignes lues. Pour DELTA, on garde aussi ce que le pied de fichier annonce (nombre de lignes et total des montants). Ce journal sert au test de complétude de la partie 4.

### Le chargement incrémental

```python
deja = dict(cur.execute("select nom_fichier, empreinte_md5 from raw.journal_chargement").fetchall())
...
empreinte = hashlib.md5(chemin.read_bytes()).hexdigest()
if deja.get(chemin.name) == empreinte:
    ignores += 1
    continue
```

1. On lit dans le journal l'empreinte de chaque fichier déjà chargé.
2. Pour chaque fichier du dossier, on calcule son empreinte MD5.
3. Si elle est identique, le fichier n'a pas changé : on passe au suivant.
4. Sinon, on supprime ses anciennes lignes et on le recharge.

**Les fichiers disparus** sont aussi retirés de `raw`, pour qu'un changement de jeu de données (léger ou gros volume) ne laisse pas d'anciennes lignes.

### La lecture d'un fichier

```python
with gzip.open(chemin, "rb") as f:
    texte = f.read().decode(encodage)
lignes = texte.splitlines()
if titre:
    meta["ligne_titre"], lignes = lignes[0], lignes[1:]
if total and lignes and lignes[-1].startswith("TOTAL"):
    _, nb, montant = lignes[-1].split(sep)[:3]
    ...
lignes = lignes[:1] + [l for l in lignes[1:] if l != lignes[0]]
paquets = pd.read_csv(io.StringIO("\n".join(lignes)), sep=sep, dtype=str, keep_default_na=False,
                      chunksize=TAILLE_PAQUET)
```

1. On décompresse et on décode avec le bon encodage.
2. On met de côté la ligne de titre et la ligne de total de DELTA.
3. On retire les en-têtes répétés au milieu du fichier (DELTA les répète toutes les 5 000 lignes).
4. On lit le CSV **en texte** (`dtype=str`) : aucune conversion, aucun nombre interprété. `keep_default_na=False` empêche pandas de transformer `NULL` ou `N/A` en valeur vide : le nettoyage doit voir ce que la filiale a vraiment écrit.
5. On lit par paquets de 500 000 lignes pour ne pas saturer la mémoire.

### La création de table et la dérive de schéma

```python
defs = ", ".join(f'"{c}" text' for c in colonnes)
cur.execute(f"create table if not exists {table} ({defs}, _fichier text, _ligne integer, ...)")
for c in colonnes:
    cur.execute(f'alter table {table} add column if not exists "{c}" text')
```

Toutes les colonnes sont en texte. On ajoute trois colonnes de traçabilité : le fichier, le numéro de ligne et la date de chargement. Si un export récent contient une nouvelle colonne (NORDIC ajoute `channel` en 2025), elle est ajoutée à la table : c'est la gestion de la **dérive de schéma**.

### La copie en base

```python
with cur.copy(f"copy {table} ({colonnes}) from stdin with (format csv)") as copie:
    copie.write(tampon.getvalue())
```

Chaque paquet est envoyé à PostgreSQL avec `COPY`, la méthode la plus rapide. Le journal est ensuite mis à jour avec `insert … on conflict do update` : on insère la ligne du fichier, ou on la remplace si elle existe déjà.

### Les petits fichiers

Le grand livre (`raw.soldes_comptables`) et les ancrages réels (`raw.ancrages_zf`) sont petits : ils sont vidés (`truncate`) et rechargés en entier à chaque fois. Les cours BCE (`raw.bce_taux_change`) le sont aussi, par `etl/chargement_raw.py`. Enfin, `analyze` met à jour les statistiques des tables.

## 7. Les performances

**Mesuré sur 6 cœurs et 15 Go de RAM, gros volume :**

| Étape | Durée |
|---|---|
| Génération | 16 min |
| Chargement | 11 min |
| `dbt build` | 39 à 50 min |
| Pipeline complet | environ 1 h 10 |

La base fait 17 Go ; il faut prévoir environ 30 Go libres, car PostgreSQL crée des fichiers temporaires pendant les gros calculs.

**Les 3 optimisations (diapo 7) :**
1. **Chargement par paquets** avec `COPY` : 42,7 M de lignes en 11 minutes.
2. **Chargement incrémental (DELTA)** : seuls les fichiers modifiés sont rechargés, grâce au MD5.
3. **Agrégation et incrémental** : 40,7 M de lignes résumées en environ 756 000 lignes horaires ; Power BI n'importe qu'environ 10 Mo.

**Un réglage pour Power BI.** Power BI ne sait pas lire un `numeric` de plus de 28 chiffres. Une macro dbt (`dbt/macros/compatibilite_power_bi.sql`) convertit donc toutes les colonnes `numeric` des marts en `double precision` à la fin de leur construction, et un test le vérifie.

## 8. Le branchement de Power BI

Power BI ne lit pas les fichiers des filiales : il se connecte à PostgreSQL et ne lit que le schéma `marts`.

### L'import et l'actualisation

- **Mode Import.** Power BI copie dans son fichier les 15 tables utiles, environ 10 Mo : 4 dimensions (`dim_date`, `dim_filiale`, `dim_devise`, `dim_scenario_stress`) et 11 faits. Restent dans PostgreSQL : `fct_flux_tresorerie_horaire`, `fct_situation_initiale_filiale`, `fct_taux_change`, `mart_qualite_defauts` et `dim_type_transaction`.
- **La connexion.** Chaque table est lue par une petite requête Power Query (langage M), écrite dans son fichier TMDL. `ServeurPostgres` et `BasePostgres` sont deux paramètres du modèle, `localhost:5432` et `cresus` par défaut.
- **L'actualisation.** Après chaque lancement du pipeline, on clique sur **Actualiser**. La première fois, on choisit l'onglet **Base de données** pour saisir l'utilisateur et le mot de passe PostgreSQL, puis on clique sur **OK** au message sur le chiffrement : la base est sur le PC, rien ne passe par Internet.
- **Les types.** Les colonnes arrivent en `double precision` grâce à la macro de la section précédente ; un `numeric` de plus de 28 chiffres bloquait l'import.

La requête de connexion, pour `dim_filiale` :

```
Source = PostgreSQL.Database(ServeurPostgres, BasePostgres),
Donnees = Source{[Schema="marts",Item="dim_filiale"]}[Data]
```

### La sécurité par filiale (RLS)

| Rôle | Filtre | Ce qu'il voit |
|---|---|---|
| Direction groupe | Aucun | Tout le groupe |
| Filiale France | `dim_filiale[code_filiale] = "FR"` et `dim_devise[code_devise] = "EUR"` | La France seulement : 1,84 Md€ de position, 23 jours sous 100 %, pas de VaR |
| Filiale États-Unis | `dim_filiale[code_filiale] = "US"` et `dim_devise[code_devise] = "USD"` | Les États-Unis seulement : 572 M€, 44 jours sous 100 %, VaR de 8,49 M€ |

Le filtre posé sur la dimension descend vers tous les faits par les relations. Pour tester : **Modélisation → Afficher comme rôles**, clique sur le **nom** du rôle (pas sur la case), puis **OK**. En production, il faudrait un rôle par filiale, alimenté par les groupes de l'annuaire de l'entreprise.

### Le format PBIP

```
powerbi/Cresus/
  Cresus.pbip                 le fichier à ouvrir
  Cresus.SemanticModel/       le modèle en TMDL : tables/, relationships.tmdl, roles/
  Cresus.Report/              le rapport en PBIR : une page et un visuel par dossier
```

Tout est en texte : Git montre précisément ce qui change. Le cache des données (`.pbi/`) n'est pas versionné. `powerbi/generer_pbip.py` peut régénérer le projet entier à partir de la base et de `mesures_dax.dax`, mais il demande le SDK .NET 8 (outil TomTool). Les dernières modifications ont été faites directement dans les fichiers TMDL, puis vérifiées dans Power BI Desktop.

**Comment `generer_pbip.py` fabrique le projet Power BI.**
1. Il lit dans PostgreSQL les colonnes et les types des 15 tables à importer.
2. Il construit le modèle : les tables, les 20 relations, les 3 rôles, les 4 paramètres What-if et les mesures de `powerbi/mesures_dax.dax`.
3. Il le convertit en TMDL avec TomTool, un petit programme .NET (`powerbi/outils/TomTool/`) qui utilise la bibliothèque officielle de Microsoft et vérifie que le modèle est valide.
4. Il écrit les 5 pages et leurs 37 visuels, avec le thème de couleurs `theme_cresus.json`, puis les vérifie avec les schémas publiés par Microsoft.

## 9. Installer et lancer le projet

Le détail est dans [docs/09](../09_procedure_pas_a_pas.md). En résumé, dans PowerShell :

```powershell
git clone https://github.com/mehdi182003/projet_bi_finance.git cresus
cd cresus
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE cresus"
python pipeline.py
```

La commande doit finir par `Pipeline terminé`, avec `ERROR=0` dans le journal de dbt. Sans le venv activé, Python ne trouve pas dbt (« dbt introuvable »).

## 10. Travailler en équipe avec Git et GitHub

Le code est dans un dépôt Git, partagé sur GitHub (`mehdi182003/projet_bi_finance`). Les 6 membres y sont invités comme collaborateurs.

| Notion | En clair |
|---|---|
| **Commit** | Une version enregistrée, avec un message qui dit ce qui change |
| **Branche** | Une copie de travail séparée, pour modifier sans toucher à la version principale (`main`) |
| **Pull request (PR)** | La demande de fusionner une branche dans `main`, relue avant d'être acceptée |
| **`.gitignore`** | La liste de ce qui n'est jamais envoyé : `.env`, PaySim, le gros volume, les caches de dbt et de Power BI |

```bash
git pull                          # récupérer la dernière version
git switch -c ma-branche          # créer une branche pour son travail
git add docs/fiches               # préparer les fichiers modifiés
git commit -m "Compléter la fiche 3"
git push -u origin ma-branche     # envoyer la branche, puis ouvrir une pull request sur GitHub
```

Un exemple réel : la revue des dimensions et des faits a été faite par Mokhmad sur la branche `moe/dimensions-faits-dictionnaire`, relue, complétée, puis fusionnée dans `main` par la pull request n° 1.

## 11. Les questions probables du prof

**Quelle différence entre ETL et ELT, et pourquoi ELT ?**
En ETL, on transforme avant de charger ; en ELT, on charge le brut puis on transforme dans l'entrepôt. Nous gardons ainsi une copie exacte de ce que les filiales ont envoyé, et PostgreSQL fait les transformations en SQL, ce qui est rapide et traçable.

**À quoi servent les couches Bronze, Silver et Gold ?**
Bronze garde le brut, Silver contient les données nettoyées et contrôlées, Gold contient le schéma en étoile prêt pour l'analyse. En cas d'erreur, on remonte couche par couche.

**Pourquoi tout charger en texte ?**
Pour ne rien perdre ni rien interpréter au chargement. Une date mal écrite ou un montant avec une parenthèse doit arriver tel quel dans `raw`, puis être corrigé et tracé par dbt.

**Comment évitez-vous les doublons si on relance le pipeline ?**
Le chargement est idempotent : un fichier inchangé est ignoré grâce à son empreinte MD5, et un fichier modifié est d'abord supprimé de la table, puis rechargé.

**Que se passe-t-il si une filiale ajoute une colonne ?**
Le chargeur l'ajoute à la table brute (`alter table … add column if not exists`). Les anciennes lignes ont la colonne vide.

**Pourquoi PostgreSQL et pas un entrepôt cloud ?**
Le volume tient sur un PC et c'est gratuit. Le SQL reste standard, donc une migration vers Snowflake ou BigQuery reste possible si le volume grandit.

**Pourquoi pas d'ordonnanceur comme Airflow ?**
C'est un POC lancé à la main. Pour une mise en production, il faudrait un ordonnanceur et une supervision : c'est dans les prérequis et les limites.

**Que contient le schéma `ml` ?**
Les 5 tables écrites par Python : les prévisions de trésorerie et de change, le backtest, la réserve optimale et le contrôle sur janvier 2026. dbt les reprend ensuite dans des marts.

**Pourquoi pas une solution cloud ou temps réel ?**
Le volume tient sur un PC et les décisions de trésorerie se prennent une fois par jour. Le temps réel coûterait cher sans rien apporter, d'où la note TCO de 1 pour l'option B.

**Comment avez-vous fixé les notes de la grille ?**
Ce sont des appréciations du groupe, pondérées selon la grille du cours. Le Must, lui, n'est pas discutable : sans rapprochement au grand livre, aucune banque n'accepterait les chiffres.

**Pourquoi ne pas importer toutes les tables dans Power BI ?**
Pour garder le rapport léger : 15 tables, environ 10 Mo. Le détail horaire et le catalogue des défauts se consultent dans la base.

**Comment fonctionne la sécurité ?**
Chaque rôle filtre `dim_filiale` et `dim_devise`. Le filtre descend vers tous les faits par les relations. Nous l'avons vérifié dans Power BI et par des requêtes DAX sous chaque rôle.

## 12. Les limites à assumer

- Le parcours Docker n'a pas été testé.
- Le traitement se lance à la main : pas d'ordonnanceur ni d'alertes.
- Le chargement lit chaque fichier en entier en mémoire avant de le découper : il suffit ici, mais pas pour des fichiers de plusieurs Go.
- Tout tourne sur un seul PC, sans sauvegarde ni haute disponibilité.
- Le fichier Power BI se rafraîchit à la main ; en production, il faudrait le publier et planifier l'actualisation.
- `generer_pbip.py` n'a pas été rejoué depuis les dernières modifications, faute de SDK .NET sur le PC de test.
- Seuls 3 rôles de sécurité existent, pour l'exemple.

## 13. Pour t'entraîner

1. Installe le projet sur ton PC en suivant [docs/09](../09_procedure_pas_a_pas.md) et lance `python pipeline.py`.
2. Dans pgAdmin, ouvre la base `cresus` et parcours les 6 schémas.
3. Lance ces requêtes et explique le résultat :
   ```sql
   select systeme_source, count(*) as fichiers, sum(nb_lignes_lues) as lignes
   from raw.journal_chargement group by 1;

   select _fichier, _ligne, * from raw.src_delta limit 5;
   ```
4. Relance `python pipeline.py --etapes load` et vérifie dans le journal que les fichiers sont « déjà à jour ».
5. Lis `pipeline.py` en entier : il ne fait que 115 lignes.
6. Refais le calcul de la note 4,25 de l'option A dans la grille de choix.
7. Dans Power BI, teste le rôle Filiale France (**Modélisation → Afficher comme rôles**, clique sur le nom du rôle puis **OK**) et retrouve 1,84 Md€ et 162,6 %.

## 14. Avec qui tu travailles

| Partie | La frontière |
|---|---|
| 2. Données | Tu charges ses fichiers : formats, encodages, lignes de titre et de total |
| 4. Nettoyage | dbt part de tes tables `raw` ; le test de complétude compare `raw` à ton journal |
| 1. Besoin | Ta grille utilise son TCO ; ton SWOT reprend ses gains |
| 5. Modèle | Tu branches Power BI sur ses tables ; elle explique les relations et les mesures DAX. La macro qui convertit les `numeric` ; le fait incrémental et `--full-refresh` |
| 6. Prévision | Python lit `marts` et écrit dans `ml` |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| `pipeline.py` | L'orchestrateur : il lance les étapes dans l'ordre |
| `etl/__init__.py` | Un fichier vide qui fait du dossier `etl` un paquet Python, pour pouvoir écrire `from etl.config import …` |
| `etl/config.py` | Les réglages : chemins, connexion, paramètres |
| `etl/db.py` | Les deux connexions à PostgreSQL |
| `etl/chargement_raw.py` | La création des schémas `raw` et `ml`, le chargement des cours BCE |
| `etl/sql/create_raw.sql` | Le SQL qui crée les tables brutes |
| `etl/chargement_sources_internes.py` | Le chargement incrémental des fichiers des filiales |
| `.env.example` | Le modèle du fichier de réglages |
| `docker-compose.yml` | PostgreSQL lancé par Docker (non testé) |
| `requirements.txt` | Les bibliothèques Python |
| `.gitignore` | Ce qui n'est jamais mis dans Git |
| `dbt/macros/compatibilite_power_bi.sql` | La conversion des `numeric` pour Power BI |
| `powerbi/Cresus/Cresus.pbip` | Le fichier à ouvrir dans Power BI |
| `powerbi/Cresus/Cresus.SemanticModel/definition/expressions.tmdl` | Les paramètres de connexion : serveur et base |
| `powerbi/Cresus/Cresus.SemanticModel/definition/roles/` | Les 3 rôles de sécurité |
| `powerbi/generer_pbip.py` | La génération du projet Power BI |
| `powerbi/outils/TomTool/` | Le petit programme .NET qui écrit le TMDL |
| `README.md`, [docs/09](../09_procedure_pas_a_pas.md) | La présentation du dépôt et la procédure de lancement |
