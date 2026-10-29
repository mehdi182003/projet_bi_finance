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
data/sources_internes/  exports BRUTS (« sales ») des 4 systèmes bancaires des filiales, versionnés (lots de 100)
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
Power BI : powerbi/Cresus/Cresus.pbip (6 pages, 73 mesures DAX), import depuis marts
```
dbt ne stocke rien : il exécute le SQL **dans** PostgreSQL. Tests, documentation et lignage : `dbt docs`.

## 3. Les données (point le plus important pour comprendre le projet)
1. **Départ** : PaySim (Kaggle `ealaxi/paysim1`, 6,36 M de lignes, 31 jours). Le profilage (docs/06) a montré qu'il est inexploitable seul : 12 jours normaux seulement, fraude constante, soldes incohérents, pas d'entrées interbancaires.
2. **Décision** : construire **3 ans (2023-2025)** de flux ancrés sur des **séries réelles** (docs/07).
   - Les dépôts à vue par pays viennent de la BCE, de la Fed (hebdomadaire), de la Banque du Canada, du SCB, de Danmarks Nationalbank, du FMI et de la BEAC.
   - Les taux directeurs viennent des API officielles et des communiqués BCEAO / BEAC.
   - PaySim ne sert plus que de « texture » (montants, types, heures, fraude).
3. **Exports bruts** (`etl/systemes_sources.py`, docs/08) : la « vérité » est exportée au format de 4 systèmes, avec des défauts réalistes injectés volontairement.

   | Système | Filiales | Défauts injectés |
   |---|---|---|
   | SAB | FR, BNL, FI | séparateur `;`, cp1252, virgule décimale, sens D/C, fichiers mensuels qui se chevauchent, annulations |
   | NORDIC | SE, DK, NO | heures UTC, montants signés, öre en Suède, extournes |
   | AMERICORE | CA, US | dates MM/JJ/AAAA AM/PM, colonnes débit / crédit, séparateur de milliers, comptes de test |
   | DELTA | CI, CM | ligne de titre et ligne de total, libellés sans norme, « FCFA » |

   Sur les 4 systèmes s'ajoutent des doublons, des devises et libellés non normalisés, et des clients manquants.
4. **Preuve de fiabilité** (tests dbt) :
   - **rapprochement comptable** jour par jour (10 960 jours-filiales) ;
   - **ancrage** sur les dépôts réels (491 dates, écart maximal de 0,000007 %) ;
   - **complétude** des fichiers.

   Après nettoyage, on retrouve **exactement** le nombre d'opérations réelles de chaque filiale.
5. **Volumes** : une ligne = un **lot** de `taille_lot` opérations.

   | Taille de lot | Lignes brutes | CSV décompressé | Où | Usage |
   |---|---|---|---|---|
   | 100 (défaut) | 2,9 M | 286 Mo (49 Mo compressé) | `data/sources_internes/` (Git) | dépôt, démo, tests |
   | 10 | 29,0 M | 2,83 Go (444 Mo compressé) | `data/generees/lot_10/` (local) | « gros volume » réaliste sur un PC |
   | 1 | ~290 M | ~28 Go | local | déconseillé sur un portable (plus de 100 Go dans PostgreSQL) |

   **Mesuré sur 4 cœurs / 16 Go de RAM, en lots de 10** :
   - génération : 17 min, pic mémoire de 5 Go ;
   - pipeline complet (load + dbt + prévision) : 22 min, 150 contrôles réussis ;
   - base PostgreSQL : **13 Go**. Prévoir **~20 Go libres** (fichiers temporaires pendant `dbt build`).

   Les montants totaux et les ancrages sont identiques quelle que soit la taille de lot ; seul le grain change.

## 4. Lancer le projet (Windows, PowerShell)
```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
docker compose up -d                       # PostgreSQL 16 sur localhost:5432, base "cresus"
python pipeline.py                         # jeu versionné (lots de 100) : ~3,5 min, aucun téléchargement
```
**Gros volume en local** (nécessite le CSV PaySim dans `data/raw/`, à télécharger depuis Kaggle) :
```powershell
python pipeline.py --regenerer --taille-lot 10    # génère data/generees/lot_10 puis charge et transforme tout
# pour les lancements suivants, ajouter dans .env :
# DOSSIER_SOURCES_INTERNES=data/generees/lot_10
```
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

## 8. Résultats clés (jeu versionné, à re-vérifier si on régénère)
- Prévision quotidienne : régression calendaire championne sur 19 séries sur 20. WAPE : 12-16 % sur les décaissements, 12-23 % sur les encaissements.
- Dépôts réels de janvier 2026 dans la fourchette à 90 % pour **7 filiales sur 9** ; change : 94 % des jours dans la fourchette.
- Janvier = 40 % des jours sous 100 % de liquidité. Réserve requise pour janvier 2026 : ~18 % en France contre 15 % actuellement. Sur-réserve en zone CFA et en Norvège (~90 M€).
- 2023 : 4,0 Md€ de refinancement net ; 2025 : 2,6 Md€ de placements nets. Effet de change sur 3 ans : −57 M€ (USD), −46 M€ (NOK).
- ETL : 2 896 020 lignes brutes → 2 788 404 opérations (3,7 % rejetées, toutes tracées avec leur motif).

## 9. Limites connues et points à vérifier
- Transactions et défauts des exports : **simulés** (aucune banque ne publie ses opérations). Sont réels : dépôts, taux, change, jours fériés.
- Hypothèses : profil intra-mensuel (paie, prélèvements), parts de marché, taux de réserve par filiale.
- Taux BCEAO du 16/12/2022 **déduit** (`a_verifier = true`). Cameroun : 10 mois interpolés.
- Le projet `.pbip` a été validé (bibliothèque Microsoft TOM et schémas JSON officiels) mais **jamais ouvert dans Power BI Desktop** (généré sous Linux). Premier test à faire sous Windows.

## 10. Reste à faire
- [ ] Ouvrir `Cresus.pbip` sous Windows, actualiser, corriger d'éventuels visuels.
- [ ] Générer le gros volume en local (`--regenerer --taille-lot 10`) et vérifier que `dbt build` reste vert.
- [ ] Rapport « réponse à l'appel d'offres » (~15 pages Word) à partir de docs/01 à 08.
- [ ] Support de soutenance (PowerPoint) ; modèles du cours : `04_IBI_SUPPORT_SOUTENANCE…pptx`, `05_IBI_MOE_POC…`.
- [ ] Corriger la fiche d'expertise : Côte d'Ivoire = **XOF** (pas XAF) ; outil de restitution = **Power BI** (la fiche cite Tableau) ; ajouter les filiales d'Europe du Nord.
- [ ] Valider avec le groupe le choix Power BI (le groupe parlait initialement de Tableau).
