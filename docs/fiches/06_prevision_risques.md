# Partie 6 : prévision, simulation et stress tests

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **la partie prédictive** du sujet : comment on prévoit les flux du mois suivant, comment on mesure l'erreur, comment la simulation Monte-Carlo donne une fourchette et une réserve, et comment fonctionnent les stress tests et le simulateur. Le change (fourchette, VaR, couverture) est présenté par la partie 2. C'est la partie la plus mathématique : tu dois savoir expliquer chaque méthode avec des mots simples.

**Diapos :** 13 (anticiper), 14 (la partie « résister » ; la partie 2 présente « couvrir »).

**Fichiers :** `etl/prevision.py`, `etl/controle_a_posteriori.py`, `dbt/models/marts/prevision/`, `dbt/models/marts/analyses/mart_stress_test.sql`, `dbt/seeds/ref_scenarios_stress.csv`, la section 6 de `powerbi/mesures_dax.dax`.

## À savoir dire en une minute

> Pour chaque filiale, nous prévoyons séparément les encaissements et les décaissements de chaque jour du mois suivant. Trois modèles sont mis en concurrence : un modèle naïf qui sert de référence, un lissage de Holt-Winters et une régression sur le calendrier. On les teste sur trois mois passés que le modèle n'a pas vus, et on garde celui qui a la plus petite erreur, le WAPE. La régression gagne sur les 20 séries, avec 14,5 % d'erreur au niveau du groupe. Ensuite, une simulation Monte-Carlo rejoue 1 000 fois le mois suivant à partir des erreurs passées : on obtient une fourchette, la probabilité de passer sous le besoin de liquidité, et la réserve qui suffit dans 99 % des cas. Notre meilleure preuve : les vrais dépôts de janvier 2026, publiés après, tombent dans la fourchette pour 7 filiales sur 9. Enfin, 7 scénarios de crise et un simulateur à 4 curseurs disent combien de temps chaque filiale tient.

**À dire clairement :** il n'y a pas d'intelligence artificielle dans ces calculs. Ce sont des méthodes statistiques classiques, simples à expliquer.

## 1. Les notions à maîtriser

### Prévision

| Notion | En clair |
|---|---|
| **Série temporelle** | Une suite de valeurs datées : les décaissements de la France chaque jour |
| **Horizon** | Jusqu'où l'on prévoit : ici le mois suivant, jour par jour |
| **Apprentissage et test** | On ajuste le modèle sur le passé (apprentissage), puis on mesure son erreur sur une période qu'il n'a pas vue (test) |
| **Backtest** | Rejouer la prévision à une date passée et la comparer à ce qui s'est vraiment passé |
| **WAPE** | Weighted Absolute Percentage Error : la somme des écarts absolus divisée par la somme du réel. 14,5 % veut dire que l'on se trompe en moyenne de 14,5 % du montant |
| **Modèle naïf** | La prévision la plus simple possible. Un modèle n'est utile que s'il fait mieux |
| **Lissage exponentiel** | Une moyenne qui donne plus de poids aux valeurs récentes |
| **Holt-Winters** | Un lissage exponentiel qui suit aussi une tendance et un rythme qui se répète (ici chaque semaine) |
| **Régression linéaire** | On explique une valeur par une somme pondérée de variables. Les poids sont trouvés par la méthode des moindres carrés |
| **Variable indicatrice** | Une variable qui vaut 1 ou 0 : « ce jour est férié », « on est en janvier » |
| **Champion / challenger** | On met plusieurs modèles en concurrence et on garde le meilleur, série par série |
| **Résidu** | L'écart entre le réel et ce que le modèle a calculé |

### Simulation et statistiques

| Notion | En clair |
|---|---|
| **Monte-Carlo** | On rejoue un grand nombre de fois un avenir possible, en tirant le hasard, puis on regarde la répartition des résultats |
| **Trajectoire** | Un avenir simulé, jour par jour |
| **Rééchantillonnage par blocs (bootstrap)** | On fabrique des erreurs futures en recopiant au hasard des morceaux de 7 jours d'erreurs passées. Les blocs gardent le rythme de la semaine |
| **Quantile, P5, P50, P95** | P5 : 5 % des trajectoires sont en dessous. P50 : le milieu. P95 : 5 % sont au-dessus. Entre P5 et P95, on a 90 % des cas : c'est la fourchette à 90 %. Dans le rapport : bas, milieu, haut |
| **P99** | La valeur qui suffit dans 99 % des cas |
| **Hors échantillon** | Tester sur des données réelles postérieures, que le modèle n'a jamais vues |

### Risques

| Notion | En clair |
|---|---|
| **Stress test** | Une crise imaginaire appliquée à la position d'aujourd'hui |
| **Reverse stress test** | Un scénario extrême qui combine tous les chocs, pour voir ce qui casse |
| **Horizon de survie** | Les jours avant que la position tombe à zéro pendant la crise |

## 2. La prévision des flux (`etl/prevision.py`)

### Les données

Python lit `marts.fct_position_tresorerie_quotidienne` : les encaissements et les décaissements de chaque jour de 2023 à 2025, pour chaque filiale, en devise locale. Il y a 20 séries à prévoir : 10 filiales × 2 séries.

### Les 3 modèles

**1. Le naïf hebdomadaire**, la référence à battre :

```python
def prevoir_naif(y, futur, code_pays):
    recent = y.iloc[-28:]
    profil = recent.groupby(recent.index.weekday).mean()
    return profil.reindex(futur.weekday).to_numpy()
```

On prend les 4 dernières semaines, on calcule la moyenne de chaque jour de la semaine (tous les lundis, tous les mardis…), et on répète ce profil sur le mois suivant.

**2. Holt-Winters** :

```python
ExponentialSmoothing(y.iloc[-365:].to_numpy() + 1.0, trend="add", damped_trend=True,
                     seasonal="mul", seasonal_periods=7, …).fit()
```

Appris sur la dernière année, avec une tendance amortie (elle ralentit dans le futur) et un rythme hebdomadaire multiplicatif (le lundi vaut, par exemple, 1,2 fois la moyenne). On ajoute 1 avant le calcul pour éviter les valeurs nulles, puis on le retire.

**3. La régression calendaire**, qui gagne :

```python
colonnes = [np.ones(len(c)), c.ouvre, c.ferie,
            ((c.rang >= 1) & (c.rang <= 3)).astype(float),          # 3 premiers jours ouvrés du mois
            ((c.rang_fin >= 1) & (c.rang_fin <= 2)).astype(float),  # 2 derniers jours ouvrés
            (c.ouvre * c.date.dt.day.between(13, 15)).astype(float),# mi-mois
            (c.date - debut_tendance).dt.days.astype(float) / 365]  # tendance
colonnes += [(c.date.dt.weekday == j).astype(float) for j in range(1, 7)]   # jour de la semaine
colonnes += [(c.date.dt.month == m).astype(float) for m in range(2, 13)]    # mois de l'année
coef, *_ = np.linalg.lstsq(X, y, rcond=None)
```

Chaque jour est décrit par des variables connues à l'avance : jour ouvré ou férié (avec les vrais jours fériés du pays), début ou fin de mois, mi-mois, jour de la semaine, **mois de l'année**, et une tendance. La régression trouve le poids de chaque variable sur les 3 ans d'historique (`lstsq` : moindres carrés). Pour prévoir, on calcule les mêmes variables pour les jours futurs et on applique les poids.

**L'effet « mois »** a été ajouté après le premier contrôle sur janvier 2026 : il capte la vraie saisonnalité des dépôts, en hausse en décembre et en baisse en janvier. La couverture de la fourchette est alors passée de 4 filiales sur 9 à 7 sur 9.

### Le backtest et le choix du champion

```python
ORIGINES_BACKTEST = ["2025-09-30", "2025-10-31", "2025-11-30"]
...
apprentissage, test = y[y.index <= origine], y[(y.index > origine) & (y.index <= fin)]
prevu = modele(apprentissage, test.index, code_pays)
scores[nom].append(wape(test.to_numpy(), prevu))
...
champion = min(moyenne, key=moyenne.get)
```

1. On se place fin septembre 2025, on apprend sur tout ce qui précède et on prévoit octobre. On recommence fin octobre (pour novembre) et fin novembre (pour décembre).
2. Pour chaque modèle, on calcule le WAPE de chacun des 3 mois.
3. Le champion est le modèle qui a la plus petite moyenne. Un modèle qui diverge (valeurs infinies ou plus de 3 fois le maximum observé) est éliminé.

```python
def wape(reel, prevu):
    return float(np.abs(reel - prevu).sum() / max(reel.sum(), 1e-9))
```

### Les résultats

WAPE moyen des 10 filiales :

| Modèle | Décaissements | Encaissements |
|---|---|---|
| Naïf hebdomadaire | 17,6 % | 45,9 % |
| Holt-Winters | 16,4 % | 78,5 % |
| **Régression calendaire** | **13,3 %** | **16,7 %** |

- La régression est championne sur les **20 séries sur 20**.
- Avec le champion, l'erreur va de 12,0 % à 15,4 % sur les décaissements et de 12,1 % à 27,6 % sur les encaissements ; les encaissements des États-Unis sont les plus difficiles à prévoir (27,6 %).
- Au niveau du groupe, en euros : **14,5 %**.
- Holt-Winters se trompe beaucoup sur les encaissements, sans doute parce que les salaires arrivent en pic en fin de mois, ce qu'un rythme hebdomadaire ne voit pas.

### Toutes les fonctions de `etl/prevision.py`

| Fonction | Rôle |
|---|---|
| `variables_calendrier` | Fabrique les variables du calendrier : jours ouvrés et fériés, début et fin de mois, mi-mois, jour, mois, tendance |
| `prevoir_naif`, `prevoir_holt_winters`, `prevoir_regression` | Les 3 modèles ; Holt-Winters vient de la bibliothèque `statsmodels` |
| `ajuster_regression` | Trouve les poids de la régression par les moindres carrés (`numpy.linalg.lstsq`) |
| `wape` | L'erreur d'une prévision |
| `est_divergent` | Écarte une prévision absurde : infinie, ou plus de 3 fois le maximum observé |
| `backtester` | Teste les 3 modèles sur 3 mois passés et choisit le champion |
| `ecart_type_mensuel` | Mesure l'incertitude du flux net d'un mois, pour le choc mensuel |
| `charger_donnees` | Lit les positions et les paramètres des filiales dans la base |
| `blocs_erreurs` | Tire des blocs de 7 jours d'erreurs passées |
| `prevoir_tresorerie` | La prévision, la simulation et la réserve, filiale par filiale |
| `prevoir_change` | La fourchette de change (partie 2) |
| `lancer_previsions` | Lance tout, puis écrit les résultats dans 4 tables du schéma `ml` avec `to_sql` |

La graine aléatoire fixée à 42 rend les 1 000 trajectoires identiques d'un lancement à l'autre : tout le groupe obtient les mêmes chiffres.

## 3. La simulation Monte-Carlo et la réserve

### Simuler 1 000 mois de janvier

```python
NB_SIM_FLUX = max(PREVISION_NB_SIMULATIONS, 1000)
...
etat = rng.bit_generator.state
e_enc = blocs_erreurs(erreurs_relatives["encaissements"][:n], len(futur), NB_SIM_FLUX, rng)
rng.bit_generator.state = etat
e_dec = blocs_erreurs(erreurs_relatives["decaissements"][:n], len(futur), NB_SIM_FLUX, rng)
net = niveaux["encaissements"][:, None] * (1 + e_enc) - niveaux["decaissements"][:, None] * (1 + e_dec)
net = net + rng.normal(0, sigma_mois, NB_SIM_FLUX)[None, :] / len(futur)
```

1. Le champion donne la prévision centrale de chaque jour de janvier 2026.
2. On a gardé les **erreurs relatives** du champion au backtest (par exemple : le réel a été 8 % au-dessus du prévu ce jour-là).
3. Pour chaque trajectoire, on recopie au hasard des **blocs de 7 jours** de ces erreurs, et on les applique à la prévision. Un bloc garde l'enchaînement des erreurs sur plusieurs jours de suite : quand le modèle se trompe un jour, il se trompe souvent dans le même sens le lendemain.
4. **Le même tirage** sert aux encaissements et aux décaissements (on remet le générateur aléatoire dans le même état) : une journée chargée l'est des deux côtés, comme dans la réalité.
5. On ajoute un **choc mensuel** sur le flux net, d'après les écarts mensuels passés du modèle, pour ne pas sous-estimer l'incertitude sur le niveau du mois.
6. On obtient 1 000 trajectoires de flux net, jour par jour.

### Ce qu'on en tire

```python
position = reserve_pct * depots_fin + net.cumsum(axis=0)     # rééquilibrage au 1er du mois
besoin = TAUX_FUITE_LCR * depots
resultat["proba_sous_besoin_liquidite"] = (position < besoin).mean(axis=1)
```

- **La fourchette** de la position : P5, P50 et P95 de chaque jour, sur les 1 000 trajectoires.
- **La probabilité de passer sous le besoin** de liquidité, chaque jour : la part des trajectoires où la position est sous 10 % des dépôts. La carte de la page Prévisions montre la plus forte : 91,1 % pour la Finlande.

### La réserve requise à 99 %

```python
manque = ((besoin - net.cumsum(axis=0)) / depots_fin).max(axis=0)
reserve_requise = float(np.quantile(manque, CONFIANCE_RESERVE))   # 0,99
liberable = (reserve_pct - reserve_requise) * depots_fin
```

1. Pour chaque trajectoire, on cherche la réserve de départ qui aurait juste suffi pour rester au-dessus du besoin **tout le mois**.
2. On prend la valeur qui suffit dans 99 % des trajectoires : c'est la réserve requise.
3. La différence avec la réserve actuelle est la liquidité **libérable** (positive) ou **à lever** (négative). Placée au taux directeur, elle donne un gain annuel.

| Filiale | Réserve actuelle | Réserve requise | À placer (+) ou à lever (−) |
|---|---|---|---|
| France | 15 % | 18,11 % | −352 M€ |
| Benelux | 15 % | 19,53 % | −195 M€ |
| Finlande | 15 % | 20,57 % | −135 M€ |
| Côte d'Ivoire | 20 % | 17,69 % | +34 M€ |
| Cameroun | 20 % | 14,01 % | +36 M€ |
| Norvège | 15 % | 14,13 % | +22 M€ |

Les 3 filiales en sur-réserve libèrent **90,9 M€**, qui rapportent **3,56 M€ par an** au taux réel de leur banque centrale. En zone CFA, le placement reste local à cause du contrôle des changes.

### Le contrôle sur les vrais dépôts de janvier 2026

`etl/controle_a_posteriori.py` compare la fourchette prévue au 31/01/2026 aux dépôts réels publiés ensuite par les banques centrales (gardés dans `data/sources/depots_reels_janvier_2026.csv`).

| Résultat | Filiales |
|---|---|
| Dans la fourchette | Benelux, Canada, Côte d'Ivoire, Danemark, France, Norvège, États-Unis : **7 sur 9** |
| Hors fourchette | Finlande (−3,89 %), Suède (−3,65 %) : les vrais dépôts ont été plus hauts que prévu |
| Non contrôlé | Cameroun : la BEAC ne publie pas de point mensuel |

C'est **la preuve la plus solide** du projet, car ces dépôts sont réels et le modèle ne les avait pas vus.

**Comment le contrôle est codé** (`etl/controle_a_posteriori.py`) :
- `depots_publies` lit les dépôts de janvier 2026 gardés dans `data/sources/depots_reels_janvier_2026.csv`, et ne télécharge que ceux qui manquent. Si une source ne répond pas, la filiale est signalée et le contrôle est marqué incomplet.
- `controler` ramène chaque dépôt réel à la part de marché de ZF Banque, le compare à la fourchette prévue au 31/01/2026, calcule l'erreur et écrit la table `ml.controle_depots_reels`.

## 4. Les stress tests et le simulateur

### Les 7 scénarios (`dbt/seeds/ref_scenarios_stress.csv`)

| Scénario | Retraits | Change | Taux | Sorties | Inspiré de |
|---|---|---|---|---|---|
| Central | 0 | 0 | 0 | × 1 | La tendance des 30 derniers jours |
| Retraits modérés | 5 % | 0 | +50 pb | × 1,5 | Northern Rock (2007) |
| Panique bancaire | 20 % | 0 | +150 pb | × 2,5 | Silicon Valley Bank (2023) |
| Chute du dollar | 0 | USD −10 %, CAD −8 % | 0 | × 1 | Le dollar en 2017 et en 2025 |
| Chute des couronnes | 0 | SEK et NOK −12 % | +50 pb | × 1,2 | Les couronnes entre 2020 et 2023 |
| Dévaluation du franc CFA | 3 % | −50 % | +200 pb | × 1,3 | La dévaluation de janvier 1994 |
| Crise combinée | 10 % | tous les chocs | +200 pb | × 2 | Scénario extrême (reverse stress test) |

La couronne danoise n'est jamais choquée, car elle est liée à l'euro.

### Le calcul (`mart_stress_test`, règles RG-STR)

```
position après change   = position × (1 + choc de change)                              (RG-STR-01)
retraits massifs        = dépôts × (1 + choc de change) × choc de retraits             (RG-STR-02)
position stressée       = position après change − retraits massifs
flux net quotidien      = (encaissements moyens − décaissements moyens × multiplicateur)
                          × (1 + choc de change)                                        (RG-STR-03)
horizon de survie       = position stressée / sortie nette quotidienne                  (RG-STR-04)
besoin de refinancement = sorties stressées sur 30 jours − position stressée, si > 0    (RG-STR-05)
coût annuel du besoin   = besoin × (taux directeur + 0,5 point + choc de taux)
```

Les moyennes d'encaissements et de décaissements portent sur les 30 derniers jours, pour lisser le cycle des salaires et des prélèvements. Le statut est **Critique** si la position est négative ou la survie inférieure à 7 jours, **Vigilance** de 7 à 30 jours, **Résilient** au-delà.

### Les résultats (gros volume)

| Scénario | Position après choc | À trouver | Survie |
|---|---|---|---|
| Central | 5,53 Md€ | 0 | Pas de fuite marquée |
| Retraits modérés | 3,78 Md€ | 166 M€ | 22 à 51 jours hors zone CFA |
| Crise combinée | 1,82 Md€ | 3,82 Md€ | 3 à 38 jours |
| Panique bancaire | −1,49 Md€ | 10,77 Md€ | 0 jour (2 à 8 en zone CFA) |

En panique, trouver 10,77 Md€ coûterait **481 M€ par an**, dont 162 M€ dus à la hausse des taux. Le besoin est plus grand que le déficit, car il couvre 30 jours de sorties en crise, filiale par filiale. Les chocs de change seuls ne créent aucun besoin : ce sont les retraits et les sorties massives qui mettent le groupe en danger.

### Le simulateur Power BI

Les mêmes formules sont réécrites en DAX, avec les 4 curseurs comme paramètres :

```dax
Position stressée (EUR) =
SUMX ( VALUES ( dim_filiale[code_filiale] ),
    ( [Position de trésorerie (EUR)] - [Encours de dépôts (EUR)] * [Valeur Choc retraits %] / 100 )
        * [Facteur choc change] )

Besoin de refinancement stressé (EUR) =
SUMX ( VALUES ( dim_filiale[code_filiale] ),
    MAX ( 0, - [Flux net quotidien stressé (EUR)] * 30 - [Position stressée (EUR)] ) )
```

`SUMX` sur les filiales calcule **filiale par filiale** puis additionne : l'excédent d'une filiale ne couvre pas le besoin d'une autre. La recette (ligne A4) vérifie que le simulateur réglé sur la panique (retraits 20 %, sorties × 2,5, taux +150 pb) donne exactement les chiffres de `mart_stress_test`.

## 5. Les marts de prévision

Le pipeline écrit 5 tables dans le schéma `ml`, puis dbt les reprend dans des marts lus par Power BI :

| Mart | Contenu |
|---|---|
| `mart_prevision_tresorerie` | Position réalisée jusqu'au 31/12/2025, puis prévue (P5, P50, P95) en janvier 2026, en devise et en euros |
| `mart_backtest_journalier` | Réel et prévu, jour par jour, pour les 3 modèles et les 3 origines, en devise et en euros |
| `mart_reserve_optimale` | Réserve actuelle, réserve requise, libérable, gain annuel, diagnostic |
| `mart_prevision_change` | Cours historiques, puis fourchette à 30 jours et cours réel (expliqué en partie 2) |
| `mart_controle_a_posteriori` | Dépôts prévus et réels au 31/01/2026, erreur, dans la fourchette ou non |

En simplifié, `mart_prevision_tresorerie` met bout à bout le réalisé et la prévision :

```sql
select …, 'Réalisé' as type_valeur, position_cloture_eur as position_p50_eur, …
from {{ ref('fct_position_tresorerie_quotidienne') }}
union all
select …, 'Prévision' as type_valeur, p.position_p50_devise / t.taux_eur_jour, …
from {{ source('ml', 'prevision_tresorerie_quotidienne') }} p join taux_arrete t …
```

- Dans le réalisé, bas, milieu et haut sont égaux : la courbe ne s'ouvre qu'en janvier 2026.
- La prévision est convertie en euros au cours du 31/12/2025 (**RG-PRV-01**, change constant), pour isoler le risque de liquidité du risque de change.
- `mart_backtest_journalier` convertit le réel et le prévu en euros au cours de chaque jour, pour le WAPE du groupe.
- `mart_reserve_optimale` ajoute le diagnostic : liquidité à placer ou à lever.
- Ces marts ont l'étiquette `prevision` : ils sont construits après Python, par `dbt build --select tag:prevision`.

## 6. Les questions probables du prof

**Y a-t-il de l'IA dans votre projet ?**
Non, pas dans les calculs : ni réseau de neurones ni modèle génératif. Sur 3 ans de données quotidiennes, des modèles statistiques simples suffisent et s'expliquent à la Direction Financière.

**La régression gagne sur 20 séries sur 20 : ce n'est pas trop beau ?**
Si, en partie, et il faut le dire : notre générateur crée un rythme calendaire, et la régression le retrouve. C'est pour cela que notre vraie preuve est le contrôle sur les dépôts réels de janvier 2026, que le modèle n'avait pas vus.

**Pourquoi le WAPE et pas le MAPE ?**
Le MAPE fait la moyenne des erreurs en pourcentage de chaque jour : un jour presque vide, comme un dimanche, donne une erreur énorme. Le WAPE pondère par les montants, ce qui correspond à ce qui coûte de l'argent.

**Pourquoi un modèle naïf ?**
C'est la référence : un modèle qui ne bat pas « la même chose que les 4 dernières semaines » ne sert à rien.

**À quoi sert Monte-Carlo, si vous avez déjà une prévision ?**
Une prévision seule donne un chiffre ; la trésorerie a besoin de savoir le risque. Les 1 000 trajectoires donnent une fourchette, une probabilité de manquer de liquidité et la réserve qui suffit dans 99 % des cas.

**Pourquoi des blocs de 7 jours ?**
Parce que les erreurs ne sont pas indépendantes d'un jour à l'autre : quand le modèle se trompe un jour, il se trompe souvent dans le même sens les jours suivants. Tirer des blocs d'une semaine garde cet enchaînement ; tirer les jours un par un le ferait disparaître et sous-estimerait le risque. Les blocs ne sont pas calés sur le jour de la semaine.

**Le stress test de panique est-il réaliste ?**
Il s'inspire de Silicon Valley Bank, où 25 % des dépôts ont été demandés en une journée. Le but n'est pas de prédire la crise, mais de chiffrer ce qu'il faudrait trouver, pour négocier des lignes de secours à l'avance.

**Pourquoi la Finlande et la Suède sortent-elles de la fourchette ?**
Leurs vrais dépôts ont été 3,7 à 3,9 % plus hauts que prévu. C'est une erreur, mais dans le bon sens : il n'a pas manqué d'argent.

## 7. Les limites à assumer

- La régression est avantagée par le générateur, qui crée lui-même le rythme du calendrier.
- Seuls 3 mois de janvier permettent d'estimer l'effet saisonnier.
- Le backtest porte sur octobre, novembre et décembre 2025 : il ne contient aucun mois de janvier, le mois le plus difficile. Le champion est aussi choisi et mesuré sur ces mêmes 3 mois, ce qui rend son erreur un peu optimiste.
- La réserve à 99 % repose sur 1 000 trajectoires, donc sur les 10 pires : c'est un ordre de grandeur, pas une valeur au dixième près.
- La prévision du groupe additionne les fourchettes des filiales : la fourchette du groupe est donc large, ce qui est prudent.
- Les stress tests sont simplifiés : pas d'effet de contagion entre filiales, pas de vente d'actifs.
- Le Cameroun n'entre pas dans le contrôle de janvier 2026.

## 8. Pour t'entraîner

1. Relance seulement la prévision et lis le journal (champions, réserve requise) :
   ```bash
   python pipeline.py --etapes prevision dbt_prev
   ```
2. Dans pgAdmin, compare les 3 modèles pour la France :
   ```sql
   select serie, modele, round((100 * sum(abs(reel_devise - prevu_devise)) / sum(reel_devise))::numeric, 1) as wape
   from marts.mart_backtest_journalier where code_filiale = 'FR' group by 1, 2 order by 1, 3;
   ```
3. Sur la page Simulateur, règle retraits 20 %, sorties × 2,5, taux 150 pb : retrouve −1,49 Md€, 10,77 Md€ et 480,79 M€.

## 9. Avec qui tu travailles

| Partie | La frontière |
|---|---|
| 1. Besoin et KPI | Tes résultats sont les gains qu'elle présente : réserve et résilience |
| 2. Données et change | La régression retrouve le calendrier du générateur, une limite à connaître ensemble ; elle présente le change avec la même idée de simulation et de quantiles |
| 5. Modèle et Power BI | Tu lis son fait de position ; ses pages affichent tes marts ; le simulateur est écrit en DAX |
| 3. Chargement | Python écrit dans le schéma `ml`, puis dbt construit les marts de prévision |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| `etl/prevision.py` | Les modèles, le backtest, la simulation, la réserve et le change |
| `etl/controle_a_posteriori.py` | Le contrôle sur les dépôts réels de janvier 2026 |
| `data/sources/depots_reels_janvier_2026.csv` | Les dépôts publiés pour ce contrôle |
| `dbt/models/marts/prevision/mart_prevision_tresorerie.sql` | Le réalisé, puis la fourchette prévue |
| `dbt/models/marts/prevision/mart_backtest_journalier.sql` | Le réel et le prévu, en devise et en euros |
| `dbt/models/marts/prevision/mart_reserve_optimale.sql` | La réserve requise et le diagnostic |
| `dbt/models/marts/prevision/mart_controle_a_posteriori.sql` | Le résultat du contrôle de janvier 2026 |
| `dbt/models/marts/analyses/mart_stress_test.sql` | Les 7 scénarios appliqués à chaque filiale |
| `dbt/seeds/ref_scenarios_stress.csv` | Les chocs de chaque scénario |
| `powerbi/mesures_dax.dax`, section 6 | Les mesures du simulateur |
| Schéma `ml` | Les 5 tables écrites par Python : `prevision_tresorerie_quotidienne`, `backtest_prevision`, `reserve_optimale`, `prevision_change`, `controle_depots_reels` |
| [docs/03](../03_analyse_predictive_et_simulation.md) | Les modèles et leurs résultats |
