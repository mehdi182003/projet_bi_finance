# 09 — Procédure pas à pas : lancer tout le projet sur son PC

Ce guide part d'un PC Windows sans rien d'installé et va jusqu'au rapport Power BI vérifié.
Toutes les commandes se tapent dans **PowerShell**.

```
Python (données sales) → PostgreSQL (raw) → dbt (nettoyage, étoile, tests) → Python (prévisions) → dbt → Power BI
```

## 1. Choisir son parcours

| | **A. Jeu versionné** | **B. Gros volume** |
|---|---|---|
| Pour quoi faire | Découvrir le projet, faire une démo, travailler sur le rapport | Travailler au volume réaliste |
| Données | 4,3 M de lignes, déjà dans Git | 42,7 M de lignes, générées sur le PC |
| Télécharger PaySim | Non (visuel PaySim de la page Qualité vide) | **Oui** |
| Disque libre à prévoir | 3 Go | **30 Go** (base de 18 Go + fichiers temporaires) |
| Durée, une fois installé | **~8 min** | **~1 h 10** |

Durées mesurées sur un PC de 6 cœurs et 15 Go de RAM. Dans les deux cas, les données sont les mêmes (mêmes défauts, mêmes totaux ancrés sur les dépôts réels) : seul le nombre de lignes change.

## 2. Installer les prérequis

| Outil | Version | Remarque |
|---|---|---|
| Git | récente | |
| Python | 3.10 à 3.13 | Testé en 3.13.5. Cocher « Add python.exe to PATH » à l'installation |
| PostgreSQL | 15 ou 16 | **Noter le mot de passe choisi pour `postgres`.** Docker Desktop est une alternative (non testée sur ce projet) |
| Power BI Desktop | mi-2025 ou plus récent | Windows uniquement. Testé en 2.159 (version Microsoft Store) |

## 3. Récupérer le projet

Cloner dans un dossier **court**, par exemple `C:\Users\<vous>\cresus` : Windows refuse les chemins trop longs (erreur `Filename too long`).

```powershell
cd $HOME
git clone https://github.com/mehdi182003/projet_bi_finance.git cresus
cd cresus
```

Vérifier qu'on est bien sur `main` :

```powershell
git branch --show-current
```

## 4. Préparer Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Compter 3 minutes. `(.venv)` doit apparaître au début de la ligne de commande.

**À refaire dans chaque nouvelle fenêtre PowerShell** : se placer dans le dossier du projet, puis lancer `.\.venv\Scripts\Activate.ps1`.

## 5. Préparer PostgreSQL

Vérifier que le service tourne (le numéro dépend de la version installée) :

```powershell
Get-Service postgresql*
```

`Status` doit afficher `Running`. Créer ensuite la base, en saisissant le mot de passe choisi à l'installation :

```powershell
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE cresus"
```

Le message `la base de données « cresus » existe déjà` n'est pas un problème.

*Avec Docker, à la place de cette étape :* `docker compose up -d` crée le serveur et la base.

## 6. Configurer le projet

```powershell
copy .env.example .env
```

Si le mot de passe de `postgres` n'est pas `postgres`, ouvrir `.env` et modifier `POSTGRES_PASSWORD`. Dans ce cas, avant toute commande `dbt` lancée à la main, ajouter :

```powershell
$env:POSTGRES_PASSWORD = "votre_mot_de_passe"
```

dbt ne lit pas le fichier `.env` : seul `python pipeline.py` le fait.

## 7. Parcours A : lancer avec le jeu versionné

En une seule commande :

```powershell
python pipeline.py
```

Elle doit finir par `Pipeline terminé`. Les étapes sont détaillées au § 9 si l'on préfère les lancer une par une. Passer ensuite au § 10 (Power BI).

## 8. Parcours B : préparer le gros volume

1. Télécharger le fichier PaySim (compte Kaggle gratuit) : <https://www.kaggle.com/datasets/ealaxi/paysim1>
2. Décompresser le `.zip` et placer `PS_20174392719_1491204439457_log.csv` (494 Mo) dans `data\raw\`.
3. Dans `.env`, décommenter la dernière ligne :
   ```
   DOSSIER_SOURCES_INTERNES=data/generees/lot_50
   ```

En une seule commande (~1 h 10) :

```powershell
python pipeline.py --regenerer --taille-lot 50
```

Ou étape par étape, en suivant le § 9 avec l'étape 1.

## 9. Le détail de chaque étape

Le venv doit être activé, et les commandes lancées depuis la racine du projet. Les durées sont indiquées pour le jeu versionné / le gros volume.

### Étape 1 — Python : générer les données sales *(parcours B uniquement, – / 16 min)*

```powershell
python pipeline.py --etapes generer --taille-lot 50
```

- **Ce que ça fait** : calcule 3 ans d'opérations ancrées sur les dépôts réels (`etl/generateur_flux.py`), puis les écrit dans le format de chacun des 4 systèmes bancaires, avec leurs défauts (`etl/systemes_sources.py`).
- **Résultat** : `data\generees\lot_50\` contient 374 fichiers compressés (586 Mo) et les soldes comptables.
- **À savoir** : le résultat est reproductible. Avec les mêmes paramètres, on obtient les mêmes fichiers.

### Étape 2 — Python : charger les fichiers dans PostgreSQL *(1 min / 11 min)*

```powershell
python pipeline.py --etapes extract load
```

- **Ce que ça fait** : récupère les cours BCE et les séries des banques centrales (déjà en cache dans `data\sources\`), puis copie les exports **tels quels, en texte**, dans le schéma `raw`.
- **À vérifier** : le journal affiche une ligne par système, par exemple `SAB : 111 fichiers (0 déjà à jour), 2 149 620 lignes chargées`.
- **À savoir** : au lancement suivant, un fichier inchangé est ignoré (`déjà à jour`) ; c'est normal. Un fichier absent du dossier actif est retiré de `raw`.

### Étape 3 — dbt : nettoyer et construire l'étoile *(5 min / 39 min)*

```powershell
cd dbt
dbt build --profiles-dir . --exclude tag:prevision
cd ..
```

Si les données ont changé depuis le dernier lancement (étape 1 relancée, changement de jeu), ajouter **`--full-refresh`** : le fait `fct_flux_tresorerie_horaire` ne recalcule sinon que ses 35 derniers jours.

- **Ce que ça fait** : `staging` (un modèle par système : formats, fuseaux, unités, sens), `intermediate` (union, dédoublonnage, rejets tracés avec leur motif), `marts` (étoile et analyses), puis tous les contrôles.
- **À vérifier** : la dernière ligne doit afficher **`ERROR=0`** (par exemple `PASS=138 WARN=1 ERROR=0`).
- **Seule alerte attendue** : `alerte_rupture_serie_change`, car le rouble n'est plus coté par la BCE depuis 2022.

### Étape 4 — Python : calculer les prévisions *(1 min)*

```powershell
python pipeline.py --etapes prevision
```

- **Ce que ça fait** : met en concurrence 3 modèles de prévision, simule 1 000 trajectoires de janvier 2026, calcule la réserve requise, puis compare la prévision aux dépôts réels publiés ensuite. Écrit dans le schéma `ml`.
- **À vérifier** : le journal se termine par `Couverture de l'intervalle à 90 % : 7 / 9 filiales`.
- **À savoir** : ce contrôle télécharge des données réelles. Sans Internet, il est simplement ignoré, avec un avertissement.

### Étape 5 — dbt : construire les marts de prévision *(moins d'1 min)*

```powershell
python pipeline.py --etapes dbt_prev
```

- **À vérifier** : `PASS=18 WARN=0 ERROR=0`.

## 10. Connecter Power BI à la base

1. Double-cliquer sur `powerbi\Cresus\Cresus.pbip`. Le rapport s'ouvre **vide** : c'est normal, rien n'est encore importé.
2. Cliquer sur **Actualiser maintenant**, dans la barre au-dessus du rapport.
3. Quand les identifiants sont demandés, choisir l'onglet **Base de données** à gauche :
   - Nom d'utilisateur : `postgres`
   - Mot de passe : celui de votre PostgreSQL (`postgres` si vous avez gardé cette valeur)
4. Cliquer sur **Se connecter**.
5. Au message **Prise en charge du chiffrement**, cliquer sur **OK** : la base est sur votre PC, rien ne passe par Internet.
6. Attendre la fin de l'import (environ 1 minute).

Il n'y a **pas** de source à ajouter : n'utilisez pas *Obtenir des données*. L'adresse de la base (`localhost:5432`, base `cresus`) est déjà dans le projet. Pour la changer : flèche sous *Transformer les données* → *Modifier les paramètres*.

## 11. Vérifier les rapports

Comparer sans aucun filtre (tous les segments sur « Tout »). La colonne B a été contrôlée dans Power BI ; la colonne A est calculée en SQL avec les mêmes formules.

| Page | Indicateur | A. Jeu versionné | B. Gros volume |
|---|---|---|---|
| Cockpit DAF | Position de trésorerie | 5,51 Md | 5,53 Md |
| | Ratio de liquidité | 156,9 % | 157,6 % |
| | Jours sous 100 % | 202 | 175 |
| | Encours de dépôts | 35,11 Md | 35,11 Md |
| | Refinancement levé | 6,96 Md | 6,94 Md |
| | Excédent placé | 5,62 Md | 5,60 Md |
| | VaR change 95 % 10 j | 26,24 M | 26,61 M |
| | Effet de change cumulé | −115,58 M | −118,16 M |
| Flux de trésorerie | Part des gros décaissements | 9,6 % | 13,8 % |
| Prévisions | Erreur du champion (WAPE) | 17,1 % | 17,1 % |
| | Contrôle réel janv. 2026 : dans la fourchette | 77,8 % | 77,8 % |
| Change & couverture | Exposition au change | 2,57 Md | 2,60 Md |
| Simulateur (aucun choc) | Position stressée | 5,51 Md | 5,53 Md |
| Simulateur (retraits 20 %) | Position stressée | −1,51 Md | −1,49 Md |
| Qualité des données | Lignes brutes reçues | 4,26 M | 42,67 M |
| | Taux de rejet | 4,4 % | 4,5 % |
| | Rejets inattendus | 0 | 0 |

**Ce que les graphiques doivent raconter :**
- **Flux** : le refinancement domine en 2023 (fuite des dépôts pendant la hausse des taux), les placements en 2025.
- **Flux** : les virements émis sont le premier type de décaissement. Le solde net est positif le matin (traitements en lot) et négatif en journée.
- **Change** : sans devise choisie, la courbe affiche l'USD (1 EUR ≈ 1,14 à 1,20).
- **Change** : l'USD et la NOK ont les effets de change les plus négatifs ; la SEK est positive.
- **Qualité** : l'encours réel et l'encours reconstitué se superposent. Sans filiale choisie, la courbe affiche la France (de 12,5 Md à environ 11 Md).
- **Simulateur** : choisir retraits 20 %, multiplicateur 2,5 et taux 150 pb reproduit le scénario « Panique bancaire sévère » : la plupart des filiales passent en « Critique ». En gros volume : besoin de 10,77 Md, coût de 480,79 M par an.

Une carte qui affiche *(Vide)* pour l'horizon de survie signifie qu'il n'y a pas de fuite de trésorerie : la position ne baisse pas.

**N'enregistrez le rapport que si vous l'avez modifié** : l'enregistrement réécrit de nombreux fichiers de `powerbi/Cresus`, qui apparaîtront ensuite dans `git status`.

## 12. Regarder directement la base (pgAdmin)

1. Ouvrir **pgAdmin 4**, puis **Servers → PostgreSQL** (mot de passe de `postgres`). Si le serveur n'apparaît pas : clic droit sur *Servers → Register → Server*, avec `localhost`, le port `5432` et l'utilisateur `postgres`.
2. Ouvrir **Databases → cresus → Schemas**.

| Schéma | Contenu |
|---|---|
| `raw` | Données sales, telles que reçues (bronze) |
| `staging`, `intermediate` | Nettoyage (argent) |
| `marts` | Étoile et analyses, lues par Power BI (or) |
| `ml` | Sorties des prévisions |

Dans le *Query Tool*, trois requêtes utiles :

```sql
-- catalogue des défauts détectés et traités par l'ETL
select * from marts.mart_qualite_defauts;

-- lignes rejetées, avec leur motif
select motif_rejet, count(*) from intermediate.int_operations_controlees
where motif_rejet is not null group by 1 order by 2 desc;

-- exemple de données sales, avant nettoyage
select * from raw.src_sab limit 20;
```

Pour le lignage et le dictionnaire de données :

```powershell
cd dbt
dbt docs generate --profiles-dir .
dbt docs serve --profiles-dir .
```

## 13. Que relancer après un changement ?

| J'ai modifié… | Je relance |
|---|---|
| Le générateur, ses paramètres ou la taille de lot | `python pipeline.py --regenerer --taille-lot <n>` (le fait est reconstruit automatiquement), puis *Actualiser* dans Power BI |
| Un modèle dbt ou un test | `python pipeline.py --etapes dbt prevision dbt_prev`, puis *Actualiser* |
| Le jeu de données actif (`DOSSIER_SOURCES_INTERNES`) | `python pipeline.py --full-refresh`, puis *Actualiser* |
| Une mesure DAX ou un visuel | `powerbi/mesures_dax.dax` ou `powerbi/generer_pbip.py`, puis `python powerbi/generer_pbip.py --tomtool …` (SDK .NET 8, voir `CLAUDE.md`) |
| Rien, je veux juste rafraîchir | *Actualiser* dans Power BI |

Le changement de taille de lot écrit dans un autre dossier (`data\generees\lot_<n>`) : penser à mettre à jour `DOSSIER_SOURCES_INTERNES` dans `.env` pour les lancements suivants.

## 14. En cas de problème

| Symptôme | Cause | Solution |
|---|---|---|
| `Filename too long` au clonage | Chemin trop long sous Windows | Cloner dans un dossier court, ou `git config --global core.longpaths true` |
| `Activate.ps1 ne peut pas être chargé` | Politique d'exécution de PowerShell | `Set-ExecutionPolicy -Scope Process RemoteSigned`, puis relancer l'activation |
| `dbt` n'est pas reconnu | Venv non activé | `.\.venv\Scripts\Activate.ps1` |
| Erreur à `pip install`, en particulier sur dbt | Python trop récent | Utiliser Python 3.13 |
| `échec de l'authentification par mot de passe` | Mot de passe différent de `postgres` | Corriger `.env` ; pour dbt à la main : `$env:POSTGRES_PASSWORD = "..."` |
| `la base de données « cresus » n'existe pas` | Base non créée | Voir § 5 |
| `Aucun export SAB dans …` | Mauvais `DOSSIER_SOURCES_INTERNES` ou gros volume pas encore généré | Corriger `.env`, ou lancer l'étape 1 |
| `--regenerer nécessite PaySim` | Fichier absent | Voir § 8 |
| `assert_fct_flux_a_jour` échoue | Données changées sans reconstruire le fait | `python pipeline.py --etapes dbt --full-refresh` |
| `assert_rapprochement_comptable` échoue | Règle de nettoyage cassée, ou doublon non traité | Lire les lignes en écart, avec `dbt test --select assert_rapprochement_comptable --store-failures` |
| Le rapport reste vide après l'ouverture | Import non lancé | *Actualiser maintenant* (§ 10) |
| *Prise en charge du chiffrement* | PostgreSQL local sans SSL | Cliquer sur **OK** |
| Power BI refuse les identifiants | Mauvais mot de passe enregistré | Flèche sous *Transformer les données* → *Paramètres de la source de données* → *Modifier les autorisations* |
| Erreur d'import citant `Decimal` | Colonne `numeric` restée dans `marts` | Relancer `dbt build` : les marts sont convertis en `double precision` à chaque construction |
| Une table du rapport est vide | Étape 3, 4 ou 5 non lancée ou en échec | Relancer l'étape, puis *Actualiser* |

Pour repartir de zéro, supprimer et recréer la base (**efface tout son contenu**), puis relancer le parcours choisi :

```powershell
& "C:\Program Files\PostgreSQL\15\bin\psql.exe" -U postgres -h localhost -c "DROP DATABASE cresus" -c "CREATE DATABASE cresus"
```
