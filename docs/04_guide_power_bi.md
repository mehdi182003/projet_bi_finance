# 04 — Cockpit Power BI

## Option A (recommandée) : ouvrir le projet déjà construit

Le rapport complet est fourni au format **projet Power BI (`.pbip`)** dans `powerbi/Cresus/` :
modèle de données (26 tables, 26 relations, 73 mesures DAX, paramètres What-if) et 6 pages de visuels, sur 3 ans (2023-2025).

1. Lancer le pipeline (`python pipeline.py`) pour remplir le schéma `marts` de PostgreSQL.
2. Ouvrir **Power BI Desktop** (version de mi-2025 ou plus récente) → *Fichier → Ouvrir* → `powerbi/Cresus/Cresus.pbip`.
   - Si Power BI refuse le fichier (version plus ancienne) : *Fichier → Options → Fonctionnalités en préversion* → cocher « Option d'enregistrement de projet Power BI (.pbip) », « Stocker le modèle sémantique au format TMDL » et « Stocker les rapports au format PBIR », puis redémarrer.
3. *Accueil → Actualiser*. Aux identifiants demandés pour PostgreSQL, choisir l'onglet **Base de données** : `postgres` / `postgres`. En cas d'erreur de chiffrement, décocher « Chiffrer les connexions » (voir § 1).
4. Si la base n'est pas sur `localhost:5432` / `cresus` : *Transformer les données → Modifier les paramètres* (`ServeurPostgres`, `BasePostgres`).
5. Pour garder une copie en un seul fichier : *Fichier → Enregistrer sous → .pbix*.

Comment le projet a été produit et vérifié (à mentionner en soutenance) : `powerbi/generer_pbip.py` lit la structure réelle des tables dans PostgreSQL, construit le modèle, puis le fait **valider et convertir au format TMDL par la bibliothèque officielle Microsoft** (Analysis Services TOM, outil `powerbi/outils/TomTool`). Les 69 fichiers du rapport sont validés contre les **schémas JSON publiés par Microsoft**. Un contrôle croisé vérifie enfin que chaque champ des visuels et chaque référence DAX existent dans le modèle. Limite : Power BI Desktop ne tournant que sous Windows, le projet n'a pas pu être ouvert dans Power BI pendant sa génération ; s'il signale un problème à l'ouverture, l'option B permet de reconstruire la page concernée à la main.

Les sections ci-dessous décrivent le contenu du rapport. Elles servent aussi de **guide pour le reconstruire à la main (option B)**.

## 1. Connexion à PostgreSQL
1. Lancer le pipeline (`python pipeline.py`) : le schéma `marts` doit être rempli.
2. Power BI : **Accueil → Obtenir des données → Base de données PostgreSQL**.
   - Serveur : `localhost:5432` · Base : `cresus` · Mode : **Importer**.
   - Identifiants : onglet **Base de données**, `postgres` / `postgres`.
   - Si une erreur SSL apparaît : *Fichier → Options → Sécurité des sources de données → Modifier les autorisations* → décocher « Chiffrer les connexions ».
   - Si le connecteur réclame Npgsql (anciennes versions de Power BI) : installer Npgsql 4.0.x en cochant « Npgsql GAC Installation ».
3. Cocher les tables du schéma **marts** :
   `dim_date, dim_filiale, dim_devise, dim_type_transaction, dim_scenario_stress, fct_flux_tresorerie_horaire, fct_position_tresorerie_quotidienne, fct_taux_change, mart_exposition_change, mart_liquidite_placement, mart_stress_test, mart_prevision_tresorerie, mart_prevision_change, mart_qualite_prevision, mart_backtest_journalier, mart_qualite_donnees, mart_qualite_ancrage, mart_reserve_optimale, mart_controle_a_posteriori` (`mart_qualite_donnees` n'a pas de relation : c'est une table autonome par jour de simulation PaySim).
4. Dans Power Query, renommer les tables pour enlever le préfixe `marts ` (sinon adapter les noms dans les mesures DAX).

## 2. Modèle (vue Modèle)
Power BI détecte souvent les relations tout seul ; vérifier et compléter (cardinalité 1 → *, filtrage simple) :

| De (côté 1) | Vers (côté *) |
|---|---|
| `dim_date[date_jour]` | `fct_flux_tresorerie_horaire[date_operation]`, `fct_position_tresorerie_quotidienne[date_position]`, `fct_taux_change[date_cours]`, `mart_exposition_change[date_position]`, `mart_liquidite_placement[date_position]`, `mart_prevision_tresorerie[date_jour]`, `mart_prevision_change[date_jour]` |
| `dim_filiale[code_filiale]` | `fct_flux…`, `fct_position…`, `mart_liquidite_placement`, `mart_stress_test`, `mart_prevision_tresorerie`, `mart_qualite_prevision`, `mart_backtest_journalier` |
| `dim_devise[code_devise]` | `dim_filiale`, `fct_taux_change`, `mart_exposition_change`, `mart_prevision_change` |
| `dim_type_transaction[code_type]` | `fct_flux_tresorerie_horaire` |
| `dim_scenario_stress[code_scenario]` | `mart_stress_test` |

Ensuite :
- `dim_date` → **Marquer comme table de dates** (colonne `date_jour`). Trier `libelle_mois` par `mois` et `libelle_jour` par `jour_semaine`.
- `dim_filiale[pays]` → catégorie de données **Pays** (pour la carte).
- Masquer les colonnes techniques (`id_*`, codes en double côté faits).

## 3. Mesures
1. **Accueil → Entrer des données** → table vide nommée `_Mesures`.
2. Créer les 4 paramètres What-if (**Modélisation → Nouveau paramètre → Plage numérique**) :
   `Choc retraits %` (0 → 30, pas 1) · `Choc change %` (−50 → 20, pas 1) · `Multiplicateur sorties` (1 → 3, pas 0,1) · `Choc taux (pb)` (0 → 300, pas 25).
3. Créer la table `Devises choquées` (**Modélisation → Nouvelle table**, formule fournie dans le fichier DAX).
4. Copier les mesures de `powerbi/mesures_dax.dax` une par une (**Nouvelle mesure**) dans `_Mesures`.
5. Formats : montants en `# ##0 €` (ou en M€), ratios en pourcentage.
6. **Affichage → Thèmes → Parcourir** → `powerbi/theme_cresus.json`.

## 4. Pages du rapport

### Page 1 — Cockpit Direction Financière
- Segments : région, filiale, année.
- Cartes : *Position de trésorerie*, *Ratio de couverture liquidité %*, **Jours sous 100 %**, *Encours de dépôts*, *Refinancement levé*, *Excédent placé*, *VaR change 95 % 10 j*, *Effet de change cumulé*.
- Courbe : position par filiale sur 3 ans (creux de début de mois, remontée avec les salaires).
- Tableau par filiale : ratio, jours sous 100 %, refinancement, placements.
- Ne **pas** mettre sur cette page : *Taux de fraude* (artefact du simulateur), voir docs/06.

### Page 2 — Flux de trésorerie
- Encaissements / décaissements **par mois** (`dim_date[annee_mois]`).
- **Opérations de trésorerie de fin de mois** : *Refinancement levé* vs *Excédent placé* par mois. On y voit 2023 (refinancement pendant la fuite des dépôts) et 2025 (placements).
- Décaissements par type d'opération ; profil horaire du solde net ; carte *Part des gros décaissements %* (~14 %).

### Page 3 — Prévisions (analyse prédictive)
- Cartes : *Probabilité de passer sous 100 %* (mois prévu), *WAPE du champion*, et le **contrôle sur données réelles de janvier 2026** (*Couverture de l'intervalle à 90 %*, *Erreur médiane*).
- Courbe : position réalisée puis prévue (P5 / P50 / P95).
- Tableau de backtest (3 origines, 3 modèles, champion).
- Tableau **réserve requise (P99) vs réserve actuelle** par filiale, avec le diagnostic.
- Tableau du **contrôle a posteriori** : dépôts réels au 31/01/2026 vs prévus.

### Page 4 — Change & couverture
- Courbe `mart_prevision_change` : *Taux de change prévu P50* + barres d'erreur P05/P95, avec *Taux de change réalisé* en superposition (contrôle a posteriori), segment = devise.
- Cartes : *Exposition au change*, *Part de la position en devises*, *VaR 95 % 10 j*, *Coût annuel de couverture*.
- Barres : *Effet de change cumulé* par devise. Sur 2023-2025, la remontée de l'euro coûte −58 M€ sur l'USD et −46 M€ sur la NOK.
- Tableau de décision : devise, exposition, volatilité, *Rapport coût / risque de la couverture*, *Recommandation de couverture*.
- Tableau `fct_taux_change` : volatilité annualisée par devise ; mettre en évidence le RUB (`est_rupture_serie`).

### Page 5 — Simulateur de stress (What-if)
- Les 4 curseurs + segment `Devises choquées[Cible]`.
- Cartes dynamiques : *Position stressée*, *Horizon de survie (jours)*, *Besoin de refinancement stressé*, *Coût du refinancement stressé*.
- Tableau par filiale avec *Statut de résilience* coloré via *Couleur statut* (Format → Couleur d'arrière-plan → Valeur du champ).
- Matrice des scénarios précalculés : lignes = `dim_scenario_stress[libelle_scenario]`, colonnes = filiale, valeur = `mart_stress_test[horizon_survie_jours]`, couleur selon `statut_resilience`. Info-bulle : `reference_historique`.

### Page 6 — Qualité et fiabilité des données
- Cartes : *Lignes brutes reçues*, *Taux de rejet %*, *Rejets inattendus*, *Écart max à l'encours réel %*.
- Barres **défauts détectés et corrigés par l'ETL, par système source** (doublons, libellés, devises, annulations / tests / extournes) et tableau par filiale (`mart_qualite_sources`).
- Courbe **encours réel publié par la banque centrale vs encours reconstitué** (segment filiale) : les deux courbes se superposent. C'est la preuve visuelle de l'ancrage sur le réel.
- Carte *Écart max à l'encours réel %* (≈ 0).
- Volume PaySim par jour (retenu ou exclu) et fraudes constantes : ils montrent **pourquoi** PaySim ne sert plus que de texture.
- Cartes de détection de fraude (0,2 % pour le système PaySim, 97,6 % pour la règle « vide le compte »).

## 5. Conseils pour la soutenance
- Démonstration en direct : régler *Choc retraits* sur 20 % (scénario SVB) et montrer quelles filiales passent en « Critique ».
- Montrer la page Qualité : encours réel vs reconstitué, puis la page Prévisions : la fourchette contenait le réel de janvier 2026 pour 7 filiales sur 9.
- Montrer le cône de prévision et le contrôle a posteriori du change : c'est la preuve concrète que le prédictif fonctionne.
- Afficher le lignage `dbt docs` pour démontrer la traçabilité (exigence Bâle III / BCBS 239).
