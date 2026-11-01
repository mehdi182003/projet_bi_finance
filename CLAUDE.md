# CLAUDE.md — Contexte du projet Crésus (à lire avant toute reprise)

> Ce fichier est chargé automatiquement par Claude Code à l'ouverture d'une session dans ce dépôt.
> Il sert aussi de note de passation pour l'équipe : où en est le projet, pourquoi il est construit
> ainsi, comment le lancer et ce qu'il reste à faire.

## 1. Le projet en bref
- **Cours** : étude de cas IBI (BI), sujet 3 « BI prédictive Finance ».
- **Problématique** : *Comment l'analyse prédictive et la simulation peuvent-elles être des facteurs de gains dans la gestion de trésorerie d'une banque ?*
- **Client fictif** : ZF Banque, avec 10 filiales en France, Europe du Nord, Afrique (CFA) et Amérique du Nord. Projet « Crésus » de la Direction Financière.
- **Livrables du cours** : fiche AMOA (rendue), rapport « réponse à l'appel d'offres » (~15 pages Word), support de soutenance (PowerPoint), POC.
- **Stack imposée par le groupe** : **Python → PostgreSQL → dbt → Power BI**.
- **Langue** : tout est en français (code, commentaires, documentation, messages).

## 2. Architecture (ELT en couches, « médaillon »)
```
data/sources_internes/  exports BRUTS (« sales ») des 4 systèmes bancaires des filiales, versionnés (lots de 500)
data/generees/lot_<n>/  mêmes exports à plus gros volume, générés en local (ignorés par Git)
data/sources/           séries RÉELLES : dépôts et taux directeurs des banques centrales, cours BCE (Webstat)
        │  Python (etl/chargement_*.py) : chargement tel quel, en texte, incrémental (MD5), tracé
        ▼
PostgreSQL = data warehouse
  raw           bronze : lignes brutes + fichier, ligne, date de chargement
  staging       argent : 1 modèle dbt par système source (typage, formats, fuseaux, unités, sens)
  intermediate  argent : union, correspondances, dédoublonnage, exclusions, rejets tracés (RG-NET-xx)
  marts         or     : schéma en étoile (dim_* conformes, fct_* au grain documenté) + marts d'analyse
  ml                   : sorties Python (prévisions, réserve optimale, contrôle a posteriori)
        ▼
Power BI : powerbi/Cresus/Cresus.pbip (6 pages, 75 mesures DAX), import depuis marts
```
dbt ne stocke rien : il exécute le SQL **dans** PostgreSQL. Tests, documentation et lignage : `dbt docs`.

## 3. Les données (point le plus important pour comprendre le projet)
1. **Départ** : PaySim (Kaggle `ealaxi/paysim1`, 6,36 M de lignes, 31 jours). Le profilage (docs/06) a montré qu'il est inexploitable seul : 12 jours normaux seulement, fraude constante, soldes incohérents, pas d'entrées interbancaires.
2. **Décision** : construire **3 ans (2023-2025)** de flux ancrés sur des **séries réelles** (docs/07).
   - Les dépôts à vue par pays viennent de la BCE, de la Fed (hebdomadaire), de la Banque du Canada, du SCB, de Danmarks Nationalbank, du FMI et de la BEAC.
   - Les taux directeurs viennent des API officielles et des communiqués BCEAO / BEAC.
   - PaySim ne sert plus que de « texture » : **forme** des montants, heures, fraude.
   - **Réalisme économique** (docs/07 § 3.4) : composition des décaissements par type selon la zone, tickets recalés par type (carte 45 €, retrait 110 €, prélèvement 180 €…) et modulés par le niveau de vie du pays (Côte d'Ivoire 0,35, Norvège 1,5…), prélèvements en début de mois, traitements en lot le matin. Les totaux restent exactement ancrés sur les dépôts réels : seuls le nombre et la taille des opérations changent.
3. **Exports bruts** (`etl/systemes_sources.py`, docs/08) : la « vérité » est exportée au format de 4 systèmes, avec des défauts réalistes injectés volontairement, tels qu'on les rencontre dans les extractions bancaires en entreprise.

   | Système | Filiales | Défauts injectés |
   |---|---|---|
   | SAB | FR, BNL, FI | séparateur `;`, cp1252, virgule décimale, sens D/C, fichiers mensuels qui se chevauchent, annulations, **migration** (dates ISO dès juillet 2024), **fichiers retouchés sous Excel** (espace insécable), références avec espaces, vérifications de carte à 0,00 |
   | NORDIC | SE, DK, NO | heures UTC, montants signés, öre en Suède, extournes, **pré-autorisations `PENDING`**, **nouvelle colonne `channel`** en 2025, codes entité en casse variable |
   | AMERICORE | CA, US | dates MM/JJ/AAAA AM/PM, colonnes débit / crédit, séparateur de milliers, comptes de test, **montants comptables `(…)` et `US$`**, **données tardives** (clôture à 18 h), codes entité en casse variable |
   | DELTA | CI, CM | ligne de titre et ligne de total, libellés sans norme, « FCFA », **encodage cassé** (`DÃ‰PÃ”T`), **en-tête répété** toutes les 5 000 lignes, vérifications de carte à 0 |

   Sur les 4 systèmes s'ajoutent des doublons, des **fichiers renvoyés** (`_v2`), des devises et libellés non normalisés, et des clients manquants ou codés `NULL` / `N/A` / `?` / `0000000`. Catalogue des défauts traités : `marts.mart_qualite_defauts`.
4. **Preuve de fiabilité** (tests dbt) :
   - **rapprochement comptable** jour par jour (10 960 jours-filiales) ;
   - **ancrage** sur les dépôts réels (481 dates contrôlées, écart maximal de 0,00001 %) ;
   - **complétude** des fichiers.

   Après nettoyage, on retrouve **exactement** le nombre d'opérations réelles de chaque filiale.
5. **Volumes** : une ligne = un **lot** de `taille_lot` opérations.

   Avec les tickets réalistes, les 3 ans représentent **~2,03 milliards d'opérations**.

   | Taille de lot | Lignes brutes | Fichiers | Où | Usage |
   |---|---|---|---|---|
   | **500** (défaut) | 4,3 M | 64 Mo compressés | `data/sources_internes/` (Git) | dépôt, démo, collègues (~8 min, base de 1,9 Go) |
   | **50** | **42,7 M** | **586 Mo compressés** | `data/generees/lot_50/` (local) | **gros volume local (~20 Go au total)** |

   **Mesuré sur 6 cœurs / 15 Go de RAM, en lots de 50 (31/10/2026)** :
   - génération : 16 min ;
   - chargement : 11 min (rechargement incrémental : seuls les fichiers modifiés) ;
   - `dbt build` : 39 min, 138 contrôles réussis + 18 sur les marts de prévision ; pipeline complet depuis zéro : ~1 h 10 ;
   - base PostgreSQL : **18 Go**. Prévoir **~30 Go libres** (fichiers temporaires pendant `dbt build`).

   Les montants totaux et les ancrages sont identiques quelle que soit la taille de lot ; seul le grain change.

## 4. Lancer le projet (Windows, PowerShell)
Procédure complète, valeurs attendues et dépannage : **docs/09**.
```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
docker compose up -d                       # PostgreSQL 16 sur localhost:5432, base "cresus"
python pipeline.py                         # jeu versionné (lots de 500) : ~8 min, aucun téléchargement
```
**Gros volume en local** (nécessite le CSV PaySim dans `data/raw/`, à télécharger depuis Kaggle) :
```powershell
python pipeline.py --regenerer --taille-lot 50    # génère data/generees/lot_50 puis charge et transforme tout
# pour les lancements suivants, ajouter dans .env :
# DOSSIER_SOURCES_INTERNES=data/generees/lot_50
```
**Relancer chaque étape à la main** (venv activé, depuis la racine) :
```powershell
python pipeline.py --etapes generer --taille-lot 50               # Python : exports bruts « sales » (CSV)
python pipeline.py --etapes extract load                          # Python : CSV -> PostgreSQL, schéma raw (incrémental)
cd dbt ; dbt build --profiles-dir . --exclude tag:prevision ; cd ..   # dbt : staging -> intermediate -> marts + tests (--full-refresh si les données ont changé)
python pipeline.py --etapes prevision dbt_prev                    # Python : prévisions -> ml, puis dbt : marts de prévision
# Power BI : ouvrir powerbi/Cresus/Cresus.pbip -> Actualiser
```
Sans Docker, un PostgreSQL 15/16 installé localement convient (base `cresus`, utilisateur et mot de passe `postgres`).
Autres commandes utiles :
- `python pipeline.py --etapes dbt prevision dbt_prev` : relancer seulement certaines étapes.
- `cd dbt ; dbt build --profiles-dir .` : modèles et tests.
- `dbt docs generate --profiles-dir . ; dbt docs serve --profiles-dir .` : lignage.
- `python -m etl.sources_reelles` : rafraîchir les séries des banques centrales (Internet requis).
- **Power BI** : ouvrir `powerbi/Cresus/Cresus.pbip` → *Actualiser* (PostgreSQL `postgres` / `postgres`, onglet Base de données). Guide : docs/04.
- **Régénérer le projet Power BI** après un changement de modèle dbt (nécessite le SDK .NET 8) :
  `dotnet build powerbi/outils/TomTool -c Release -o powerbi/outils/TomTool/bin` puis
  `python powerbi/generer_pbip.py --tomtool powerbi/outils/TomTool/bin/TomTool.dll`

## 5. Fichiers clés
| Fichier | Rôle |
|---|---|
| `pipeline.py` | Orchestrateur : extract → [générer] → load → dbt → prévision → dbt |
| `etl/chargement_sources_internes.py` | Load des exports bruts dans `raw` (incrémental, idempotent, par paquets) |
| `etl/generateur_flux.py`, `etl/systemes_sources.py` | Vérité ancrée sur le réel, puis exports bruts (pour `--regenerer`) |
| `etl/sources_reelles.py` | API des banques centrales (dépôts, taux) → `data/sources/` |
| `etl/prevision.py` | Champion/challenger quotidien, Monte-Carlo, réserve requise P99, change |
| `etl/controle_a_posteriori.py` | Prévision vs dépôts réels de janvier 2026 (hors échantillon) |
| `dbt/models/staging/stg_*__operations.sql` | Nettoyage par système source |
| `dbt/models/intermediate/int_operations_controlees.sql` | Règles RG-NET, motif de rejet |
| `dbt/models/marts/` | Dimensions, faits, analyses, prévision (grains dans `schema.yml`) |
| `dbt/seeds/` | Référentiels : filiales (part de marché, système, fuseau), devises, taux directeurs réels, scénarios, correspondances |
| `powerbi/mesures_dax.dax` | **Source unique des mesures DAX** (lues par `generer_pbip.py`) |
| `docs/01` à `docs/08` | Cadrage AMOA, spécifications MOE, prédictif, Power BI, synthèse/SWOT, profil et KPI, données 3 ans, ETL |

## 6. Conventions
- Toute règle métier ou de nettoyage porte un code (`RG-POS-06`, `RG-NET-07`, etc.) en commentaire SQL et dans la documentation.
- Tout changement doit garder `dbt build` vert. Seule alerte attendue : la rupture du rouble.
- Les colonnes des marts sont en `double precision` (post-hook `convertir_numeric_en_double`) : Power BI ne sait pas lire un `numeric` de plus de 28 chiffres.
- Ne jamais versionner `data/raw/` (PaySim, 494 Mo), `data/generees/` (gros volumes) ni `.env`.
- Les chiffres cités dans la documentation proviennent de requêtes sur les marts : les vérifier après toute régénération.
- PostgreSQL : une chaîne vide chargée par `COPY CSV` devient `NULL` (penser à `coalesce(trim(x), '')`).

## 7. Historique des décisions (pour la soutenance)
1. POC v1 sur PaySim, sur 31 jours.
2. Profilage avec skills (`data:explore-data`) : artefacts de PaySim, fenêtre restreinte à 12 jours.
3. Revue dbt (`data-pipeline-builder`), réévaluation statistique des KPI (`data:statistical-analysis`) et relecture (`data:validate-data`). Ancien ratio de liquidité remplacé (double comptage) ; netting et taux de fraude retirés.
4. Passage à 3 ans ancrés sur les dépôts réels. Tous les taux directeurs viennent maintenant de sources officielles : plusieurs valeurs saisies de mémoire étaient fausses.
5. Trésorerie **gérée** : réserve ramenée chaque mois à sa cible. Sans cela, la fuite réelle des dépôts à vue en zone euro rendait la position négative.
6. Contrôle sur les dépôts réels de janvier 2026 : il a révélé la **saisonnalité de janvier**. Effet « mois » ajouté ; couverture de la fourchette passée de 4/9 à 7/9.
7. Exports bruts multi-systèmes et vrai ETL de nettoyage, versionnés dans Git ; option `--taille-lot` pour les gros volumes en local.
8. Audit de réalisme économique : les tickets PaySim (retrait médian 1 500 €, identiques dans tous les pays) faussaient la composition des flux (48 % des décaissements en retraits DAB). Composition par zone, tickets par type et niveau de vie ajoutés ; fraude PaySim ramenée à l'ordre de grandeur BCE. Les totaux ancrés et les résultats clés (§ 8) sont inchangés.
9. Défauts d'entreprise ajoutés aux exports : migration de format, dérive de schéma, fichiers Excel, montants comptables, pré-autorisations, données tardives, fichiers renvoyés, valeurs nulles codées, encodage cassé, en-têtes répétés. Chacun a sa règle RG-NET et le rapprochement comptable reste exact.
10. Premier test dans Power BI Desktop (01/11/2026). Il a révélé ce que les validations de schéma ne pouvaient pas voir : import bloqué par des `numeric` de plus de 28 chiffres, filtres inutilisables (liste déroulante coupée), courbes additionnant des devises différentes, totaux de jours sans sens, simulateur incohérent avec `mart_stress_test` (fenêtre de 7 jours au lieu de 30, besoin compensé entre filiales). Tout est corrigé et les valeurs ont été recoupées avec la base.
11. Jeu versionné régénéré avec le générateur actuel en lots de 500, pour garder un dépôt léger.

## 8. Résultats clés (gros volume en lots de 50, vérifiés le 01/11/2026 ; le jeu versionné donne des ordres de grandeur très proches, voir docs/09 § 11)
- Prévision quotidienne : régression calendaire championne sur 20 séries sur 20. WAPE : 12-15 % sur les décaissements, 12-28 % sur les encaissements (États-Unis 27,6 %).
- Gros volume : refinancements 2023 = 3,98 Md€, placements 2025 = 2,62 Md€ ; effet de change −58 M€ (USD), −46 M€ (NOK) ; 7 filiales sur 9 dans la fourchette ; réserve requise France 18,1 % ; fraude 0,02-0,06 % des décaissements en valeur.
- Dépôts réels de janvier 2026 dans la fourchette à 90 % pour **7 filiales sur 9** ; change : 94 % des jours dans la fourchette.
- Janvier = 34 % des jours sous 100 % de liquidité (60 sur 175). Réserve requise pour janvier 2026 : ~18 % en France contre 15 % actuellement. Sur-réserve en zone CFA et en Norvège (~90 M€).
- 2023 : 4,0 Md€ de refinancement net ; 2025 : 2,6 Md€ de placements nets. Effet de change sur 3 ans : −58 M€ (USD), −46 M€ (NOK).
- ETL : 42 669 356 lignes brutes → 40 749 329 opérations (4,5 % rejetées, toutes tracées avec leur motif). Jeu versionné : 4 259 292 → 4 073 845 (4,35 %).

## 9. Limites connues et points à vérifier
- Transactions et défauts des exports : **simulés** (aucune banque ne publie ses opérations). Sont réels : dépôts, taux, change, jours fériés.
- Hypothèses : profil intra-mensuel (paie, prélèvements), parts de marché, taux de réserve par filiale, composition des flux par zone, tickets moyens par type et facteurs de niveau de vie (`etl/generateur_flux.py`, ordres de grandeur à sourcer pour le rapport).
- Taux BCEAO du 16/12/2022 **déduit** (`a_verifier = true`). Cameroun : 10 mois interpolés.
- Le catalogue `marts.mart_qualite_defauts` n'est pas importé dans Power BI : il se consulte dans pgAdmin. L'ajouter demande de régénérer le `.pbip` (SDK .NET 8).
- La dernière version du rapport a été écrite sans TomTool (SDK .NET absent du PC de test) : `_Mesures.tmdl` et les visuels ont été réécrits à partir de `mesures_dax.dax` et `generer_pbip.py`, puis contrôlés dans Power BI Desktop. `generer_pbip.py` en contient bien les sources, mais sa conversion par TomTool n'a pas été rejouée.
- Parcours Docker (`docker compose up -d`) non testé sur le PC de référence.

## 10. Reste à faire
- [x] Ouvrir `Cresus.pbip` sous Windows, actualiser, corriger les visuels.
- [x] Générer le gros volume en local (`--regenerer --taille-lot 50`) et vérifier que `dbt build` reste vert.
- [x] Régénérer le jeu versionné avec le générateur actuel (lots de 500).
- [ ] Ajouter `mart_qualite_defauts` à la page Qualité du rapport.
- [ ] Rapport « réponse à l'appel d'offres » (~15 pages Word) à partir de docs/01 à 08.
- [ ] Support de soutenance (PowerPoint) ; modèles du cours : `04_IBI_SUPPORT_SOUTENANCE…pptx`, `05_IBI_MOE_POC…`.
- [ ] Corriger la fiche d'expertise : Côte d'Ivoire = **XOF** (pas XAF) ; outil de restitution = **Power BI** (la fiche cite Tableau) ; ajouter les filiales d'Europe du Nord.
- [ ] Valider avec le groupe le choix Power BI (le groupe parlait initialement de Tableau).
