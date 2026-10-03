# 04 — Guide de construction du cockpit Power BI

> Le fichier `.pbix` se construit dans Power BI Desktop (Windows) en suivant ce guide (environ 1 h à 1 h 30). Toutes les mesures sont prêtes dans `powerbi/mesures_dax.dax`.

## 1. Connexion à PostgreSQL
1. Lancer le pipeline (`python pipeline.py`) : le schéma `marts` doit être rempli.
2. Power BI : **Accueil → Obtenir des données → Base de données PostgreSQL**.
   - Serveur : `localhost:5432` · Base : `cresus` · Mode : **Importer**.
   - Identifiants : onglet **Base de données**, `postgres` / `postgres`.
   - Si une erreur SSL apparaît : *Fichier → Options → Sécurité des sources de données → Modifier les autorisations* → décocher « Chiffrer les connexions ».
   - Si le connecteur réclame Npgsql (anciennes versions de Power BI) : installer Npgsql 4.0.x en cochant « Npgsql GAC Installation ».
3. Cocher les tables du schéma **marts** :
   `dim_date, dim_filiale, dim_devise, dim_type_transaction, dim_scenario_stress, fct_flux_tresorerie_horaire, fct_position_tresorerie_quotidienne, fct_taux_change, mart_exposition_change, mart_liquidite_placement, mart_stress_test, mart_prevision_tresorerie, mart_prevision_change, mart_qualite_prevision, mart_backtest_journalier`.
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
- Segments : période (`dim_date`), région, filiale.
- Cartes : *Position de trésorerie*, *Variation de position %*, *Ratio de couverture liquidité %*, *Liquidité excédentaire*, *Gain annuel de placement*, *Coût annuel de refinancement*, *VaR change 95 % 10 j*, *Résultat net de trésorerie annuel*.
- Courbe : position (`fct_position…[position_cloture_eur]`) par date, légende = filiale.
- Carte géographique : `dim_filiale[pays]`, taille = *Position de trésorerie*.
- Tableau par filiale : position, ratio de couverture (mise en forme conditionnelle : vert ≥ 100 %, rouge < 100 %), excédent, refinancement.

### Page 2 — Flux de trésorerie
- Histogramme groupé : *Encaissements* / *Décaissements* par `date_jour`.
- Matrice (carte de chaleur) : lignes = `fct_flux…[heure]`, colonnes = `dim_date[libelle_jour]`, valeur = *Solde net*, couleur divergente → profil intrajournalier.
- Barres : *Décaissements* par `dim_type_transaction[libelle_type]`.
- Cartes : *Taux de netting potentiel %* (flux intragroupe compensables), *Taux de fraude %*.

### Page 3 — Prévisions (analyse prédictive)
- Graphique en courbes : axe = `mart_prevision_tresorerie[date_jour]`, valeur = *Position prévue P50*, légende = `type_valeur` (Réalisé / Prévision). Volet **Analyse → Barres d'erreur** : limite haute = *P95*, limite basse = *P05* → **cône d'incertitude**.
- Carte : *Probabilité de passer sous le besoin de liquidité %*.
- Tableau `mart_qualite_prevision` : filiale, série, modèle, WAPE, biais, champion (icône).
- Histogramme réel vs prévu : `mart_backtest_journalier` filtré sur `est_champion = Vrai`.

### Page 4 — Change & couverture
- Courbe `mart_prevision_change` : *Taux de change prévu P50* + barres d'erreur P05/P95, avec *Taux de change réalisé* en superposition (contrôle a posteriori), segment = devise.
- Barres : *Exposition au change* par devise ; cartes *VaR 95 % 10 j*, *Coût annuel de couverture*, *Effet de change cumulé*.
- Tableau `fct_taux_change` : volatilité annualisée par devise ; mettre en évidence le RUB (`est_rupture_serie`).

### Page 5 — Simulateur de stress (What-if)
- Les 4 curseurs + segment `Devises choquées[Cible]`.
- Cartes dynamiques : *Position stressée*, *Horizon de survie (jours)*, *Besoin de refinancement stressé*, *Coût du refinancement stressé*.
- Tableau par filiale avec *Statut de résilience* coloré via *Couleur statut* (Format → Couleur d'arrière-plan → Valeur du champ).
- Matrice des scénarios précalculés : lignes = `dim_scenario_stress[libelle_scenario]`, colonnes = filiale, valeur = `mart_stress_test[horizon_survie_jours]`, couleur selon `statut_resilience`. Info-bulle : `reference_historique`.

## 5. Conseils pour la soutenance
- Démonstration en direct : régler *Choc retraits* sur 20 % (scénario SVB) et montrer quelles filiales passent en « Critique ».
- Montrer le cône de prévision et le contrôle a posteriori du change : c'est la preuve concrète que le prédictif fonctionne.
- Afficher le lignage `dbt docs` pour démontrer la traçabilité (exigence Bâle III / BCBS 239).
