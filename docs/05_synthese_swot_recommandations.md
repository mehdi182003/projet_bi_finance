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
| Placer la liquidité dormante : chaque million d'euros placé au taux de la facilité de dépôt de la BCE (2 % fin 2025) rapporte environ 20 000 € par an | Rupture de séries (RUB non coté depuis mars 2022) qui peut fausser ou bloquer un modèle |
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

| Levier | Ce que montrent les 3 ans de données (2023-2025) | Mesure Power BI |
|---|---|---|
| **Moduler la réserve selon le mois** | Janvier concentre 34 % des jours sous 100 % (décollecte réelle de début d'année). La prévision demande ~18 % de réserve en France pour janvier 2026, contre 15 % aujourd'hui : il faut **pré-financer en décembre** plutôt que subir un ratio sous 100 % | *Réserve requise P99 %*, *Jours sous 100 %* |
| **Placer les excédents structurels** | Côte d'Ivoire, Cameroun et Norvège sont sur-dotés (~90 M€ libérables), placés aux taux réels BCEAO / BEAC / Norges Bank (~3,5 M€ par an). En zone CFA, le placement reste local (contrôle des changes) | *Liquidité libérable*, *Gain annuel* |
| **Anticiper le refinancement** | 4,0 Md€ de refinancement net en 2023 (fuite des dépôts à vue pendant la hausse des taux BCE) : un besoin prévisible qui se finance de façon programmée (MRO) plutôt qu'en urgence (facilité marginale, +25 pb) | *Refinancement levé*, *Économie annuelle grâce à l'anticipation* |
| **Couvrir le change avec discernement** | −58 M€ d'effet de change sur l'USD et −46 M€ sur la NOK en 3 ans. À fin 2025 : couvrir en priorité le CAD (coût faible) et la SEK (la couverture rapporte), arbitrer USD et NOK (coût élevé), ne pas couvrir la DKK (ancrée à l'euro), piloter le CFA par stress test | *Rapport coût / risque*, *Recommandation*, *VaR 95 % 10 j*, *Effet de change cumulé* |
| **Mesurer la résilience** | Retraits modérés (type Northern Rock) : 22 à 51 jours de survie en Europe et en Amérique du Nord ; panique type SVB : 0 jour, ce qui justifie des lignes de liquidité de secours | *Horizon de survie*, statut |
| **Fiabiliser la donnée** | Les dépôts reconstitués égalent les dépôts publiés par les banques centrales (481 dates contrôlées) ; la prévision a été confrontée aux dépôts réels de janvier 2026 (7 filiales sur 9 dans la fourchette) | Page *Qualité des données* |

Les montants dépendent des parts de marché supposées : il faut **présenter les mécanismes et les ordres de grandeur**. Les dynamiques (saisonnalité, cycle de taux, effet de change), elles, sont réelles.

## 4. Réponse à la problématique (synthèse)
L'analyse prédictive transforme la trésorerie de centre de coûts en centre de profit, à trois conditions. **Prévoir** les flux par filiale et par devise permet de réduire les coussins de liquidité de précaution et de placer l'excédent. **Simuler** (Monte-Carlo, stress tests) chiffre le risque associé à chaque décision : on sait avec quelle probabilité une filiale passera sous son besoin de liquidité, et combien de jours elle tient en cas de crise. **Fiabiliser** la donnée (sources officielles, règles de gestion testées) rend ces chiffres opposables à la Direction Financière et au superviseur. Le POC montre que c'est faisable à faible coût avec des briques open source et Power BI. Il montre aussi les limites à maîtriser : qualité et profondeur de l'historique, ruptures de séries, et nécessité de toujours comparer un modèle à une référence simple (backtest).

## 5. Corrections suggérées pour la fiche d'expertise
- Côte d'Ivoire = **XOF** (BCEAO, UEMOA) ; Cameroun = **XAF** (BEAC, CEMAC).
- Étape 5 : remplacer « Tableau Software » par **Power BI** (outil retenu) ; mentionner dbt pour la modélisation en étoile et les tests.
- Ajouter les filiales d'Europe du Nord (SEK, DKK, NOK) au périmètre multidevise.
- Coquilles : « notre groupe **va** conseiller », « a besoin d'**améliorer** sa trésorerie », « la réalisation du projet se **passera** ».
- Source de change : préciser « Banque de France Webstat — cours de référence BCE (série EXR) ».
