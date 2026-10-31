# 07 — Trois ans de données fiables (2023-2025) : construction et vérifications

## 1. Pourquoi changer de données
Le profilage du vrai PaySim (docs/06) a montré que ses 31 jours ne suffisent pas : activité normale sur 12 jours seulement, fraude injectée à rythme constant, soldes incohérents, pas d'entrées interbancaires (la trésorerie se vidait d'environ 2 % par jour). Avec 12 jours, impossible d'observer une saisonnalité mensuelle ou annuelle, un cycle de taux ou une crise.

**Contrainte incontournable** : aucune banque ne publie ses transactions clients (secret bancaire, RGPD). Des données « 100 % réelles au niveau de la transaction » n'existent pas en accès libre. La solution retenue combine donc **ce qui est réel et publié** avec une désagrégation documentée :

| Composante | Origine | Réel ? |
|---|---|---|
| Niveau, tendance, saisonnalité annuelle et chocs des dépôts | Séries officielles des banques centrales (tableau § 2) | **Oui** |
| Taux directeurs (placement, refinancement, coût de couverture) | API BCE, Fed, Banque du Canada, Riksbank, Norges Bank, Danmarks Nationalbank ; communiqués BCEAO et BEAC | **Oui** |
| Taux de change quotidiens | BCE via Banque de France Webstat | **Oui** |
| Jours fériés de chaque pays | Bibliothèque `holidays` (calendriers officiels) | **Oui** |
| Forme des montants (dispersion), heures, fraude | Tirées parmi les 4,9 M de transactions **réelles** de PaySim (fenêtre stable) | Oui (proxy) |
| Niveau des tickets par type et par pays, composition des flux par type | Hypothèses documentées (§ 3, point 4) | Non : hypothèse |
| Répartition des flux à l'intérieur du mois (paie, prélèvements) | Hypothèses documentées (§ 3) | Non : hypothèse |
| Part de marché de ZF Banque par pays | Paramètre (`dbt/seeds/ref_filiales.csv`) | Non : hypothèse |

## 2. Séries réelles utilisées (cache versionné dans `data/sources/`)

| Filiale | Série de dépôts | Source | Fréquence | Évolution 2023-2025 |
|---|---|---|---|---|
| France, Benelux, Finlande | Dépôts à vue des ménages et des entreprises (BSI L21) | BCE | mensuelle | −14 %, −11 %, −15 % |
| États-Unis | Dépôts des banques commerciales (DPSACBW027NBOG) | Fed H.8 / FRED | **hebdomadaire** | +5 % |
| Canada | M1+ brut non désaisonnalisé (V37258) | Banque du Canada | mensuelle | +13 % |
| Suède | M1 | SCB | mensuelle | −5 % |
| Danemark | Dépôts transférables des entreprises et des ménages (DNRUIPI) | Danmarks Nationalbank | mensuelle | +9 % |
| Norvège, Côte d'Ivoire | Dépôts transférables inclus dans la masse monétaire (MFS F22) | FMI | mensuelle | +6 %, +46 % |
| Cameroun | Monnaie scripturale des banques commerciales | Bulletins BEAC | mensuelle (10 mois interpolés et signalés) | +31 % |

La baisse des dépôts à vue en zone euro est un phénomène réel : avec la hausse des taux de la BCE (jusqu'à 4 % en 2023), les ménages et les entreprises ont déplacé leur épargne vers des comptes à terme.

## 3. Méthode de génération (`etl/generateur_flux.py`)
1. **Ancrage** : encours de ZF Banque = encours national × part de marché. Les flux nets générés entre deux dates de publication égalent **exactement** la variation réelle de l'encours.
2. **Volume brut** : décaissements d'un jour ouvré ≈ 0,8 % de l'encours. C'est l'ordre de grandeur mesuré dans PaySim (0,78 %) et cohérent avec les statistiques de paiement de détail.
3. **Calendrier** :
   - aucun virement le week-end ni les jours fériés du pays ;
   - cartes et retraits à 35 % du niveau d'un jour ouvré ;
   - prélèvements renforcés les 3 premiers jours ouvrés ;
   - salaires sur les 2 derniers jours ouvrés (Europe, Afrique) ou le 15 et en fin de mois (Amérique du Nord) ;
   - bruit quotidien log-normal.
4. **Composition et tickets réalistes** : PaySim n'est pas une banque de détail (retrait médian ~1 500 €, mêmes montants dans tous les pays, 0,6 % de prélèvements). On en garde la **forme** des montants de chaque type (dispersion, queue des gros montants, fraude, heure), mais :
   - chaque jour, les décaissements sont ventilés par type selon la part de la **valeur** observée dans une banque de détail de la zone :

     | Zone | Virements émis | Prélèvements | Cartes | Retraits | Encaissements en virements (sinon espèces) |
     |---|---|---|---|---|---|
     | Europe | 50 % | 25 % | 17 % | 8 % | 90 % |
     | Afrique (CI, CM) | 40 % | 5 % | 10 % | 45 % | 55 % |
     | Amérique du Nord | 42 % | 28 % | 22 % | 8 % | 93 % |

     Ni virement ni prélèvement le week-end ; prélèvements concentrés sur les 3 premiers jours ouvrés (loyers, factures) ; composition légèrement variable d'un jour à l'autre ;
   - le ticket moyen de chaque type est recalé (France : carte 45 €, retrait 110 €, prélèvement 180 €, virement émis 2 500 €, dépôt d'espèces 450 €, virement reçu 1 800 €), puis modulé par un **facteur de niveau de vie** (Norvège 1,5, États-Unis 1,4, Côte d'Ivoire 0,35, Cameroun 0,30…, ordre de grandeur à vérifier) ;
   - prélèvements et virements reçus sont traités en lot entre 5 h et 9 h ;
   - le nombre de clients découle de l'encours (dépôt à vue moyen de 20 000 € par client en France, modulé par le niveau de vie).

   Les montants d'une journée sont ensuite ajustés pour respecter exactement le total du jour : **ces hypothèses changent le nombre et la taille des opérations, jamais les totaux ancrés sur les dépôts réels.** Résultat (France) : carte médiane 33 €, retrait 92 €, prélèvement 101 €, salaire 1 527 € ; ~390 opérations par client et par an ; 64 % des opérations sont des paiements par carte. En Côte d'Ivoire, retrait médian 32 € (≈ 21 000 FCFA).
5. **Échantillon pondéré** : une ligne = un lot de `taille_lot` opérations de même montant. Les 3 ans représentent ~2,03 milliards d'opérations : 41 M de lignes en lots de 50 (gros volume local), 4 M en lots de 500.
6. **Exports bruts** (`etl/systemes_sources.py`) : cette « vérité » n'est jamais chargée directement. Elle est exportée au format de chaque système bancaire (SAB, NORDIC, AMERICORE, DELTA), avec des défauts réalistes. Ce sont **ces fichiers sales** qui sont versionnés dans `data/sources_internes/` et que l'ETL nettoie (docs/08). Le rapprochement comptable prouve que le nettoyage restitue exactement la vérité.

## 4. Gestion de trésorerie modélisée (RG-POS-06/07)
Au 1er de chaque mois, la trésorerie ramène la réserve à sa cible (15 % des dépôts en Europe, 20 % en Afrique, 12 % en Amérique du Nord) :
- elle **lève un refinancement** si la réserve est passée sous la cible ;
- elle **place l'excédent** si la réserve est au-dessus.

Dans le mois, la position suit les flux réels.

Résultat : 4,0 Md€ de refinancement net en 2023 (fuite des dépôts pendant la hausse des taux), puis 2,6 Md€ de placements nets en 2025.

## 5. Vérifications de fiabilité
| Contrôle | Résultat |
|---|---|
| Encours reconstitué = encours réel publié, à chaque date (test dbt `assert_ancrage_depots_reels`, 491 points) | ✅ Écart maximal de 0,000007 % |
| Complétude du chargement (test `assert_conservation_volumes`) | ✅ |
| Taux de change disponibles chaque jour de la période | ✅ |
| Vraisemblance : décaissements / dépôts entre 0,05 % et 5 % par jour | ✅ |
| **Prévision confrontée à du réel postérieur** : encours de janvier 2026 publiés après la date d'arrêté | ✅ Erreur médiane de −3,7 % à +2,0 % ; réel dans la fourchette à 90 % pour 7 filiales sur 9 |
| Fourchette de change confrontée aux cours réels de janvier 2026 | ✅ 119 jours-devises sur 126 (94 %) dans la fourchette à 90 % |

## 6. Limites à annoncer
- **Les transactions individuelles restent simulées.** Ce qui est réel : les niveaux mensuels (hebdomadaires aux États-Unis), les taux, le change et le calendrier des jours fériés.
- **Le profil intra-mensuel est une hypothèse**, et le modèle de prévision utilise les mêmes variables de calendrier. Sa précision journalière (WAPE de 12 à 23 %) est donc en partie « attendue ». En revanche, le contrôle sur janvier 2026 porte sur des niveaux réels qu'il n'a pas vus.
- **Cameroun** : 10 mois sur 36 sont interpolés entre des points trimestriels BEAC ; les points de 2023 mélangent des millésimes provisoires et révisés.
- **Parts de marché** : ce sont des hypothèses (FR 1 %, Benelux et Finlande 2 %, nordiques 1 %, Côte d'Ivoire et Cameroun 8 %, Canada 0,2 %, États-Unis 0,03 %). Elles fixent la taille, pas la dynamique.
- **Taux BCEAO de décembre 2022** : déduit des communiqués de septembre 2022 et mars 2023 (marqué `a_verifier`).
