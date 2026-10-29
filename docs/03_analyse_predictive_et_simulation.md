# 03 — Analyse prédictive et simulation

## 1. Prévision des flux de trésorerie

**Données** : séries horaires d'encaissements et de décaissements par filiale (en devise locale), sans trou (une heure sans opération vaut 0). On ne garde que des journées complètes (le dernier jour de PaySim s'arrête à 22 h).

**Modèles candidats**
| Modèle | Principe | Pourquoi |
|---|---|---|
| Naïf saisonnier | Pour chaque heure, moyenne des 7 derniers jours | Référence minimale : un modèle « intelligent » doit faire mieux |
| Holt-Winters | Lissage exponentiel (niveau + saisonnalité journalière de 24 h **multiplicative**) | Modèle de série temporelle classique, explicable, rapide |

**Backtest et sélection du champion** : chaque modèle est réentraîné sans les 3 derniers jours complets, puis on compare ses prévisions au réalisé, jour par jour.
- WAPE = Σ|réel − prévu| / Σ réel (indicateur principal, robuste aux jours à faible volume) ;
- MAPE et biais (le biais indique si le modèle sur- ou sous-estime) ;
- le modèle au WAPE le plus faible devient le **champion** de la série.

**Ce que le backtest nous a appris** (versions successives testées pendant le POC) :
| Version | Résultat | Cause |
|---|---|---|
| Holt-Winters sur log(1 + montant) | Biais de −70 à −99 % | Biais de retransformation : exp(moyenne des log) < moyenne, surtout quand il y a beaucoup d'heures à 0 |
| Holt-Winters additif | WAPE d'environ 1 500 % | La saisonnalité apprise pendant la forte activité ne diminue pas quand le volume chute (après la 400ᵉ heure de PaySim) |
| Holt-Winters **multiplicatif** | WAPE médian d'environ 10 % | Le profil horaire est proportionnel au niveau d'activité |
| Naïf saisonnier | WAPE de 3,5 à 7,7 % sur la fenêtre stable du vrai PaySim (champion sur 19 séries sur 20) | Robuste ; les flux journaliers sont stables |
| Backtest sur les jours 28-30 (avant correction) | WAPE de 74 % (naïf), 902 559 % (Holt-Winters) | Le test portait sur des jours « morts » : fenêtre d'analyse restreinte aux jours 6-17 + garde-fou de divergence |

## 2. Simulation Monte-Carlo de la position
Une prévision ponctuelle ne suffit pas : le trésorier doit connaître le **risque**. Pour chaque filiale :
1. on tire au hasard, pour chaque jour futur, une des 7 dernières journées réellement observées (encaissements **et** décaissements du même jour, pour conserver leur corrélation) ;
2. on la met à l'échelle du niveau prévu par le champion ;
3. on cumule les flux nets à partir de la dernière position connue ;
4. on répète 500 fois, puis on lit les quantiles **P5 / P50 / P95** et la **probabilité de passer sous le besoin de liquidité à 30 jours**.

C'est une *simulation historique*, la même logique que la VaR historique utilisée en salle des marchés : elle ne suppose pas de loi normale et respecte les queues de distribution réelles.

## 3. Prévision du change
Les cours de change sont proches d'une **marche aléatoire** : aucun modèle ne bat durablement la prévision « demain = aujourd'hui » (Meese & Rogoff, 1983). On ne cherche donc pas à prédire le cours exact, mais une **fourchette** :
- mouvement brownien géométrique, volatilité estimée sur les 250 dernières cotations ;
- 2 000 trajectoires sur 30 jours → quantiles P5 / P50 / P95 ;
- **contrôle a posteriori** : comme l'export Webstat va jusqu'en septembre 2026, on compare la fourchette prévue au 12/09/2025 (date d'arrêté) aux cours réellement observés ensuite. Résultat : 100 % des 20 jours de cotation dans la fourchette à 90 %, pour les 6 devises. C'est plus que les 90 % attendus : l'intervalle est **prudent** (plutôt large), et les jours successifs sont autocorrélés. Un premier essai depuis le 01/10/2025 donnait 82 % pour le JPY : la fourchette est utile, pas infaillible.
- Le RUB est exclu automatiquement (dernière cotation le 01/03/2022).
- La DKK, ancrée à l'euro (MCE II), a une fourchette très étroite (±0,1 %) : couvrir une position en couronnes danoises n'a presque aucun intérêt.

## 4. Stress tests
| Scénario | Retraits | Change | Taux | Sorties ×  | Référence historique |
|---|---|---|---|---|---|
| Central | 0 | 0 | 0 | 1,0 | Tendance observée |
| Retraits modérés | 5 % | — | +50 pb | 1,5 | Northern Rock 2007 |
| Panique sévère | 20 % | — | +150 pb | 2,5 | SVB, mars 2023 |
| Dépréciation du dollar | — | USD −10 %, CAD −8 % | — | 1,0 | 2017, S1 2025 |
| Couronnes nordiques | — | SEK, NOK −12 % | +50 pb | 1,2 | 2020-2023 |
| Dévaluation du CFA | 3 % | XOF/XAF −50 % | +200 pb | 1,3 | 12 janvier 1994 |
| Crise combinée | 10 % | tous les chocs | +200 pb | 2,0 | Reverse stress test |

Sortie : position stressée, horizon de survie (jours), besoin et coût de refinancement, statut (Résilient ≥ 30 j / Vigilance 7-30 j / Critique < 7 j).
Le simulateur Power BI rejoue le même calcul avec des curseurs libres (paramètres What-if).

## 5. Limites
- 12 jours d'historique stable : pas de saisonnalité hebdomadaire ou mensuelle exploitable.
- À la maille journalière, la prévision ne fait pas mieux qu'une moyenne simple (flux stables) : sa valeur est dans l'anticipation de la date de franchissement du seuil et dans la mesure de l'incertitude (voir docs/06 § 5).
- Encaissements et décaissements sont simulés à partir des mêmes journées tirées : la corrélation est respectée, mais pas d'éventuelles tendances futures.
- Pistes d'industrialisation : Prophet ou SARIMAX avec calendrier (jours fériés par pays, paie, fins de mois), modèles hiérarchiques (filiale → groupe), réentraînement quotidien et suivi de la dérive (WAPE glissant).
