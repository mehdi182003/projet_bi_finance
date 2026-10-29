# 06 — Profil des données réelles et choix des KPI

> Revue réalisée sur le **vrai** PaySim (6 362 620 transactions, Kaggle `ealaxi/paysim1`) et les cours BCE réels (Webstat), avec trois skills :
> `data:explore-data` (profilage), `data-pipeline-builder` (revue dbt), `data:statistical-analysis` (évaluation des KPI).
> Méthode suivie : **on profile la donnée avant de choisir les indicateurs**, puis on garde un KPI seulement s'il varie, s'il est mesuré (et pas seulement supposé), s'il résiste aux artefacts du jeu de données et s'il éclaire une décision.

## 1. Ce que montre le profilage de PaySim

| Constat | Mesure | Conséquence |
|---|---|---|
| Aucune valeur manquante, identifiants bien formés | 0 NULL sur 11 colonnes | Pas de nettoyage lourd nécessaire |
| **Activité normale seulement les jours 1-2 et 6-17** | Jours 3-5 et 18-31 : 1 à 6 % du volume médian | Fenêtre d'analyse restreinte aux **jours 6 à 17** (RG-QUA-02) : 12 jours continus, 77 % des opérations, 80 % des montants |
| La fraude est injectée à rythme constant | ~11 fraudes par heure, de jour comme de nuit ; « taux de fraude » de 100 % le jour 31 | Un taux de fraude dans le temps est un **artefact** : on ne le pilote pas |
| **Soldes incohérents** | Montant > solde dans 88,5 % des retraits et 95,2 % des virements ; solde final ramené à 0 | L'encours de dépôts reconstitué est un ordre de grandeur, contrôlé par un test de vraisemblance (décaissements = 0,78 % des dépôts par jour : plausible) |
| 99,85 % des clients n'apparaissent qu'une fois | 6 344 009 clients sur 6 353 307 (99,7 % des transactions) | Aucun KPI client (fidélité, comportement) n'est possible |
| Montants très asymétriques | Moyenne 180 k, médiane 75 k ; 2 % des transactions (≥ 1 M PaySim) = 29 % des montants | Suivre la **concentration** plutôt que des moyennes |
| Plafond de 10 M sur les virements | 3 207 opérations exactement à 10 000 000 | Découpage des gros virements par le simulateur, sans impact sur les totaux |
| Profil horaire très marqué | Quasi rien entre 2 h et 7 h, pic à 18 h | Base de la prévision intrajournalière |
| **Flux net structurellement négatif** | Les 12 jours sont négatifs pour les 10 filiales ; le solde net vaut −38 % des décaissements | PaySim n'a pas de flux interbancaires entrants (salaires, virements reçus) : la réserve se consomme d'environ 2 % par jour. C'est un biais du proxy, à assumer en soutenance |

## 2. Revue du pipeline dbt (skill `data-pipeline-builder`)

| Constat du script | Vérification | Action |
|---|---|---|
| 21 × « model has no tests » | **Faux positif** : le script coupe le bloc du modèle au premier `- name:` de colonne et ne voit pas les tests déclarés par colonne | Aucune (78 tests exécutés par `dbt build`) |
| `SELECT *` hors staging (6) | 2 réels (`dim_scenario_stress`, `fct_taux_change`) ; les 4 autres sont des unions de CTE aux colonnes déjà listées | Colonnes explicites sur les 2 modèles |
| Pas de contrôle de fraîcheur | Réel pour les cours BCE (publiés chaque jour ouvré) | `freshness` sur `raw.bce_taux_change` (alerte au-delà de 10 jours), lancé par `pipeline.py` |

Problèmes de fond trouvés en plus par la revue manuelle, plus graves que ceux du script :
1. Le backtest portait sur les jours « morts » (28-30) : erreur WAPE de 74 % pour le modèle naïf et de 902 559 % pour Holt-Winters. **Corrigé** par la fenêtre d'analyse : WAPE de 3,5 à 7,7 %, biais de +2,5 %.
2. Le stress test calculait ses moyennes sur la période morte (600 à 1 800 jours de survie). **Corrigé** : 30 à 63 jours dans le scénario central.
3. Holt-Winters diverge sur 4 séries sur 20. **Garde-fou ajouté** : le modèle est écarté (WAPE NULL) au lieu d'afficher une erreur absurde.
4. Nouveaux contrôles : `mart_qualite_donnees` (jours retenus ou exclus et pourquoi), alerte de régime d'activité, alerte de vraisemblance de l'encours.

## 3. Évaluation des KPI (skill `data:statistical-analysis`)

Période : 01/09 → 12/09/2025 (jours 6 à 17 de PaySim), 10 filiales, soit 120 observations filiale × jour.

| KPI | Ce que disent les données | Verdict |
|---|---|---|
| Solde net quotidien | Toujours négatif ; dispersion faible (coefficient de variation 13 à 23 %) ; FR −35 M€/j, US −19 M€/j | ✅ **Gardé** (cœur du pilotage) |
| Position de trésorerie | Baisse de 6,1 à 4,8 Md€ en 12 jours | ✅ Gardé + **nouveau : consommation quotidienne** (1,6 à 3,3 %/j selon la filiale) |
| Ratio de couverture liquidité **v1** (tendance des flux ajoutée au besoin) | Entre 47 et 100 %, **jamais au-dessus de 100 %** ; liquidité excédentaire = 0 sur 120/120 jours ; gain de placement toujours nul | ❌ **Remplacé** : définition non standard (double comptage) et KPI figé |
| Ratio de couverture liquidité **v2** (position / 10 % des dépôts, Bâle III) | Entre 88 et 197 % ; varie d'une filiale et d'un jour à l'autre | ✅ **Nouveau standard** |
| **Jours avant passage sous 100 %** (nouveau) | US, CA : déjà dessous ; FR, Benelux, nordiques : 6 à 8 jours ; CFA : 25-26 jours | ✅ **KPI phare** : il dit *quand* se refinancer |
| Probabilité de passer sous le seuil (prévision) | v1 : 100 % partout (inutile). v2 : monte à J+7 (Benelux 95 %, Danemark 86 %, Suède 80 %) | ✅ Gardé (redevenu informatif) |
| Effet de change réalisé | Sur 12 jours : au plus 1,3 % de la position (NOK) ; 0,03 % pour l'USD | ⚠️ **Secondaire** : explicatif, pas de pilotage à court terme |
| VaR 95 % 10 j | 1,4 à 2,4 % de l'exposition pour les devises flottantes ; 0,05 % pour la DKK ; 0 pour le CFA | ✅ Gardé, avec la limite : **la VaR ne voit pas le risque de dévaluation du CFA** (traité par stress test) |
| Coût de couverture | Inutile seul : un coût n'a de sens que rapporté au risque couvert | ✅ Transformé en **rapport coût / risque + recommandation** (nouveau) |
| Horizon de survie sous stress | Scénario central 30-63 j ; retraits modérés 6-18 j ; panique sévère 0 j | ✅ Gardé |
| Taux de netting intragroupe | 13,6 %, entièrement déterminé par l'hypothèse « 85 % de virements domestiques » | ❌ **Retiré du cockpit** : paramètre de simulation, pas une mesure |
| Taux de fraude dans le temps | Artefact (fraude à rythme constant) | ❌ Retiré du suivi temporel ; remplacé par le **taux de détection** (page Qualité / Risques) |
| Pic de liquidité intrajournalier (envisagé) | Pic / solde du jour = 1,00 en médiane ; pic à 23 h dans 76 % des cas | ❌ **Testé et écarté** : les flux nets sont négatifs presque toutes les heures, donc le pic est toujours en fin de journée |
| Part des gros décaissements (nouveau) | 0,4 % des décaissements ayant un impact de trésorerie (≥ 10 k€) = 10,3 % des montants décaissés. Les très gros tickets de PaySim sont surtout des virements internes, neutralisés | ✅ Ajouté (secondaire) : justifie une pré-notification des gros retraits |
| « Coussin libéré grâce à la prévision » (envisagé) | Calcul erroné repéré pendant la revue ; une fois corrigé : à la maille journalière, la prévision ne fait pas mieux qu'une moyenne simple (flux stables) | ❌ **Non retenu** : la valeur du prédictif est ailleurs (voir § 4) |

### Décision de couverture par devise (date d'arrêté)
| Devise | Exposition | Volatilité / an | Coût de couverture / an | Coût / risque | Recommandation |
|---|---|---|---|---|---|
| USD | 557 M€ | 7,3 % | 2,50 % | 0,34 | Couverture partielle à arbitrer |
| CAD | 351 M€ | 4,3 % | 0,75 % | 0,18 | **Couverture prioritaire** |
| SEK | 284 M€ | 4,6 % | 0,00 % | 0,00 | **Couverture prioritaire** (coût nul) |
| NOK | 194 M€ | 5,9 % | 2,25 % | 0,38 | Couverture partielle à arbitrer |
| DKK | 185 M€ | 0,2 % | −0,40 % | — | Couverture inutile (ancrée à l'euro) |
| XOF / XAF | 1 233 M€ | 0 % | — | — | Pas de couverture de marché : stress test « dévaluation » |

## 4. Cockpit retenu

**Niveau 1 : cockpit de la Direction Financière**
1. Position de trésorerie et **consommation quotidienne**.
2. **Ratio de liquidité (Bâle III simplifié)** et **jours avant passage sous 100 %**.
3. Prévision du solde à J+7 avec intervalle P5-P95 et précision du modèle (WAPE).
4. Exposition au change (58 % de la position du groupe hors EUR, dont 26 points en franc CFA) et VaR 95 % 10 j.
5. Horizon de survie par scénario de stress.
6. Résultat de trésorerie : gain de placement des excédents − coût de refinancement des déficits.

**Niveau 2 : analyse**
Rapport coût / risque de la couverture et recommandation par devise · effet de change réalisé · part des gros décaissements · probabilité de passer sous le seuil · qualité des données et fraude.

## 5. Où l'analyse prédictive crée vraiment de la valeur (réponse argumentée)
- **Anticiper le moment, pas le montant du jour.** Les flux quotidiens sont stables : une moyenne suffit à prévoir le solde du lendemain. Ce que la prévision apporte, c'est **la date** à laquelle chaque filiale passera sous son seuil (6 à 8 jours pour la plupart des filiales européennes). On peut alors se refinancer de façon programmée plutôt qu'en urgence : environ 0,25 point d'écart (taux des opérations principales vs facilité de prêt marginal BCE) et surtout, aucun ratio réglementaire franchi.
- **Placer les excédents qui dorment.** Les filiales CFA ont un ratio supérieur à 170 % et un excédent d'environ 440 M€ (17 M€ par an placés aux taux BCEAO / BEAC). Ces excédents restent cependant **bloqués localement** par le contrôle des changes : la décision porte sur un placement local, pas sur un rapatriement.
- **Couvrir intelligemment le change.** Tout couvrir coûterait environ 20 M€ par an. En ciblant les devises au rapport coût / risque faible (CAD, SEK) et en ne couvrant pas la DKK, on réduit fortement ce coût pour un risque comparable.
- **Simuler les crises.** Avec un horizon de survie de 0 jour dans le scénario « panique sévère », le stress test justifie des lignes de liquidité de secours.

## 6. Validation avant présentation (skill `data:validate-data`)

**Verdict : présentable, avec les réserves ci-dessous.**

Contrôles réalisés :
| Contrôle | Résultat |
|---|---|
| Recalcul indépendant du ratio de liquidité et des jours avant 100 % (France, 12/09) | ✅ Identique (120,03 % ; 7,37 jours) |
| Grain des tables (pas d'explosion de jointure) | ✅ 120 lignes filiale × jour, 84 devise × jour, 70 scénario × filiale, 31 jours de qualité |
| Sous-totaux : flux horaires = flux quotidiens ; position du stress test = position de liquidité | ✅ Égalités exactes |
| Fenêtre d'analyse | ✅ 4 918 825 transactions, du 01/09 0 h au 12/09 23 h |
| VaR USD recalculée à la main (1,645 × 7,3 %/√252 × 557 M€ × √10) | ✅ 13,3 M€ |
| Gain de placement CFA recalculé (197 M€ × 4,50 % ; 245 M€ × 3,25 %) | ✅ 8,9 M€ et 8,0 M€ |
| Cohérence prévision / indicateur déterministe | ✅ Benelux : 6,2 jours avant 100 % ↔ probabilité de 34 % à J+6 puis 95 % à J+7 |
| WAPE moyen vs WAPE pondéré par les montants | ✅ 4,67 % vs 4,69 % : pas de biais de « moyenne de moyennes » |
| Chiffres cités dans ce document | ⚠️ 2 erreurs trouvées et corrigées (part de clients uniques ; part des gros décaissements, calculée sur une autre population que le KPI du cockpit) |

Réserves à dire au jury :
1. **Biais d'anticipation dans la fenêtre** : elle a été choisie en regardant tout le mois, y compris les jours qui suivent. C'est légitime pour écarter un artefact de simulation, mais un trésorier réel ne connaîtrait pas l'avenir.
2. **Encours « initial »** : il somme les soldes de clients vus pour la première fois jusqu'au 12/09, donc il contient de l'information postérieure au 01/09.
3. **Petit échantillon de backtest** : 3 jours × 20 séries. La conclusion « le naïf saisonnier gagne » vaut pour des flux stables sur 12 jours, pas en général.
4. **Fourchettes de change plutôt larges** : 100 % des cours réalisés y tombent, alors qu'on en attendrait environ 90 %. Les 120 points (20 jours × 6 devises) sont autocorrélés : l'intervalle est prudent, pas « parfait ».
5. **Gains présentés comme des majorants** : placement au taux directeur local (une banque place un peu en dessous) ; économie d'anticipation calculée en supposant qu'à défaut on emprunterait à la facilité de prêt marginal.
6. **La recommandation SEK repose sur un taux Riksbank marqué « à vérifier »** dans le référentiel.

## 7. Limites assumées
- 12 jours d'historique : pas de saisonnalité hebdomadaire ou mensuelle mesurable ; échantillon de backtest réduit (3 jours × 20 séries).
- Les **niveaux** des ratios dépendent d'hypothèses (taux de réserve de 12 % en Amérique du Nord contre 15 % en Europe, d'où US et CA sous 100 %). Les **pentes** (consommation, jours avant seuil), elles, viennent des données.
- La signature de fraude « vide le compte » (rappel 97,6 %, précision 100 %) est propre au simulateur : elle ne se transposerait pas telle quelle à une vraie banque.
