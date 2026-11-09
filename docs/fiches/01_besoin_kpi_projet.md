# Partie 1 : besoin, KPI et pilotage du projet

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **pourquoi** le projet existe et **ce qu'il rapporte**. Tu ouvres la soutenance avec le besoin de la banque, et tu la refermes avec les résultats et les gains. Tu présentes aussi la gouvernance et le pilotage du projet : le RACI, le planning et le TCO. La grille de choix et le SWOT sont présentés par la partie 3, et les priorités MoSCoW par la partie 4 : connais-les dans les grandes lignes.

Ta partie contient peu de code, mais beaucoup de notions de finance. Tu dois pouvoir expliquer chaque KPI avec des mots simples et un exemple chiffré.

**Diapos :** 1, 2, 3 (contexte), 8 (KPI et gouvernance), 10 (impacts), 16 (conclusion).

## À savoir dire en une minute

> ZF Banque est un groupe de 10 filiales dans 10 pays, avec 8 devises. Sa Direction Financière gère la trésorerie avec des tableurs : elle découvre les besoins d'argent au dernier moment et garde des réserves de précaution trop larges. La question du sujet est de savoir comment la prévision et la simulation peuvent faire gagner de l'argent. Notre réponse : elles font gagner parce qu'elles permettent de décider plus tôt. On prépare un emprunt au lieu de le subir, on place l'argent qui dort, on choisit quoi couvrir contre le change et on sait combien de temps on tient en crise. Nous l'avons démontré sur 3 ans de données calées sur les vrais dépôts publiés par les banques centrales, avec 6 KPI et un tableau de bord Power BI.

## 1. Comprendre la trésorerie d'une banque

Ces notions reviennent dans toutes les parties. Tu dois être la personne du groupe qui les explique le mieux.

| Notion | En clair | Exemple dans le projet |
|---|---|---|
| **Dépôt à vue** | L'argent des clients sur leur compte courant. Le client peut le retirer quand il veut : pour la banque, c'est une dette à rembourser à tout moment | Les dépôts réels de chaque pays, publiés par les banques centrales |
| **Encours de dépôts** | Le total des dépôts à une date donnée. C'est un **stock** | 35,11 Md€ pour le groupe au 31/12/2025 |
| **Flux** | Ce qui entre (encaissements : salaires, dépôts d'espèces, virements reçus) et ce qui sort (décaissements : cartes, retraits, prélèvements, virements émis) | 234,1 Md€ d'encaissements et 235,7 Md€ de décaissements sur 3 ans |
| **Flux net** | Encaissements moins décaissements. Négatif : la banque perd de l'argent ce jour-là | |
| **Position de trésorerie** | L'argent immédiatement disponible à la fin de la journée, c'est-à-dire la réserve de liquidité | 5,53 Md€ pour le groupe fin 2025 |
| **Taux de réserve** | La part des dépôts que la filiale garde disponible | 15 % en Europe, 20 % en zone CFA, 12 % en Amérique du Nord (hypothèses) |
| **Besoin de liquidité à 30 jours** | Ce qui pourrait sortir en un mois difficile. Nous le fixons à 10 % des dépôts | 3,51 Md€ pour le groupe (10 % de 35,11 Md€) |
| **Ratio de liquidité (LCR)** | Position divisée par le besoin à 30 jours. La règle de Bâle III impose au moins 100 %. Nous visons 110 % pour garder une marge | 5,53 / 3,51 = 157,6 % |
| **Refinancement** | Emprunter quand la position passe sous la cible. Programmé, il coûte le taux de la banque centrale ; en urgence, il coûte environ 0,25 point de plus | 6,94 Md€ levés sur 3 ans |
| **Placement** | Placer ce qui dépasse la cible, par exemple au taux de dépôt de la banque centrale | 5,60 Md€ placés sur 3 ans |
| **Taux directeur** | Le taux fixé par la banque centrale. Il fixe le coût d'un emprunt et le rendement d'un placement | Facilité de dépôt de la BCE : jusqu'à 4 % en 2023-2024, 2 % fin 2025 |
| **Devise et cours de change** | Chaque filiale tient ses comptes dans sa monnaie. Pour additionner les filiales, on convertit tout en euros au cours publié par la BCE | 1 € = environ 1,17 $ fin 2025 |
| **Parité fixe** | Le franc CFA (XOF en Afrique de l'Ouest, XAF en Afrique centrale) vaut toujours 655,957 pour 1 euro | Pas de risque de change au jour le jour, mais un risque de dévaluation |
| **Effet de change** | Ce que l'on gagne ou perd en euros uniquement parce que le cours a bougé | −58,2 M€ sur le dollar en 3 ans |
| **VaR (Value at Risk)** | La perte que l'on ne dépassera pas dans 95 % des cas, ici sur 10 jours | 26,6 M€ pour le groupe |
| **Couverture de change** | Un contrat qui fige le cours futur. Elle a un coût, à peu près l'écart de taux entre les deux monnaies | 15,3 M€ par an pour tout couvrir |
| **Stress test** | On applique une crise imaginaire (retraits massifs, chute d'une devise) et on regarde combien de temps la banque tient | 7 scénarios, dont Northern Rock (2007) et Silicon Valley Bank (2023) |
| **Horizon de survie** | Le nombre de jours avant que la position tombe à zéro pendant la crise | 22 à 51 jours avec des retraits modérés, hors zone CFA |
| **BCBS 239** | Les principes du Comité de Bâle sur la qualité des données de risque : exactes, complètes, traçables | Justifie le rapprochement au grand livre et le lineage |

**Pourquoi les dépôts baissent en 2023.** La BCE a monté ses taux très vite. Les comptes courants ne rapportent rien, alors les clients ont déplacé leur argent vers des livrets et des placements rémunérés. Les dépôts à vue ont baissé dans toute la zone euro, et la banque a dû emprunter pour garder sa réserve. C'est visible dans les vraies séries de la BCE, ce n'est pas une invention du projet.

## 2. ZF Banque et ses filiales

| Code | Filiale | Devise | Système source | Part de marché supposée | Taux de réserve |
|---|---|---|---|---|---|
| FR | France | EUR | SAB | 1 % | 15 % |
| BNL | Benelux (Belgique) | EUR | SAB | 2 % | 15 % |
| FI | Finlande | EUR | SAB | 2 % | 15 % |
| SE | Suède | SEK | NORDIC | 1 % | 15 % |
| DK | Danemark | DKK | NORDIC | 1 % | 15 % |
| NO | Norvège | NOK | NORDIC | 1 % | 15 % |
| CI | Côte d'Ivoire | XOF | DELTA | 8 % | 20 % |
| CM | Cameroun | XAF | DELTA | 8 % | 20 % |
| CA | Canada | CAD | AMERICORE | 0,2 % | 12 % |
| US | États-Unis | USD | AMERICORE | 0,03 % | 12 % |

Ces valeurs sont dans `dbt/seeds/ref_filiales.csv`. La part de marché sert à ramener les dépôts d'un pays entier à la taille de ZF Banque : en France, ZF Banque détient 1 % des dépôts à vue publiés par la BCE. **Ce sont des hypothèses** : les montants en euros en dépendent, les tendances non.

## 3. Du besoin aux pages du rapport

Le sujet fixe 5 objectifs. Chacun a ses indicateurs et sa page Power BI.

| Objectif du sujet | Indicateurs | Page Power BI |
|---|---|---|
| Optimiser l'arbitrage entre refinancement et placement | Position, ratio de liquidité, refinancement et placement | Cockpit DAF |
| Anticiper les entrées et sorties de cash | Fourchette bas / milieu / haut, WAPE, réserve requise | Prévisions |
| Élaborer une stratégie de couverture | VaR de change, décision par devise | Change & couverture |
| Mettre en place des scénarios de stress | Horizon de survie, besoin de refinancement | Simulateur de stress |
| Gérer l'hétérogénéité et intégrer des données externes | Taux de rejet, encours réel et reconstitué | Qualité des données |

## 4. Les 6 KPI

C'est le cœur de ta partie. Pour chaque KPI, sache dire sa définition, sa formule, son grain (ce que représente une ligne), sa source, son seuil et son propriétaire.

| KPI | Formule | Grain | Source | Seuil | Propriétaire proposé |
|---|---|---|---|---|---|
| Position de trésorerie | Position de clôture du dernier jour (c'est un stock) | jour × filiale | `fct_position_tresorerie_quotidienne` | Cible de réserve du mois | Trésorier groupe |
| Ratio de liquidité (LCR simplifié) | Position / (10 % des dépôts) | jour × filiale | `mart_liquidite_placement` | 100 % réglementaire, 110 % de pilotage | Risques (ALM) |
| Refinancement et placement | Opérations de fin de mois : > 0 levé, < 0 placé | mois × filiale | `fct_position_tresorerie_quotidienne` | Retour à la cible de réserve | Trésorier groupe |
| VaR de change 95 % à 10 jours | 1,645 × volatilité quotidienne × exposition × √10 | jour × devise | `mart_exposition_change` | Décision selon le coût et le risque | Salle des marchés |
| Horizon de survie | Position stressée / sorties nettes par jour | scénario × filiale | `mart_stress_test` | ≥ 30 j résilient, 7 à 30 j vigilance, < 7 j critique | Risques (ALM) |
| WAPE (erreur de prévision) | Σ \|réel − prévu\| / Σ réel | filiale × série | `mart_backtest_journalier` | Doit battre le modèle naïf | Contrôle de gestion |

**Comment les lire, avec un exemple.**

- **Position, 5,53 Md€.** On prend le dernier jour de la période et on additionne les filiales en euros. On n'additionne jamais les jours entre eux : 100 € lundi et 100 € mardi, ce n'est pas 200 €.
- **Ratio, 157,6 %.** Le groupe a 1,6 fois l'argent qu'il faudrait pour tenir un mois difficile. Sur 3 ans, une filiale est passée 175 fois sous 100 %, dont 60 fois en janvier.
- **Refinancement, 6,94 Md€, et placement, 5,60 Md€.** Chaque fin de mois, la réserve est ramenée à sa cible : si elle est trop basse, on emprunte ; si elle est trop haute, on place. Le refinancement domine en 2023, les placements en 2025.
- **VaR, 26,6 M€.** Dans 95 % des cas, le groupe ne perdra pas plus de 26,6 M€ sur 10 jours à cause du change. On additionne les VaR par devise, ce qui est prudent. Si les devises bougeaient indépendamment, elle serait d'environ 13,8 M€.
- **Horizon de survie.** Avec des retraits modérés, les filiales tiennent 22 à 51 jours hors zone CFA. En panique, elles tombent à 0 jour, sauf la zone CFA (2 à 8 jours).
- **WAPE, 14,5 %.** En moyenne, la prévision quotidienne s'écarte de 14,5 % du réel. On le calcule en euros pour ne pas donner trop de poids aux francs CFA, qui ont de très gros nombres.

**Pourquoi ces KPI et pas d'autres.** Le profilage des données a fait évoluer la liste (voir [docs/06](../06_profil_donnees_et_choix_kpi.md)). Un ancien ratio de liquidité comptait deux fois la tendance des flux et restait bloqué sous 100 % : il a été remplacé. Le netting et le taux de fraude ont été retirés, car ils ne répondaient à aucun objectif du sujet.

## 5. Les résultats et ce qu'ils rapportent

Tous les montants viennent du gros volume. Ce sont des **ordres de grandeur**, car ils dépendent des parts de marché supposées.

### Refinancement et placements par année

| En M€ | 2023 | 2024 | 2025 |
|---|---|---|---|
| Refinancement levé | 3 984 | 1 824 | 1 129 |
| Excédent placé | 813 | 2 169 | 2 618 |

Le groupe passe d'un besoin d'argent à un excédent. Le besoin de 2023 était prévisible, car il suit la baisse réelle des dépôts. Un emprunt préparé passe par les opérations normales de la banque centrale, au lieu de la facilité d'urgence qui coûte 0,25 point de plus : environ **2,5 M€ économisés par an pour chaque milliard**.

### Les 5 leviers de gain

| Levier | Ce qu'on a trouvé | Ce qu'on recommande |
|---|---|---|
| Moduler la réserve selon le mois | Janvier concentre 60 des 175 passages sous 100 %. La France aurait besoin de 18,1 % de réserve en janvier 2026, contre 15 % aujourd'hui | Préparer le financement de la France dès décembre, environ 352 M€ |
| Placer les excédents | Côte d'Ivoire, Cameroun et Norvège gardent trop de réserve : 90,9 M€ | Les placer rapporterait environ 3,56 M€ par an |
| Anticiper le refinancement | 3,98 Md€ levés en 2023 | Emprunter de façon programmée plutôt qu'en urgence |
| Couvrir le change avec discernement | −118 M€ d'effet de change en 3 ans, dont −58,2 M€ sur le dollar | Couvrir le CAD et la SEK, arbitrer USD et NOK, ne pas couvrir la DKK |
| Mesurer la résilience | En panique, il faudrait trouver 10,77 Md€ pour un coût de 481 M€ par an | Négocier des lignes de liquidité de secours à l'avance |

### La réponse à la problématique

> L'analyse prédictive fait passer la trésorerie d'un centre de coûts à un centre de profit, à trois conditions. **Prévoir** les flux par filiale permet de réduire les réserves de précaution et de placer l'argent qui dort. **Simuler** chiffre le risque de chaque décision. **Fiabiliser les données** est la condition de tout le reste : une prévision sur des données fausses fait perdre de l'argent.

## 6. La gouvernance et le pilotage du projet

Ces éléments sont dans le MOE et la réponse à l'appel d'offres. Ce sont **des propositions du groupe**, à valider ensemble avant la soutenance.

### Le RACI

R réalise, A valide et assume, C contribue, I est informé.

| Décision | Sponsor (DAF) | Data Owner (Trésorier groupe) | Data Steward (Trésorerie) | Équipe BI / Data | IT / Plateforme |
|---|---|---|---|---|---|
| Définition d'un KPI | C | A | R | C | I |
| Règle de qualité | I | A | R | C | C |
| Modèle sémantique | I | A | C | R | C |
| Accès et sécurité | I | C | C | R | A |
| Mise en production | I | C | C | R | A |

### Le planning proposé

| Phase | Durée | Contenu | Jalon |
|---|---|---|---|
| 0. Cadrage | 1 mois | Accès aux données, validation des hypothèses et des KPI, rôles | Périmètre signé |
| 1. Pilote France | 3 mois | Vraies données, recette, comparaison du prévu et du réalisé | GO ou NOGO sur les gains |
| 2. Europe | 3 mois | Benelux, Finlande, Suède, Danemark, Norvège | Cockpit Europe en service |
| 3. Afrique et Amérique du Nord | 3 mois | Côte d'Ivoire, Cameroun, Canada, États-Unis | Cockpit groupe en service |
| 4. Exploitation | Continu | Comité de trésorerie, réentraînement mensuel, suivi du WAPE | Revue annuelle |

**Pourquoi la France en pilote.** C'est la plus grosse position (1,84 Md€), elle est passée 23 fois sous 100 %, et son besoin de réserve est net (18,1 % contre 15 %).

### Le TCO (coût total de possession)

Hypothèses : 650 € par jour de travail, licence Power BI Pro à 14 € par mois. Ces valeurs sont à confirmer.

| Poste | Base de calcul | Montant |
|---|---|---|
| Build : cadrage et gouvernance | 30 jours | 19 500 € |
| Build : socle de données | 70 jours | 45 500 € |
| Build : prédictif et simulation | 30 jours | 19 500 € |
| Build : restitution | 25 jours | 16 250 € |
| Build : recette et formation | 25 jours | 16 250 € |
| **Total build** | 180 jours | **117 000 €** |
| Run : licences Power BI | 40 utilisateurs × 14 € × 12 mois | 6 720 € par an |
| Run : hébergement et ordonnanceur | Forfait supposé | 12 000 € par an |
| Run : maintenance et évolutions | 60 jours par an | 39 000 € par an |
| **Total run** | | **57 720 € par an** |
| **TCO sur 3 ans** | 117 000 € + 3 × 57 720 € | **290 160 €** |

Sur 3 ans, ce coût représente environ 3 % du seul gain de placement (3 × 3,56 M€ = 10,7 M€). Même si une petite partie du gain se confirme, le projet reste rentable. C'est ce que le pilote France doit vérifier.

### Les impacts si le projet n'est pas fait

Sans Crésus, le refinancement reste subi (3,98 Md€ levés en 2023, découverts tard), les réserves de précaution restent trop larges en zone CFA et en Norvège, le change continue de coûter sans stratégie, et personne ne sait combien de temps la banque tient en crise.

## 7. Les paramètres métier du projet

Tous les calculs reposent sur quelques paramètres. Ce sont des **hypothèses** : les changer change les montants, pas les mécanismes. Ils sont écrits à un seul endroit, dans `dbt/dbt_project.yml` (section `vars`) et dans `dbt/seeds/ref_filiales.csv`.

| Paramètre | Valeur | À quoi il sert |
|---|---|---|
| Période d'analyse | du 01/01/2023 au 31/12/2025 | Les 3 ans étudiés |
| Taux de fuite des dépôts | 10 % | Le besoin de liquidité à 30 jours, donc le ratio de liquidité |
| Cible de pilotage | 110 % | Au-dessus, on place ; en dessous, on se refinance |
| Marge de refinancement | 0,5 point | Le coût d'un emprunt = taux directeur + 0,5 point |
| Écart entre urgence et emprunt préparé | 0,25 point | Ce qu'on économise en préparant un emprunt |
| Seuil d'un gros ticket | 10 000 € | Le suivi des gros décaissements |
| Fenêtre des moyennes | 30 jours | Les moyennes de flux du ratio et des stress tests |
| Quantile de la VaR | 1,645 | La VaR à 95 % |
| Report d'un cours de change | 7 jours au plus | Week-ends et jours fériés ; au-delà, la série est rompue |
| Historique de change | 3 ans avant 2023 | Le calcul de la volatilité |
| Parts de marché et taux de réserve | par filiale | Voir la section 2 |

## 8. Les questions probables du prof

**Pourquoi la trésorerie est-elle un sujet important pour une banque ?**
Parce qu'une banque prête à long terme l'argent que les clients peuvent retirer à tout moment. Si trop de clients retirent en même temps, elle doit trouver de l'argent très vite et très cher. C'est ce qui a fait tomber Silicon Valley Bank en 2023.

**Comment la prévision fait-elle gagner de l'argent concrètement ?**
De trois façons : on garde moins de réserve inutile et on la place (3,56 M€ par an), on emprunte de façon programmée plutôt qu'en urgence (environ 2,5 M€ par an et par milliard), et on ne couvre que les devises où la couverture vaut son coût.

**Vos montants sont-ils réels ?**
Les tendances sont réelles, car elles viennent des dépôts publiés par les banques centrales. Les montants dépendent des parts de marché que nous avons supposées. C'est pour cela que nous proposons un pilote sur la France, avec de vraies données.

**Pourquoi un ratio de liquidité simplifié ?**
Le vrai LCR applique un taux de fuite différent selon le type de dépôt et compte des actifs liquides de qualité. Nous n'avons pas ce détail : nous prenons 10 % de tous les dépôts, ce qui donne le bon ordre de grandeur et reste facile à expliquer.

**Le TCO est-il fiable ?**
C'est une estimation : 180 jours de construction à 650 € et un fonctionnement à 57 720 € par an. L'important est le rapport : environ 3 % du gain attendu.

## 9. Les limites à assumer

- Les opérations sont simulées et les parts de marché supposées : les montants sont des ordres de grandeur.
- Le ratio de liquidité est simplifié, avec un taux de fuite unique de 10 %.
- La grille, le RACI, le planning et le TCO sont des propositions à valider.
- Le traitement se lance à la main : l'ordonnancement et la supervision restent à construire.

## 10. Pour t'entraîner

1. Ouvre `powerbi/Cresus/Cresus.pbip`, clique sur **Actualiser**, puis parcours les 5 pages en disant à voix haute quel objectif chacune sert.
2. Sur le Cockpit, filtre l'année 2023, puis 2025 : regarde le refinancement et les placements s'inverser.
3. Sur la page Prévisions, trouve la France dans le tableau de réserve et retrouve 15 % et 18,11 %.
4. Relis le [guide du projet](../00_guide_du_projet.md), sections 7 et 10.
5. Refais le calcul du TCO de 290 160 € sans regarder.

## 11. Avec qui tu travailles

| Partie | Ce qu'elle t'apporte |
|---|---|
| 2. Données | Pourquoi les dépôts réels baissent en 2023, ce qui est réel et ce qui est simulé |
| 5. Modèle et Power BI | Le calcul exact de la position, du ratio et du refinancement, et les pages du rapport |
| 6. Prévision et risques | La réserve requise, la VaR, la couverture et les stress tests |
| 3. Architecture | La grille de choix et le SWOT, qu'elle présente ; la note TCO de la grille vient de ton TCO |
| 4. Nettoyage et qualité | La recette, la décision GO, la méthodologie et les priorités MoSCoW |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| [docs/01](../01_cadrage_amoa.md) | Le cadrage : besoin, périmètre, prérequis |
| [docs/05](../05_synthese_swot_recommandations.md) | Le SWOT, les impacts et les leviers de gain |
| [docs/06](../06_profil_donnees_et_choix_kpi.md) | Pourquoi ces KPI, d'après le profilage des données |
| `dbt/dbt_project.yml`, section `vars` | Les paramètres métier |
| `dbt/seeds/ref_filiales.csv` | Les 10 filiales, leur part de marché et leur taux de réserve |
| `livrables/03_IBI_AMOA_FICHE_EXPERTISE_…` | La fiche d'expertise rendue |
| `livrables/IBI_AMOA_REPONSE_APPEL_OFFRES_…` | La réponse à l'appel d'offres : planning, TCO, RACI |
| `livrables/IBI_AMOA_WEBOGRAPHIE_…` | Les sources citées |
| `livrables/04_IBI_SUPPORT_SOUTENANCE_…` | Les diapos ; les notes orateur disent qui présente quoi |
| `CLAUDE.md`, section 7 | L'historique des décisions du projet, utile pour expliquer chaque choix |
