# 05 — SWOT, impacts et réponse à la problématique

## 1. Matrice SWOT (analyse prédictive appliquée à la trésorerie de ZF Banque)

| **Forces** | **Faiblesses** |
|---|---|
| Sources externes officielles et gratuites (BCE via Webstat, banques centrales) | Hétérogénéité des SI des 10 filiales (3 continents, 8 devises, 3 régimes de change) |
| Stack open source peu coûteuse (PostgreSQL, dbt, Python) + Power BI déjà présent dans l'écosystème Microsoft | Historique interne court ou hétérogène selon les filiales |
| Règles de gestion versionnées et testées : traçabilité de bout en bout | Compétences data science encore rares à la Trésorerie |
| Simulation en temps réel (What-if) au lieu de tableurs figés | Modèles sensibles aux ruptures de régime (constaté sur PaySim) |

| **Opportunités** | **Menaces** |
|---|---|
| Placer la liquidité dormante : chaque million d'euros placé au taux de la facilité de dépôt de la BCE (2 %) rapporte environ 20 000 € par an | Rupture de séries (RUB non coté depuis mars 2022) qui peut fausser ou bloquer un modèle |
| Réduire le coût de couverture : couvrir seulement l'exposition nette, après netting intragroupe | Réglementation (Bâle III/LCR, BCBS 239, RGPD, contrôle des changes en zone CFA) |
| Netting et cash pooling intragroupe : moins d'achats de devises | Risque de modèle : confiance excessive dans un chiffre unique → toujours afficher l'intervalle |
| Stress tests réguliers attendus par le superviseur (ACPR / BCE) | Risque de dévaluation (franc CFA) invisible dans la volatilité historique |

## 2. Impacts

**Technologiques**
- Création d'un entrepôt de données central (schémas raw → marts) et de flux quotidiens automatiques (cours BCE, positions des filiales).
- Gouvernance du code : Git, revues, tests automatiques (dbt), documentation générée.
- Industrialisation : ordonnanceur (Airflow / dbt Cloud), supervision, montée en charge (Snowflake / BigQuery si besoin).
- Sécurité : gestion des accès par filiale (Row-Level Security dans Power BI), chiffrement, journalisation.

**Organisationnels**
- Nouveaux rôles : *data owner* par filiale, *data steward* Trésorerie, analyste data/BI.
- Nouveau processus : comité de trésorerie hebdomadaire s'appuyant sur le cockpit (prévision J+7, stress tests).
- Conduite du changement : former les trésoriers à lire des probabilités et des intervalles de confiance.
- Validation des modèles par une équipe indépendante (exigence de gestion du risque de modèle).

## 3. Comment l'analyse prédictive génère des gains (leviers chiffrables dans le cockpit)

| Levier | Mécanisme | Mesure Power BI |
|---|---|---|
| Placement de la liquidité dormante | La prévision réduit le coussin de précaution nécessaire ; l'excédent est placé | *Gain annuel de placement* |
| Moindre coût de refinancement | On anticipe les besoins au lieu d'emprunter en urgence (plus cher) | *Coût annuel de refinancement* |
| Couverture de change optimisée | On couvre en priorité les devises au rapport coût / risque faible (CAD, SEK), pas la DKK ancrée à l'euro ; le CFA se pilote par stress test | *Rapport coût / risque*, *Recommandation de couverture*, *VaR 95 % 10 j* |
| Anticipation du refinancement | On sait **quand** chaque filiale passera sous 100 % (6 à 8 jours pour l'Europe) et on emprunte de façon programmée plutôt qu'en urgence | *Jours avant passage sous 100 %*, *Économie annuelle grâce à l'anticipation* |
| Netting intragroupe | On compense les flux entre filiales avant de passer par le marché (valeur à mesurer sur données réelles : dans le POC, elle découle d'une hypothèse) | — |
| Résilience et conformité | Stress tests fondés sur des données réelles, horizon de survie connu | *Horizon de survie*, statut |
| Fraude | Le dispositif actuel (`isFlaggedFraud`) ne détecte que 0,2 % des fraudes ; une règle simple en détecte 97,6 % sur PaySim (signature propre au simulateur) | *Taux de détection actuel %* |

Les montants du POC dépendent des hypothèses (valeur d'une unité PaySim, taux de réserve) : il faut **présenter les ordres de grandeur et les mécanismes**, pas les montants comme des prévisions réelles de ZF Banque.

## 4. Réponse à la problématique (synthèse)
L'analyse prédictive transforme la trésorerie de centre de coûts en centre de profit, à trois conditions. **Prévoir** les flux par filiale et par devise permet de réduire les coussins de liquidité de précaution et de placer l'excédent. **Simuler** (Monte-Carlo, stress tests) chiffre le risque associé à chaque décision : on sait avec quelle probabilité une filiale passera sous son besoin de liquidité, et combien de jours elle tient en cas de crise. **Fiabiliser** la donnée (sources officielles, règles de gestion testées) rend ces chiffres opposables à la Direction Financière et au superviseur. Le POC montre que c'est faisable à faible coût avec des briques open source et Power BI. Il montre aussi les limites à maîtriser : qualité et profondeur de l'historique, ruptures de séries, et nécessité de toujours comparer un modèle à une référence simple (backtest).

## 5. Corrections suggérées pour la fiche d'expertise
- Côte d'Ivoire = **XOF** (BCEAO, UEMOA) ; Cameroun = **XAF** (BEAC, CEMAC).
- Étape 5 : remplacer « Tableau Software » par **Power BI** (outil retenu) ; mentionner dbt pour la modélisation en étoile et les tests.
- Ajouter les filiales d'Europe du Nord (SEK, DKK, NOK) au périmètre multidevise.
- Coquilles : « notre groupe **va** conseiller », « a besoin d'**améliorer** sa trésorerie », « la réalisation du projet se **passera** ».
- Source de change : préciser « Banque de France Webstat — cours de référence BCE (série EXR) ».
