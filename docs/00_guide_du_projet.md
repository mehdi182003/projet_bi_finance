# Guide du projet Crésus

À lire en premier. Ce guide explique ce que fait le projet, comment le lancer, où trouver chaque fichier et comment lire les résultats.

**Groupe G5** : Fabien DEVAUX, Charles ESPRIET, Mehdi FOUIDI, Mokhmad GUIRIEV, Micipssa DJAROUN, Robin VICO.

**Sommaire** : [1. Le projet](#1-le-projet-en-bref) · [2. Le fonctionnement](#2-comment-ça-marche) · [3. Les données](#3-les-données) · [4. Les dossiers](#4-où-trouver-quoi) · [5. Le lancement](#5-lancer-le-projet) · [6. Le rapport](#6-lire-le-rapport-power-bi) · [7. Les résultats](#7-les-résultats-expliqués) · [8. Les modèles](#8-les-modèles-de-prévision) · [9. Le vocabulaire](#9-le-vocabulaire-à-connaître) · [10. Les questions du prof](#10-les-questions-probables-du-prof) · [11. Les limites](#11-les-limites-à-assumer)

## 1. Le projet en bref

**La question du sujet** : comment l'analyse prédictive et la simulation peuvent-elles faire gagner de l'argent dans la gestion de trésorerie d'une banque ?

**Le client** : ZF Banque, un groupe fictif de 10 filiales en France, en Europe du Nord, en Afrique et en Amérique du Nord.

**Notre réponse** : elles font gagner de l'argent parce qu'elles permettent de décider plus tôt. On prépare un refinancement au lieu de le subir, on place l'argent inutilisé, et on chiffre le risque de chaque choix. Cela suppose des données fiables, donc le projet commence par elles.

**Ce qu'on a construit** : une chaîne complète, des fichiers bruts des filiales jusqu'à un rapport Power BI, sur 3 ans (2023-2025).

## 2. Comment ça marche

| Étape | Outil | Ce qu'elle fait | Où |
|---|---|---|---|
| 1. Générer | Python | Crée les exports des filiales avec leurs défauts (seulement pour le gros volume) | `etl/generateur_flux.py`, `etl/systemes_sources.py` |
| 2. Charger | Python | Copie les fichiers tels quels dans PostgreSQL (couche bronze) | `etl/chargement_sources_internes.py` |
| 3. Nettoyer | dbt | Corrige les formats, retire les doublons, trace chaque rejet (couche silver) | `dbt/models/staging/`, `dbt/models/intermediate/` |
| 4. Modéliser | dbt | Construit le schéma en étoile et les tables d'analyse (couche gold) | `dbt/models/marts/` |
| 5. Prévoir | Python | Compare 3 modèles, simule 1 000 scénarios, calcule la réserve requise | `etl/prevision.py` |
| 6. Contrôler | Python, dbt | Compare la prévision aux vrais dépôts de janvier 2026, puis lance les tests | `etl/controle_a_posteriori.py`, `dbt/tests/` |
| 7. Restituer | Power BI | Affiche 5 pages et un simulateur | `powerbi/Cresus/Cresus.pbip` |

`pipeline.py` enchaîne toutes ces étapes en une seule commande.

## 3. Les données

Aucune banque ne publie ses opérations. Le projet mélange donc du réel et du simulé.

| Nature | Données | Source |
|---|---|---|
| **Réel** | Dépôts à vue par pays | BCE, Fed, Banque du Canada, SCB, Danmarks Nationalbank, FMI, BEAC |
| **Réel** | Taux directeurs, cours de change, jours fériés | Banques centrales, BCE via Webstat, bibliothèque `holidays` |
| **Simulé** | Opérations, défauts des fichiers, grand livre | Notre générateur, calé pour que le cumul des flux retombe sur les vrais dépôts |
| **Simulé** | Forme des montants, heures, fraude | PaySim (Kaggle), utilisé seulement à la génération |
| **Supposé** | Parts de marché, taux de réserve, tickets moyens | Nos hypothèses |

Les 4 systèmes bancaires ont chacun leur format et leurs défauts : SAB (France, Benelux, Finlande), NORDIC (Suède, Danemark, Norvège), AMERICORE (Canada, États-Unis) et DELTA (Côte d'Ivoire, Cameroun).

Il existe deux jeux de données, avec les mêmes défauts et les mêmes totaux :

| | Jeu léger | Gros volume |
|---|---|---|
| Lignes brutes | 4,3 M | 42,7 M |
| Où | `data/sources_internes/`, dans Git | `data/generees/lot_50/`, en local |
| Durée | Environ 7 min | Environ 1 h 10 |
| Base PostgreSQL | 1,8 Go | 17 Go |
| Usage | Lancer, travailler, faire une démo | Chiffres de référence du MOE et de la soutenance |

## 4. Où trouver quoi

```
├── README.md            présentation du dépôt
├── pipeline.py          lance toute la chaîne
├── requirements.txt     bibliothèques Python à installer
├── .env.example         modèle de configuration (à copier en .env)
├── docker-compose.yml   PostgreSQL par Docker (non testé)
├── CLAUDE.md            notes de reprise : décisions, état, reste à faire
├── data/
│   ├── sources/          données réelles : dépôts, taux, cours
│   ├── sources_internes/ exports des filiales, jeu léger
│   ├── generees/         gros volume généré en local, pas dans Git
│   └── raw/              fichier PaySim, pas dans Git
├── etl/                 scripts Python : génération, chargement, prévision
├── dbt/
│   ├── models/           nettoyage (staging, intermediate) et étoile (marts)
│   ├── seeds/            référentiels : filiales, devises, taux, scénarios
│   ├── tests/            les 10 tests métier
│   └── macros/           fonctions SQL communes
├── powerbi/
│   ├── Cresus/           le rapport à ouvrir (Cresus.pbip)
│   ├── mesures_dax.dax   toutes les formules du rapport
│   └── generer_pbip.py   génère le rapport (nécessite le SDK .NET)
├── docs/                documentation détaillée
└── livrables/           documents à rendre
```

**Les livrables**

| Fichier dans `livrables/` | Contenu |
|---|---|
| `03_IBI_AMOA_FICHE_EXPERTISE_…` | Fiche d'expertise corrigée |
| `04_IBI_SUPPORT_SOUTENANCE_…` | Diapos de soutenance, avec notes orateur |
| `05_IBI_MOE_POC_…` | Rendu MOE du POC |
| `05_IBI_MOE_POC_DICTIONNAIRE_DONNEES_…xlsx` | Dictionnaire de données : une ligne par colonne, pour les 20 tables du schéma en étoile |
| `IBI_AMOA_REPONSE_APPEL_OFFRES_…` | Réponse à l'appel d'offres |
| `IBI_AMOA_WEBOGRAPHIE_…` | Liste des sources |

**La documentation détaillée**

| Document | Pour quoi |
|---|---|
| [01 Cadrage](01_cadrage_amoa.md) | Le besoin, le périmètre, les prérequis |
| [02 Spécifications](02_specifications_moe.md) | Les règles de calcul et le plan de tests |
| [03 Prédictif](03_analyse_predictive_et_simulation.md) | Les modèles et leurs résultats |
| [04 Power BI](04_guide_power_bi.md) | Le contenu du rapport et la sécurité |
| [05 Synthèse](05_synthese_swot_recommandations.md) | SWOT, impacts, gains |
| [06 Profil des données](06_profil_donnees_et_choix_kpi.md) | Pourquoi PaySim ne suffit pas, le choix des KPI |
| [07 Données sur 3 ans](07_donnees_3_ans.md) | Comment les données sont construites |
| [08 ETL](08_etl_sources_et_nettoyage.md) | Le format des sources et les règles de nettoyage |
| [09 Procédure](09_procedure_pas_a_pas.md) | Le lancement détaillé et le dépannage |

## 5. Lancer le projet

Il faut Git, Python (3.10 à 3.13), PostgreSQL 15 ou 16 et Power BI Desktop. Commandes à taper dans PowerShell. Le détail et le dépannage sont dans la [procédure pas à pas](09_procedure_pas_a_pas.md).

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

Si votre mot de passe PostgreSQL n'est pas `postgres`, modifiez `POSTGRES_PASSWORD` dans `.env`. La commande doit finir par `Pipeline terminé`.

Ensuite, double-cliquez sur `powerbi\Cresus\Cresus.pbip`, puis cliquez sur **Actualiser maintenant**. Choisissez l'onglet **Base de données** pour saisir l'utilisateur et le mot de passe, puis cliquez sur **OK** au message sur le chiffrement.

**Si vous avez déjà le projet** : `git pull`, puis `python pipeline.py`, puis **Actualiser** dans Power BI.

**Pour le gros volume** : placez le fichier PaySim dans `data\raw\`, puis lancez `python pipeline.py --regenerer --taille-lot 50`. La procédure explique le réglage à ajouter dans `.env`.

**Vérifier que tout va bien** : voici ce que vous devez obtenir, sans aucun filtre.

| Indicateur | Jeu léger | Gros volume |
|---|---|---|
| Position de trésorerie | 5,51 Md€ | 5,53 Md€ |
| Ratio de liquidité | 156,9 % | 157,6 % |
| Refinancement levé | 6,96 Md€ | 6,94 Md€ |
| Excédent placé | 5,62 Md€ | 5,60 Md€ |
| Erreur de prévision (WAPE) | 14,3 % | 14,5 % |
| Dépôts de janvier 2026 dans la fourchette | 7 sur 9 | 7 sur 9 |
| Lignes brutes reçues | 4,26 M | 42,67 M |

Dans le journal, `dbt` doit afficher `ERROR=0`. La seule alerte normale concerne le rouble, qui n'est plus coté par la BCE depuis 2022.

## 6. Lire le rapport Power BI

| Page | Question | Comment la lire |
|---|---|---|
| **Cockpit DAF** | Faut-il emprunter ou placer ? | Les 4 cartes donnent la situation. Le graphique montre le refinancement et les placements par mois. Le tableau compare les filiales |
| **Prévisions** | Que va-t-il se passer le mois prochain ? | La courbe montre le passé puis la fourchette prévue. Le tableau de réserve indique où il manque de l'argent et où il y en a trop. Un autre tableau compare la prévision aux vrais dépôts |
| **Change & couverture** | Que couvrir ? | Le tableau donne une décision par devise. Les barres montrent ce que le change a déjà coûté |
| **Simulateur de stress** | Combien de temps tient-on en crise ? | On règle 4 chocs en haut, et les chiffres changent. Un tableau résume les 7 scénarios de crise |
| **Qualité des données** | Peut-on faire confiance aux chiffres ? | Le graphique montre les défauts corrigés. Sur la courbe, le réel et le reconstitué se superposent |

**Une carte affiche « (Vide) »** : sur le simulateur, il n'y a pas de limite de survie. Sur la perte possible, il n'y a pas de risque de change (cas de l'euro).

**Pour tester la sécurité** : *Modélisation → Afficher comme rôles*, cliquez sur le nom d'un rôle, puis sur **OK**.

## 7. Les résultats expliqués

Tous les chiffres ci-dessous viennent du gros volume. Les montants sont des **ordres de grandeur**, car ils dépendent des parts de marché supposées. Les tendances viennent de données réelles.

### Le refinancement et les placements

| En M€ | 2023 | 2024 | 2025 |
|---|---|---|---|
| Refinancement levé | 3 984 | 1 824 | 1 129 |
| Excédent placé | 813 | 2 169 | 2 618 |

**Ce qu'on voit** : le groupe passe d'un besoin d'argent à un excédent.
**Pourquoi** : en 2023, les taux montent et les clients sortent leur argent des comptes à vue. C'est visible dans les vrais dépôts.
**Ce qu'on en tire** : ce besoin était prévisible. Un refinancement préparé coûte moins cher qu'un refinancement d'urgence, environ 0,25 point d'écart, soit 2,5 M€ par an pour chaque milliard.

### La prévision et la réserve

**Ce qu'on voit** : l'erreur de prévision est de 14,5 % au niveau du groupe. Les vrais dépôts de janvier 2026 tombent dans la fourchette pour 7 filiales sur 9 ; la Finlande et la Suède en sortent.
**Pourquoi c'est important** : ces dépôts ont été publiés après la date d'arrêté, donc le modèle ne les avait pas vus. C'est notre meilleure preuve.
**Ce qu'on en tire** : janvier concentre 60 des 175 passages sous 100 % de liquidité, car les dépôts baissent chaque année à cette période. La France aurait besoin de 18,1 % de réserve au lieu de 15 %, donc il faut préparer le financement dès décembre.
**L'autre côté** : la Côte d'Ivoire, le Cameroun et la Norvège gardent trop de réserve. Placer ces 91 M€ rapporterait environ 3,6 M€ par an.

### Le change

| Devise | Effet sur 3 ans | Décision | Pourquoi |
|---|---|---|---|
| USD | −58,2 M€ | À arbitrer | Couverture chère |
| NOK | −46,2 M€ | À arbitrer | Couverture chère |
| CAD | −29,4 M€ | Prioritaire | Couverture peu chère |
| DKK | −1,2 M€ | Inutile | Devise qui suit l'euro |
| SEK | +16,8 M€ | À couvrir | La couverture rapporte |
| XOF, XAF | 0 | Parité fixe | Taux fixe, à suivre par les scénarios de crise |

L'exposition totale est de 2,60 Md€, pour une perte possible de 26,6 M€ à 10 jours. Tout couvrir coûterait 15,3 M€ par an, ce qui pousse à cibler certaines devises.

### Les crises

| Scénario | Position | À trouver | Survie |
|---|---|---|---|
| Central | 5,53 Md€ | 0 | Pas de fuite marquée |
| Retraits modérés (Northern Rock, 2007) | 3,78 Md€ | 166 M€ | 22 à 51 jours hors zone CFA |
| Crise combinée | 1,82 Md€ | 3,82 Md€ | 3 à 38 jours |
| Panique (Silicon Valley Bank, 2023) | −1,49 Md€ | 10,77 Md€ | 0 jour, 2 à 8 en zone CFA |

En panique, trouver cet argent coûterait 481 M€ par an, dont 162 M€ dus à la hausse des taux. Cela justifie de négocier des lignes de secours à l'avance.

### La fiabilité

- **Nettoyage** : 42,7 M de lignes reçues, 40,7 M retenues. Les 1,9 M de lignes rejetées (4,5 %) gardent leur motif, et la plupart sont des doublons.
- **Rapprochement** : chaque jour et pour chaque filiale, les crédits, les débits et le nombre d'opérations égalent le grand livre.
- **Ancrage** : l'encours reconstitué égale les dépôts publiés sur 481 dates.
- **Tests** : 104 tests automatiques, 0 erreur, une alerte attendue sur le rouble.

## 8. Les modèles de prévision

**Il n'y a pas d'IA dans les calculs** : ni réseau de neurones, ni modèle génératif. Sur 3 ans de données, des modèles simples suffisent et s'expliquent facilement.

| Modèle | En une phrase | Erreur sur les décaissements | Erreur sur les encaissements |
|---|---|---|---|
| Naïf hebdomadaire | Moyenne du même jour sur 4 semaines ; c'est la référence à battre | 17,6 % | 45,9 % |
| Holt-Winters | Lissage avec un rythme hebdomadaire | 16,4 % | 78,5 % |
| **Régression calendaire** (retenue) | Calcul à partir du calendrier : jours ouvrés, fériés, début et fin de mois, mois | **13,3 %** | **16,7 %** |

Erreurs moyennes des 10 filiales.

Deux simulations complètent ces modèles :
- **Monte-Carlo** : on rejoue 1 000 fois le mois suivant à partir des erreurs passées du modèle, ce qui donne la fourchette et la réserve requise.
- **Change** : un cours de change se prévoit mal, donc on simule une fourchette à 30 jours à partir de la volatilité récente. Le cours réel y tombe 94 % des jours.

## 9. Le vocabulaire à connaître

| Terme | En clair |
|---|---|
| **Bronze, Silver, Gold** | Données brutes, nettoyées, prêtes pour l'analyse |
| **ELT** | On charge d'abord, on transforme ensuite dans l'entrepôt |
| **Dimension** | Table de contexte : qui, quoi, quand, où (filiale, devise, date, scénario). Elle ne contient aucun montant |
| **Fait** | Table de mesures : combien (flux, position, VaR…), reliée aux dimensions par des clés. Préfixe `fct_` (fait de base) ou `mart_` (fait dérivé) |
| **Grain** | Ce que représente une ligne d'une table, par exemple un jour et une filiale |
| **Semi-additif** | Un stock : on lit le dernier jour, on n'additionne pas les jours entre eux |
| **Periodic snapshot** | Une photo prise à intervalle régulier, ici chaque jour |
| **SCD type 1** | On écrase l'ancienne valeur d'une dimension, sans garder d'historique |
| **DELTA et FULL** | Recharger seulement ce qui a changé, ou tout recharger |
| **Lineage** | Le chemin d'une donnée, de la source au rapport |
| **RLS** | Chaque utilisateur ne voit que ses lignes |
| **RACI** | Qui réalise, valide, contribue, est informé |
| **MoSCoW** | Priorités : indispensable, important, bonus, plus tard |
| **TCO** | Coût total : construction et fonctionnement |
| **Trésorerie (position)** | L'argent disponible à la fin de la journée |
| **Ratio de liquidité (LCR)** | Position divisée par le besoin à 30 jours ; il doit rester au-dessus de 100 %. Le nôtre est simplifié |
| **Refinancement et placement** | Emprunter ce qui manque, placer ce qui dépasse |
| **Couverture de change** | Payer pour se protéger d'une variation de devise |
| **VaR** | La perte possible sur le change, à 95 % de confiance et sur 10 jours |
| **WAPE** | L'écart entre le prévu et le réel, en pourcentage du réel |
| **P5, P50, P95** | Bas, milieu et haut de la fourchette ; 90 % des simulations sont entre P5 et P95 |
| **Backtest** | Tester un modèle sur une période passée qu'il n'a pas vue |

## 10. Les questions probables du prof

**Quelle différence entre vos dimensions et vos faits ?**
Les dimensions décrivent le contexte : qui (la filiale), quoi (la devise, le type d'opération, le scénario), quand (la date), où (le pays). Les faits contiennent les chiffres : combien. Aucune dimension ne contient de montant : l'encours et la réserve de départ, d'abord rangés dans `dim_filiale`, sont dans le fait `fct_situation_initiale_filiale`, et un test dbt les empêche d'y revenir. Le nombre de clients, qui ne servait à aucun indicateur, a été retiré.

**Il reste pourtant des nombres dans vos dimensions ?**
Oui, trois, mais ce ne sont pas des quantités à additionner : la parité fixe du franc CFA (655,957 pour 1 euro, une constante), le sens d'un type d'opération (+1 pour une entrée, −1 pour une sortie) et l'ordre d'affichage des filiales et des scénarios.

**Vos données sont-elles réelles ?**
En partie. Les dépôts, les taux, le change et les jours fériés sont réels. Les opérations sont simulées, car aucune banque ne les publie, mais leur cumul retombe sur les vrais dépôts.

**Pourquoi ne pas avoir gardé PaySim seul ?**
Il ne couvre que 31 jours, dont 12 normaux, sa fraude est constante et ses soldes sont incohérents. Il ne permet donc pas de voir une saison ou un cycle de taux.

**La régression gagne sur 20 séries sur 20 : n'est-ce pas trop beau ?**
Si, en partie, car notre générateur crée un rythme calendaire que la régression retrouve. C'est pour cela que notre vraie preuve est la comparaison avec les dépôts réels de janvier 2026.

**Le rapprochement au grand livre prouve-t-il que les données sont vraies ?**
Non. Le grand livre vient lui aussi du générateur. Le test prouve que le nettoyage ne perd et n'ajoute rien.

**Pourquoi pas de l'IA ou du temps réel ?**
Les modèles simples suffisent sur ce volume et s'expliquent plus facilement. Les décisions de trésorerie sont quotidiennes, donc le temps réel coûterait cher sans rien apporter.

**Comment avez-vous calculé la VaR du groupe ?**
On additionne les VaR de chaque devise. C'est prudent, car cela suppose que toutes les devises baissent en même temps. Si elles évoluaient indépendamment, elle serait d'environ 13,8 M€ au lieu de 26,6 M€.

**Le risque de 91,1 % concerne-t-il tout le groupe ?**
Non. C'est celui de la filiale la plus exposée, la Finlande. Il se lit filiale par filiale.

**Avez-vous utilisé une IA pour le projet ?**
Répondez franchement : Claude Code a aidé à construire le projet, comme l'indique `CLAUDE.md`. Aucun modèle d'IA n'intervient dans les calculs. L'important est que chacun sache expliquer ce qu'il présente.

## 11. Les limites à assumer

- Les opérations et leurs défauts sont simulés, et plusieurs paramètres sont des hypothèses à sourcer.
- Les montants dépendent des parts de marché supposées. Seule une filiale pilote avec de vraies données peut les confirmer.
- Le ratio de liquidité est simplifié, avec un taux de fuite unique de 10 %.
- La prévision du groupe additionne celles des filiales, ce qui donne une estimation prudente.
- Seuls 3 mois de janvier permettent d'estimer l'effet saisonnier.
- Le Cameroun a 10 mois interpolés et n'entre pas dans le contrôle de janvier 2026.
- Le traitement se lance à la main : l'ordonnancement et la supervision restent à construire.
- La grille de choix, le RACI, le planning et le TCO reposent sur des hypothèses à valider en groupe.
