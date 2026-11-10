# Répartition du projet en 6 parties

Chaque membre du groupe prend une partie, la maîtrise en détail et répond aux questions du prof sur celle-ci. Les 6 fiches de ce dossier expliquent tout ce qu'il faut savoir : les notions, les outils, le code ligne par ligne quand c'est utile, les chiffres et les questions probables.

## Les 6 parties

| N° | Partie | Ce qu'elle couvre | Fiche | Diapos | Qui |
|---|---|---|---|---|---|
| 1 | Besoin, KPI et pilotage du projet | La banque, la trésorerie, les 6 KPI, les résultats et les gains, le RACI, le planning, le TCO | [01](01_besoin_kpi_projet.md) | 1, 2, 3, 8, 10, 16 | Mokhmad |
| 2 | Les données et le change | Les séries réelles, PaySim, la génération des 3 ans, les 4 systèmes et leurs défauts, la fourchette de change, la VaR, la couverture | [02](02_donnees.md) | 6, 11, 14 (couvrir) | Robin |
| 3 | Architecture, PostgreSQL et chargement | La grille de choix, le SWOT, l'ELT en couches, PostgreSQL, le chargement Python, l'orchestration, le branchement de Power BI et la sécurité, l'installation | [03](03_architecture_chargement.md) | 4, 7, 9 | Charles |
| 4 | Nettoyage et qualité avec dbt | La méthodologie et les priorités, dbt, le nettoyage des 4 systèmes, les règles RG-NET, les tests, la recette | [04](04_nettoyage_qualite_dbt.md) | 5, 15, démo dbt | Mehdi |
| 5 | Modèle en étoile et Power BI | Dimensions et faits, grain, additivité, position et liquidité, le dictionnaire Excel, les mesures DAX, les pages | [05](05_modele_power_bi.md) | 12, démo Power BI | Fabien |
| 6 | Prévision, simulation et stress tests | Les 3 modèles de prévision, le WAPE, Monte-Carlo, la réserve, le contrôle sur janvier 2026, les stress tests et le simulateur | [06](06_prevision_risques.md) | 13, 14 (résister) | à choisir |

Mokhmad a déjà retravaillé les dimensions, les faits et le dictionnaire Excel : la partie 5 lui correspond bien. Le reste est à répartir dans le groupe. Les numéros de diapos renvoient au support de soutenance (`livrables/04_IBI_SUPPORT_SOUTENANCE_…pptx`).

**L'équilibre entre les parties.** Chacun présente 2 à 4 diapos ; ceux qui en ont le moins font une démonstration. La diapo 14 se partage : la partie 2 présente « couvrir », la partie 6 « résister ».

| Partie | Mots à apprendre | Blocs de code | Chiffres | Questions du prof | Fichiers en annexe |
|---|---|---|---|---|---|
| 1 | 3 700 | 0 | 64 | 5 | 10 |
| 2 | 4 800 | 11 | 73 | 10 | 21 |
| 3 | 4 700 | 16 | 24 | 12 | 18 |
| 4 | 4 850 | 12 | 17 | 10 | 17 |
| 5 | 4 450 | 14 | 38 | 9 | 15 |
| 6 | 3 850 | 11 | 57 | 8 | 12 |

Chaque fiche se termine par une annexe qui liste tous les fichiers de sa partie, avec une ligne d'explication. Elle sert de référence : pas besoin de l'apprendre par cœur. À elles toutes, les fiches couvrent les 78 fichiers de code du dépôt, toutes les bibliothèques Python et les 45 mesures du rapport.

Les deux fiches les plus courtes ont une contrepartie. La partie 1 parle le plus, car elle ouvre et ferme la soutenance. La partie 6 a les notions les plus difficiles, les statistiques. Le volume est comparable, pas la difficulté : donnez la partie 6 à celui qui est le plus à l'aise avec les maths, la partie 4 à celui qui aime le SQL, et la partie 1 à celui qui parle le mieux devant un jury.

## Comment les parties s'enchaînent

```
 Partie 1  Le besoin : que veut savoir la Direction Financière ?
    │
 Partie 2  Les données : séries réelles + opérations simulées, exportées par 4 systèmes « sales »
    │        fichiers CSV dans data/sources_internes/
 Partie 3  Le chargement : Python copie les fichiers tels quels dans PostgreSQL (schéma raw)
    │
 Partie 4  Le nettoyage : dbt corrige, dédoublonne, trace les rejets (schémas staging, intermediate)
    │
 Partie 5  Le modèle : dbt construit l'étoile et les calculs (schéma marts), Power BI l'affiche
    │
 Partie 6  La prévision : Python prévoit et simule (schéma ml), dbt en fait des marts, Power BI les affiche
    │
 Partie 1  Les résultats : ce que la banque gagne, et ce qu'il reste à vérifier
```

Quand le prof pose une question à la frontière de deux parties, les deux personnes doivent savoir y répondre. Chaque fiche termine par une section « Avec qui tu travailles » qui liste ces frontières.

## Ce que tout le monde doit savoir

Même si chacun a sa partie, ces points doivent être connus de tous.

**Le projet en 30 secondes.** ZF Banque a 10 filiales dans 10 pays. Sa Direction Financière veut piloter sa trésorerie : savoir chaque jour combien elle a, prévoir le mois suivant, décider quand emprunter, quand placer et quoi couvrir contre le change, et savoir combien de temps elle tient en cas de crise. Nous avons construit une chaîne complète, des fichiers bruts des filiales jusqu'à un tableau de bord Power BI, sur 3 ans (2023-2025).

**Réel et simulé.** Les dépôts, les taux directeurs, les cours de change et les jours fériés sont réels. Les opérations des clients et leurs défauts sont simulés, car aucune banque ne les publie. Le total des opérations simulées retombe exactement sur les vrais dépôts publiés par les banques centrales.

**Pas d'IA dans les calculs.** Les prévisions utilisent des méthodes statistiques classiques : moyenne, lissage, régression, simulation. Claude Code a aidé à écrire le projet ; il faut le dire franchement si le prof pose la question, et surtout savoir expliquer ce qu'on présente.

**Les 6 chiffres à connaître par cœur** (gros volume, au 31/12/2025) :

| Chiffre | Valeur | Ce qu'il veut dire |
|---|---|---|
| Position de trésorerie | 5,53 Md€ | L'argent disponible du groupe à la fin de 2025 |
| Ratio de liquidité | 157,6 % | La position couvre 1,6 fois le besoin à 30 jours |
| Refinancement 2023 | 3,98 Md€ | Ce que le groupe a dû emprunter quand les dépôts ont baissé |
| Erreur de prévision | 14,5 % | L'écart moyen entre le prévu et le réel |
| Contrôle sur janvier 2026 | 7 filiales sur 9 | Les vrais dépôts tombent dans la fourchette prévue |
| Panique bancaire | 10,77 Md€ à trouver | Le besoin de liquidité si 20 % des dépôts partent d'un coup |

**Les 4 outils.** Python (extraction, génération, chargement, prévision), PostgreSQL (l'entrepôt de données), dbt (les transformations SQL et les tests), Power BI (le tableau de bord).

## Comment travailler ta fiche

1. **Lis ta fiche en entier**, puis ouvre chaque fichier cité pour voir le code en vrai.
2. **Lance les commandes** de la section « Pour t'entraîner ». Voir les données dans pgAdmin ou dans Power BI aide beaucoup à retenir.
3. **Réponds à voix haute** aux questions du prof listées dans ta fiche, sans la regarder.
4. **Explique ta partie à un autre membre** en 5 minutes. Si tu bloques sur un point, c'est celui à revoir.
5. **Lis la section « Ce que tout le monde doit savoir »** ci-dessus et le [guide du projet](../00_guide_du_projet.md).

## Avant la soutenance

- [ ] Chacun sait dire sa partie en une minute, sans notes.
- [ ] Chacun connaît les chiffres de sa partie et les 6 chiffres communs.
- [ ] Chacun sait ce qui est réel et ce qui est simulé.
- [ ] Chacun sait montrer sa partie : un fichier, une table dans pgAdmin ou une page Power BI.
- [ ] Le groupe a répété l'enchaînement des diapos au moins une fois.
- [ ] Le groupe a validé la grille de choix, le RACI et le TCO (ce sont des hypothèses).
