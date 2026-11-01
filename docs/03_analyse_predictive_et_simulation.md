# 03 — Analyse prédictive et simulation

> Données : 3 ans (2023-2025) de flux quotidiens par filiale, ancrés sur les dépôts réels (docs/07).
> Date d'arrêté : 31/12/2025. Mois prévu : janvier 2026.

## 1. Prévision des flux de trésorerie (pas quotidien)

| Modèle | Principe | Rôle |
|---|---|---|
| Naïf hebdomadaire | Moyenne du même jour de la semaine sur les 4 dernières semaines | Référence minimale |
| Holt-Winters | Lissage exponentiel, tendance amortie, saisonnalité hebdomadaire | Modèle de série temporelle classique |
| **Régression calendaire** | Moindres carrés sur des variables connues à l'avance : jour de la semaine, jour ouvré ou férié (calendrier de chaque pays), 3 premiers jours ouvrés, 2 derniers jours ouvrés, mi-mois, **mois de l'année**, tendance ; apprise sur les 3 ans | Capte les cycles de paie et de prélèvements, et la saisonnalité annuelle des dépôts |

**Backtest** : 3 origines (fin septembre, octobre et novembre 2025), avec chaque fois un mois complet prévu. Le WAPE (Σ|réel − prévu| / Σ réel) désigne le champion de chaque série.

| Série | Naïf | Holt-Winters | Régression calendaire | Champion |
|---|---|---|---|---|
| Décaissements | 17,6 % | 16,4 % | **13,3 %** | régression (10 filiales sur 10) |
| Encaissements | 45,9 % | 78,5 % | **16,7 %** | régression (10 sur 10) |

*Moyenne des 10 filiales, mesurée sur le gros volume (lots de 50) le 31/10/2026.*

Holt-Winters échoue sur les encaissements : les salaires arrivent en fin de mois, ce qui n'est pas une saisonnalité hebdomadaire.

## 2. Simulation Monte-Carlo et réserve requise
Pour chaque filiale, 1 000 trajectoires de janvier 2026 sont simulées :
- **erreurs quotidiennes** : on rééchantillonne, par blocs de 7 jours, les erreurs relatives du champion observées au backtest, avec les mêmes tirages pour les encaissements et les décaissements (leur corrélation est conservée) ;
- **choc mensuel** sur le flux net : son écart-type est estimé sur les résidus mensuels du modèle, corrigés des degrés de liberté. Il représente l'incertitude sur le niveau du mois, que le bruit quotidien seul sous-estime ;
- **position simulée** : réserve cible au 1er janvier + cumul des flux simulés.

On en tire :
- le cône **P5 / P50 / P95** de la position et des dépôts ;
- la **probabilité de passer sous le besoin Bâle III** (10 % des dépôts) ;
- la **réserve requise à 99 %** : la plus petite réserve qui maintient la position au-dessus du besoin tout le mois dans 99 % des trajectoires.

**Résultat pour janvier 2026** :

| Filiales | Réserve requise vs actuelle | Lecture |
|---|---|---|
| France, Benelux, Finlande | 18 à 20,6 % vs 15 % | Janvier est un mois de **décollecte réelle** (−3,4 % en moyenne en France) : il faut **pré-financer** en décembre |
| Suède, Danemark | 15,6 à 16,3 % vs 15 % | Idem, dans une moindre mesure |
| États-Unis, Canada | 13,3 à 13,7 % vs 12 % | Réserve insuffisante tout au long de l'année (sous 100 % 44 à 57 jours en 3 ans) |
| Côte d'Ivoire, Cameroun, Norvège | 14 à 18 % vs 15-20 % | **Sur-réserve** : liquidité à placer localement (~90 M€) |

La valeur de la prévision n'est donc pas une « économie » uniforme : elle **module la réserve selon le mois et la filiale**. On relève la réserve avant les mois de décollecte (pour éviter un ratio sous 100 %, sanctionnable), et on place les excédents structurels (zone CFA).

## 3. Contrôle sur des données réelles postérieures (hors échantillon)
Les banques centrales ont publié depuis les encours de **janvier 2026**. On les compare à la prévision arrêtée au 31/12/2025 (`etl/controle_a_posteriori.py`) :

| Version du modèle | Erreur médiane sur l'encours fin janvier | Réel dans la fourchette à 90 % |
|---|---|---|
| v1 (sans effet « mois », bruit quotidien seul) | +0,7 à +9,6 %, biais à la hausse | 4 filiales sur 9 |
| **v2 (effet « mois » + choc mensuel)** | **−3,9 à +1,2 %** (France −0,3 %, États-Unis +0,5 %) | **7 sur 9** |

C'est ce contrôle qui a révélé la saisonnalité de janvier. Le Cameroun est exclu du contrôle : aucun point mensuel BEAC pour janvier 2026 n'est disponible par API.

## 4. Prévision du change
Les cours de change sont proches d'une **marche aléatoire** (Meese & Rogoff, 1983). On prévoit donc une **fourchette à 30 jours** (mouvement brownien géométrique, volatilité des 250 dernières cotations) plutôt qu'un point. Contrôle sur les cours réels de janvier 2026 : **119 jours-devises sur 126 (94 %)** dans la fourchette à 90 %, conforme à l'attendu. Le RUB est exclu automatiquement (dernière cotation le 01/03/2022).

## 5. Stress tests
| Scénario | Retraits | Change | Taux | Sorties × | Référence historique |
|---|---|---|---|---|---|
| Central | 0 | 0 | 0 | 1,0 | Tendance des 30 derniers jours |
| Retraits modérés | 5 % | — | +50 pb | 1,5 | Northern Rock 2007 |
| Panique sévère | 20 % | — | +150 pb | 2,5 | SVB, mars 2023 (visible dans les dépôts réels américains) |
| Dépréciation du dollar | — | USD −10 %, CAD −8 % | — | 1,0 | 2017, S1 2025 |
| Couronnes nordiques | — | SEK, NOK −12 % | +50 pb | 1,2 | 2020-2023 |
| Dévaluation du CFA | 3 % | XOF/XAF −50 % | +200 pb | 1,3 | 12 janvier 1994 |
| Crise combinée | 10 % | tous les chocs | +200 pb | 2,0 | Reverse stress test |

Avec 3 ans de données, le scénario central n'a plus de fuite structurelle (horizon de survie illimité ou supérieur à 6 ans). Retraits modérés : 22 à 51 jours en Europe et en Amérique du Nord. Panique sévère : 0 jour, sauf en zone CFA (2 à 8 jours).

## 6. Limites
- Le profil à l'intérieur du mois (paie, prélèvements) est une hypothèse du générateur, et la régression utilise les mêmes variables. Sa précision quotidienne est donc en partie « attendue ». Le contrôle sur janvier 2026 porte, lui, sur des niveaux réels.
- Il n'y a que 3 Januaries pour estimer l'effet « mois » : c'est un effet moyen, avec une incertitude élevée (d'où le choc mensuel).
- Pistes d'industrialisation : historique plus long, variables exogènes (taux, inflation), modèles hiérarchiques filiale → groupe, réentraînement mensuel avec suivi du WAPE.
