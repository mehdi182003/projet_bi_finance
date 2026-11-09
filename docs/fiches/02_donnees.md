# Partie 2 : les données et le change

[Retour à la répartition](00_repartition.md)

## Ta partie en bref

Tu expliques **d'où viennent les données** et **comment on les a construites**. C'est la partie qui intrigue le plus le prof, car aucune banque ne publie ses opérations. Tu dois savoir dire précisément ce qui est réel, ce qui est simulé, et pourquoi on peut faire confiance au résultat. Tu présentes aussi le change : la fourchette de cours prévue, la perte possible (VaR) et la décision de couvrir ou non chaque devise.

**Diapos :** 6 (prérequis : les données), 11 (du réel et du simulé), 14 (la partie « couvrir » ; la partie 6 présente « résister »).

**Fichiers :** `etl/sources_reelles.py`, `etl/extraction_bce.py`, `etl/extraction_paysim.py`, `etl/generateur_flux.py`, `etl/systemes_sources.py`, le dossier `data/`, et pour le change : la fonction `prevoir_change` de `etl/prevision.py`, `dbt/models/marts/faits/fct_taux_change.sql`, `dbt/models/marts/analyses/mart_exposition_change.sql`, `dbt/models/marts/prevision/mart_prevision_change.sql`.

## À savoir dire en une minute

> Aucune banque ne publie les opérations de ses clients. Nous sommes partis de PaySim, un jeu public de transactions, mais il ne couvre que 31 jours et il a de gros défauts. Nous avons donc construit 3 ans d'opérations, de 2023 à 2025, en partant de séries réelles : les dépôts publiés par 7 banques centrales, les taux directeurs, les cours de change de la BCE et les jours fériés. Le générateur crée les opérations jour par jour, et leur cumul retombe exactement sur les vrais dépôts à chaque date publiée. PaySim ne sert plus qu'à donner une forme réaliste aux montants et aux heures. Ensuite, nous exportons ces opérations au format de 4 systèmes bancaires différents, avec les défauts qu'on trouve dans les vraies extractions : doublons, mauvais encodage, dates en plusieurs formats, montants mal écrits. C'est ce que le nettoyage doit ensuite corriger. Pour le change, nous simulons une fourchette de cours à 30 jours, nous mesurons la perte possible avec la VaR et nous décidons, devise par devise, s'il vaut la peine de se couvrir.

## 1. Les notions à maîtriser

### Les données

| Notion | En clair |
|---|---|
| **Donnée réelle** | Publiée par un organisme officiel : banque centrale, office statistique |
| **Donnée simulée (synthétique)** | Créée par un programme pour ressembler à la réalité, quand la vraie donnée n'est pas accessible |
| **Série temporelle** | Une suite de valeurs datées : par exemple les dépôts de la France à chaque fin de mois |
| **Fréquence** | Le rythme de publication : mensuel pour la plupart des pays, hebdomadaire pour les États-Unis |
| **Point d'ancrage** | Une date où l'on connaît la vraie valeur des dépôts. Le générateur doit retomber dessus |
| **Interpolation** | Estimer une valeur manquante entre deux valeurs connues, par exemple un mois non publié |
| **Profilage** | Examiner un jeu de données (volumes, valeurs manquantes, anomalies) avant de l'utiliser |
| **API** | Une adresse web qui renvoie des données à un programme, ici celles des banques centrales |
| **Cache** | Une copie locale des données téléchargées, pour pouvoir relancer sans Internet |
| **Graine aléatoire** | Un nombre fixe qui rend le hasard reproductible : avec la même graine, on obtient exactement les mêmes données |
| **Lot (taille de lot)** | Une ligne de fichier représente plusieurs opérations identiques, 500 ou 50. Cela garde des fichiers raisonnables |
| **Données « sales »** | Des fichiers avec des erreurs de format, des doublons, des valeurs manquantes, comme dans une vraie entreprise |
| **CSV** | Un fichier texte en tableau : une ligne par enregistrement, les colonnes séparées par `,` ou `;` |
| **Encodage** | La façon d'écrire les lettres en octets. `UTF-8` est le standard moderne ; `cp1252` est l'ancien encodage Windows. Lire un fichier avec le mauvais encodage casse les accents (« DÃ‰PÃ”T » au lieu de « DÉPÔT ») |
| **BOM** | Quelques octets invisibles au début de certains fichiers UTF-8, qui peuvent gêner la lecture |
| **gzip (`.gz`)** | Un format de compression : 586 Mo au lieu de plusieurs Go pour le gros volume |
| **Extourne** | Une écriture qui annule une écriture précédente erronée |
| **Pré-autorisation** | Une réservation d'argent par carte (statut `PENDING`) avant le vrai paiement. La compter en plus du paiement ferait un doublon |
| **Grand livre** | Le registre comptable officiel de la banque. Nous en produisons un résumé par jour et par filiale pour contrôler le nettoyage |

### Le change

| Notion | En clair |
|---|---|
| **Quantile, P5, P50, P95** | P5 : 5 % des trajectoires sont en dessous. P50 : le milieu. P95 : 5 % sont au-dessus. Entre P5 et P95, on a 90 % des cas : c'est la fourchette à 90 %. Dans le rapport : bas, milieu, haut |
| **Volatilité** | L'ampleur habituelle des variations d'un cours. On la donne en pourcentage par an |
| **Rendement logarithmique** | La variation d'un cours d'un jour à l'autre, mesurée par le logarithme du rapport entre les deux cours |
| **Mouvement brownien géométrique** | Un modèle où le cours varie chaque jour d'un pourcentage tiré au hasard, avec la volatilité observée |
| **Marche aléatoire** | Le meilleur prévisionniste du change est souvent « demain comme aujourd'hui » (Meese et Rogoff, 1983) |
| **Loi normale, 1,645** | Dans une loi normale, 95 % des valeurs sont sous la moyenne + 1,645 écart-type |
| **Exposition au change** | L'argent détenu en devise étrangère, converti en euros |
| **VaR à 95 % sur 10 jours** | La perte que l'on ne dépassera pas dans 95 % des cas sur 10 jours |
| **Couverture** | Un contrat qui fige le cours futur ; son coût annuel est à peu près l'écart entre les taux des deux monnaies (parité des taux d'intérêt) |

## 2. Pourquoi PaySim ne suffit pas

PaySim (Kaggle, `ealaxi/paysim1`) contient 6 362 620 transactions simulées d'un service de paiement mobile, sur 31 jours. Le profilage ([docs/06](../06_profil_donnees_et_choix_kpi.md)) a montré :

| Problème | Ce qu'on a vu | Conséquence |
|---|---|---|
| Activité anormale | Seuls les jours 6 à 17 sont normaux ; les autres ont 1 à 6 % du volume habituel | 12 jours utilisables seulement |
| Fraude artificielle | Environ 11 fraudes par heure, de jour comme de nuit | Impossible d'étudier la fraude dans le temps |
| Soldes incohérents | Les soldes avant et après opération ne se suivent pas | Pas de position fiable |
| Pas d'entrées interbancaires | Ni salaires ni virements reçus d'autres banques | Le flux net est toujours négatif |
| 31 jours seulement | Pas de saison, pas de cycle de taux | Impossible de prévoir janvier ou de voir 2023 |

**Décision :** garder PaySim seulement comme « texture » (la forme des montants, les heures, une part de fraude), et construire les volumes à partir des séries réelles. PaySim n'est plus chargé dans l'entrepôt.

## 3. Les séries réelles

Elles sont téléchargées par `etl/sources_reelles.py`, puis gardées dans `data/sources/` (fichiers versionnés dans Git), pour que le projet tourne ensuite sans Internet.

| Pays | Dépôts à vue | Source |
|---|---|---|
| France, Belgique, Finlande | Dépôts à vue des ménages et des entreprises | BCE, statistiques BSI |
| États-Unis | Dépôts des banques commerciales, chaque semaine | Fed (FRED, série DPSACBW027NBOG) |
| Canada | Masse monétaire M1+ brute | Banque du Canada |
| Suède | Masse monétaire M1 | SCB (office statistique suédois) |
| Danemark | Dépôts transférables | Danmarks Nationalbank |
| Norvège, Côte d'Ivoire | Dépôts transférables | FMI |
| Cameroun | Monnaie scripturale des banques | Bulletins de la BEAC |

**Les autres données réelles :**
- les **taux directeurs** de chaque banque centrale (BCE, Fed, Banque du Canada, Riksbank, Danmarks Nationalbank, Norges Bank, BCEAO, BEAC), dans `data/sources/taux_directeurs_reels.csv` et `dbt/seeds/ref_taux_directeurs.csv` ;
- les **cours de change** de référence de la BCE, via Webstat de la Banque de France (`data/sources/webstat_taux_change_bce.csv`) ;
- les **jours fériés** de chaque pays, avec la bibliothèque Python `holidays` ;
- les **dépôts de janvier 2026**, publiés après la date d'arrêté et utilisés pour le contrôle a posteriori (`data/sources/depots_reels_janvier_2026.csv`).

**Deux points à connaître.** Le Cameroun a 10 mois interpolés, car la BEAC publie peu. Le taux BCEAO du 16/12/2022 a été déduit, et il est marqué `a_verifier`. Plusieurs taux saisis de mémoire au début du projet étaient faux : depuis, tous viennent de sources officielles.

## 4. La génération des 3 ans, étape par étape

C'est le fichier `etl/generateur_flux.py`. Il traite les filiales une par une.

### Étape 1 : les ancrages

```python
s = depots.set_index("date_ancrage").encours.sort_index() * part_pct / 100
```

On prend les dépôts réels du pays et on les multiplie par la part de marché de ZF Banque (1 % pour la France). On obtient l'**encours de ZF Banque à chaque date publiée** : ce sont les points d'ancrage. Un point de départ au 31/12/2022 est ajouté, par interpolation si besoin. Le résultat est écrit dans `data/sources/ancrages_zf.csv`.

### Étape 2 : le calendrier

La fonction `calendrier()` donne un poids à chaque jour, séparément pour les sorties et pour les entrées.

- **Sorties :** poids 1 un jour ouvré, 0,35 un week-end ou un jour férié, et × 1,35 les 3 premiers jours ouvrés du mois (loyers, factures).
- **Entrées :** poids 1 un jour ouvré, 0,20 sinon, et × 4 les 2 derniers jours ouvrés du mois (salaires en Europe et en Afrique). En Amérique du Nord, la paie tombe deux fois par mois : × 3 vers le 15 et le dernier jour ouvré.
- Un **bruit aléatoire** d'environ 15 % rend chaque jour un peu différent.

### Étape 3 : les flux de chaque jour

```python
c["sortie_base"] = TAUX_ROTATION * c.encours_ref * c.w_out / ...
entrees = sorties + delta
```

- Chaque jour ouvré, les sorties valent environ **0,8 % de l'encours** (`TAUX_ROTATION`), ce qui correspond à ce qu'on observe dans PaySim.
- Entre deux ancrages, on connaît la variation réelle de l'encours (`delta`). Les entrées sont alors calculées pour que **entrées − sorties = variation réelle**. C'est ce qui fait retomber le cumul exactement sur les vrais dépôts.
- En cas de très forte baisse des dépôts, les entrées ne descendent pas sous 30 % des sorties : on augmente alors les sorties.

### Étape 4 : la composition par type d'opération

Les sorties sont réparties par type selon la zone (`PROFILS_FLUX`).

| Part de la valeur décaissée | Virements | Prélèvements | Cartes | Retraits |
|---|---|---|---|---|
| Europe | 50 % | 25 % | 17 % | 8 % |
| Afrique | 40 % | 5 % | 10 % | 45 % |
| Amérique du Nord | 42 % | 28 % | 22 % | 8 % |

Les entrées sont des virements reçus (90 % en Europe, 55 % en Afrique, 93 % en Amérique du Nord) ou des dépôts d'espèces. Pas de virement ni de prélèvement le week-end ; les prélèvements sont plus forts en début de mois.

### Étape 5 : les montants

PaySim avait des montants irréalistes (un retrait médian de 1 500 €, le même dans tous les pays). On garde seulement la **forme** de ses montants, puis on recale la moyenne sur un ticket réaliste :

| Type | Ticket moyen (France) |
|---|---|
| Paiement par carte | 45 € |
| Retrait | 110 € |
| Prélèvement | 180 € |
| Virement émis | 2 500 € |
| Dépôt d'espèces | 450 € |
| Virement reçu | 1 800 € |

Ce ticket est multiplié par un facteur de niveau de vie : 0,35 en Côte d'Ivoire, 0,30 au Cameroun, 1,5 en Norvège, 1,4 aux États-Unis. Enfin, les montants d'une journée sont ajustés pour que leur total égale exactement la cible du jour. **Changer le ticket change le nombre d'opérations, jamais les totaux.**

### Étape 6 : les détails réalistes

- **Fraude :** on ne garde que 10 % des fraudes de PaySim, ce qui ramène la fraude à environ 0,03 % de la valeur décaissée, l'ordre de grandeur publié par la BCE.
- **Heures :** reprises de PaySim ; les prélèvements et les virements reçus sont traités en lot entre 5 h et 9 h.
- **Clients :** leur nombre vient de l'encours (environ 20 000 € par client en France). Quelques clients sont très actifs, comme dans la réalité.
- **Lot :** une ligne représente `POIDS` opérations, 500 pour le jeu léger, 50 pour le gros volume.
- **Référence :** chaque opération reçoit une référence unique, par exemple `FR20230102-000001`.

### Étape 7 : le grand livre

Pour chaque filiale et chaque jour, on calcule le total des crédits, des débits et le nombre d'opérations de la « vérité ». C'est le fichier `data/sources_internes/comptabilite/soldes_comptables_journaliers.csv`. Il sert au test de rapprochement de la partie 4.

## 5. Les 4 systèmes bancaires et leurs défauts

Le fichier `etl/systemes_sources.py` exporte la vérité au format de 4 systèmes, un par groupe de filiales. Chaque fichier est mensuel et compressé, par exemple `data/sources_internes/sab/FR/SAB_ZF-FR_202301.csv.gz`.

| Système | Filiales | Format | Défauts propres |
|---|---|---|---|
| **SAB** | France, Benelux, Finlande | `;`, cp1252, virgule décimale, montant positif et sens D ou C | Migration : dates `jj/mm/aaaa` puis `aaaa-mm-jj` à partir de juillet 2024 ; fichiers retouchés sous Excel (espace insécable dans les milliers) ; références avec espaces ; opérations annulées ; fichiers mensuels qui se chevauchent ; vérifications de carte à 0,00 |
| **NORDIC** | Suède, Danemark, Norvège | `,`, UTF-8 avec BOM, heure en UTC, montant signé | Montants suédois en öre (centimes) ; extournes ; pré-autorisations `PENDING` ; nouvelle colonne `channel` en 2025 ; code entité en minuscules ou avec espaces |
| **AMERICORE** | Canada, États-Unis | `,`, dates `MM/JJ/AAAA` avec AM/PM, colonnes débit et crédit séparées | Séparateur de milliers ; montants comptables `(1,234.56)` et `US$` ; comptes de test ; données tardives (après la clôture de 18 h, dans le fichier suivant) |
| **DELTA** | Côte d'Ivoire, Cameroun | `;`, cp1252, ligne de titre et ligne de total, dates `aaaammjj` | Libellés sans norme ; « FCFA » au lieu du code ISO ; encodage cassé (`DÃ‰PÃ”T`) ; en-tête répété toutes les 5 000 lignes ; vérifications de carte à 0 |

**Les défauts communs aux 4 systèmes**, avec leur fréquence (dictionnaire `TAUX`) :

| Défaut | Part des lignes |
|---|---|
| Doublon | 0,4 % |
| Opération annulée | 0,2 % |
| Extourne | 0,1 % |
| Compte de test | 0,05 % |
| Libellé non standard | 4 % |
| Devise mal écrite (`€`, `eur`) | 2 % |
| Client manquant ou mal formé | 0,3 % à 1 % |
| Client codé `NULL`, `N/A`, `?`, `0000000` | 0,4 % |
| Indicateur de fraude vide | 10 % |
| Pré-autorisation (NORDIC) | 2 % |
| Montant comptable (AMERICORE) | 3 % |
| Encodage cassé (DELTA) | 3 % |

S'y ajoutent des **fichiers entiers renvoyés une seconde fois** (`_v2`, 3 % des fichiers) et des fichiers retouchés sous Excel (15 % des fichiers SAB).

**Le principe important :** tous ces défauts sont récupérables. Après nettoyage, on doit retrouver exactement la vérité : c'est ce que vérifie le rapprochement avec le grand livre.

## 6. Les deux jeux de données

| | Jeu léger | Gros volume |
|---|---|---|
| Taille de lot | 500 opérations par ligne | 50 opérations par ligne |
| Lignes brutes | 4 259 292 | 42 669 356 |
| Fichiers compressés | 64 Mo | 586 Mo |
| Où | `data/sources_internes/`, dans Git | `data/generees/lot_50/`, en local |
| Génération | déjà faite | 16 min |

Les deux représentent environ **2,03 milliards d'opérations** et ont exactement les mêmes totaux. Seuls les indicateurs portés par les opérations rares changent avec la taille de lot. Par exemple, la part des gros décaissements passe de 9,6 % (lots de 500) à 13,8 % (lots de 50). Seul le gros volume fait référence pour ces chiffres.

## 7. Le change : prévision, VaR et couverture

Les cours viennent de la BCE (section 3). Le projet en tire trois choses : une fourchette pour le mois suivant, la perte possible (VaR) et une décision de couverture par devise. La fourchette est calculée en Python (`prevoir_change` dans `etl/prevision.py`), la VaR et la décision en SQL (`mart_exposition_change`).

### La fourchette de change à 30 jours

```python
rendements = np.diff(np.log(g.taux_eur.to_numpy()))[-250:]
vol_jour_calendaire = rendements.std(ddof=1) * np.sqrt(252 / 365)
chocs = rng.normal(-0.5 * vol_jour_calendaire**2, vol_jour_calendaire, size=(horizon, nb_sim))
trajectoires = depart * np.exp(np.cumsum(chocs, axis=0))
```

1. On mesure la volatilité sur les 250 dernières cotations (environ un an de jours ouvrés), puis on la ramène à un jour calendaire.
2. On simule 2 000 trajectoires de 30 jours : chaque jour, le cours varie d'un pourcentage tiré au hasard (mouvement brownien géométrique).
3. On en tire P5, P50 et P95. Le milieu reste presque plat : on ne parie pas sur une hausse ou une baisse, on donne l'ampleur possible.

**Résultat :** sur janvier 2026, le cours réel est resté dans la fourchette **94 % des jours** (119 jours sur 126, toutes devises confondues). Le rouble n'est pas prévu, car sa série est interrompue.

**Attention à la lecture :** le graphique montre combien de devises vaut 1 euro. Quand la courbe monte, la devise baisse, donc nos avoirs dans cette devise valent moins en euros.

### La VaR (`mart_exposition_change`)

```sql
{{ var('quantile_var_95') }} * t.volatilite_quotidienne * abs(p.exposition_eur)            as var_95_1j_eur,
{{ var('quantile_var_95') }} * t.volatilite_quotidienne * abs(p.exposition_eur) * sqrt(10) as var_95_10j_eur,
```

- **Exposition** : la position de toutes les filiales dans une devise, convertie en euros (**RG-RIS-02**).
- **Volatilité quotidienne** : l'écart-type des 60 dernières variations du cours (**RG-RIS-01**, dans `fct_taux_change`).
- **VaR à 1 jour** = 1,645 × volatilité × exposition ; **à 10 jours**, on multiplie par √10, l'horizon de Bâle (**RG-RIS-03**).
- Le franc CFA a une VaR nulle : son risque n'est pas une variation quotidienne, c'est une dévaluation brutale, traitée par les stress tests.

La VaR du groupe, 26,6 M€, est la **somme** des VaR des devises : c'est prudent, car cela suppose que toutes les devises baissent ensemble. Si elles bougeaient indépendamment, elle serait d'environ 13,8 M€.

### La décision de couverture

```sql
case when dv.regime_change = 'flottant' then td.taux_local_pct - td.taux_eur_pct else 0 end as cout_couverture_annuel_pct
...
case
    when regime_change = 'fixe'          then 'Parité fixe'
    when volatilite_annualisee_pct < 1   then 'Inutile'
    when cout_couverture_annuel_pct < 0  then 'À couvrir'
    when cout_couverture_annuel_pct / volatilite_annualisee_pct < 0.25 then 'Prioritaire'
    else 'À arbitrer'
end as recommandation_couverture
```

- **Coût de la couverture** = écart entre le taux directeur de la devise et celui de l'euro (**RG-COU-01**). Si la devise a un taux plus bas que l'euro, la couverture rapporte.
- **Rapport coût / risque** = coût / volatilité (**RG-COU-02**). Plus il est bas, plus la protection est bon marché par rapport au risque.

| Devise | Exposition | VaR 10 j | Décision | Pourquoi |
|---|---|---|---|---|
| CAD | 257 M€ | 3,6 M€ | Prioritaire | Couverture peu chère au regard du risque |
| SEK | 620 M€ | 8,4 M€ | À couvrir | La couverture rapporte (coût négatif) |
| USD | 572 M€ | 8,5 M€ | À arbitrer | Couverture chère |
| NOK | 365 M€ | 6,0 M€ | À arbitrer | Couverture chère |
| DKK | 279 M€ | 0,1 M€ | Inutile | La couronne danoise suit l'euro |
| XOF, XAF | 501 M€ | 0 | Parité fixe | Taux fixe, à suivre par les stress tests |

L'effet de change déjà subi sur 3 ans : −58,2 M€ (USD), −46,2 M€ (NOK), −29,4 M€ (CAD), −1,2 M€ (DKK), +16,8 M€ (SEK). Tout couvrir coûterait 15,3 M€ par an : d'où une couverture ciblée.

## 8. Le code à connaître

### Le tirage des opérations (`tirer`)

```python
n = np.maximum(np.rint(cibles_eur / (POIDS * ticket_eur)).astype(int), (cibles_eur > 0).astype(int))
idx = rng.integers(0, len(pool), n.sum())
...
facteur = np.divide(cibles_eur, somme, out=np.zeros_like(cibles_eur), where=somme > 0)
t["montant_eur"] = t.montant_eur.values * np.repeat(facteur, n)
```

1. Pour chaque jour, le nombre de lignes `n` = montant cible du jour / (taille du lot × ticket moyen). Au moins une ligne si la cible n'est pas nulle.
2. On tire au hasard `n` opérations PaySim du bon type.
3. Leur montant = forme PaySim × ticket moyen.
4. On calcule un facteur pour que la somme du jour égale exactement la cible, et on l'applique.

### La reproductibilité

```python
rng = np.random.default_rng(GRAINE_ALEATOIRE)       # 42 pour les flux
rng_exports = np.random.default_rng(GRAINE_DEFAUTS) # 2024 pour les défauts
```

Avec les mêmes graines, la génération produit exactement les mêmes fichiers. C'est indispensable pour que tout le groupe obtienne les mêmes chiffres.

### La commande

```bash
python pipeline.py --regenerer --taille-lot 50
```

Elle demande le fichier PaySim dans `data/raw/` (494 Mo, à télécharger sur Kaggle, jamais mis dans Git).

### L'extraction des cours de change (`etl/extraction_bce.py`)

```python
long = donnees[["date_cours", *DEVISES_BCE]].melt(id_vars="date_cours", var_name="code_devise", value_name="taux")
long["taux"] = long["taux"].str.replace(",", ".", regex=False).astype(float)
```

Le fichier Webstat de la Banque de France a une colonne par devise (format « large »), 6 lignes d'en-tête, des virgules décimales et un tiret les jours sans cotation. `melt` le passe au format « long » : une ligne par date et par devise, plus pratique pour une base de données. Si le fichier Webstat manque, le script télécharge l'historique de la BCE avec la bibliothèque `requests`. Le résultat, `data/raw/bce_taux_change_long.csv`, est chargé dans `raw.bce_taux_change`.

### PaySim (`etl/extraction_paysim.py`)

Il cherche le fichier PaySim dans `data/raw/`. S'il n'y est pas, il le télécharge avec l'API de Kaggle (bibliothèque `kaggle`, identifiants dans `.env`) ; sinon, il explique comment le déposer à la main. Il ne sert qu'avec `--regenerer`.

### Les API des banques centrales (`etl/sources_reelles.py`)

```python
url = (f"https://data-api.ecb.europa.eu/service/data/BSI/M.{pays}.N.A.L21.A.1.U2.{secteur}.Z01.E"
       f"?format=csvdata&startPeriod={DEBUT[:7]}&endPeriod={FIN[:7]}")
```

- Une fonction par source (`depots_bce`, `depots_fed`, `depots_banque_canada`, `depots_scb_suede`, `depots_statbank_danemark`, `depots_fmi`, `depots_beac_cameroun`) appelle l'API avec `requests` et renvoie la série des dépôts. Pour la BCE, on additionne les dépôts des ménages et ceux des entreprises.
- `collecter_depots` réunit les séries et **interpole les mois manquants**, en les marquant `est_interpole`.
- `collecter_taux` récupère les taux directeurs et ne garde que les dates où le taux change. La zone CFA n'a pas d'API : ses taux viennent d'un fichier rempli à partir des communiqués (`taux_directeurs_cfa_manuels.csv`).
- `assurer_cache` ne télécharge que si les fichiers de `data/sources/` manquent ; `python -m etl.sources_reelles` force la mise à jour.

### Les fonctions qui fabriquent les défauts (`etl/systemes_sources.py`)

| Fonction | Ce qu'elle fait |
|---|---|
| `_variante` | Remplace une partie des libellés ou des devises par une variante non standard (`€`, `VIR RECU SEPA`…) |
| `_client` | Abîme les identifiants clients : zéros perdus, vides, `NULL`, `N/A`, `?`, `0000000` |
| `_entite` | Écrit le code entité en minuscules ou avec des espaces |
| `_ajouter_doublons` | Recopie 0,4 % des lignes |
| `_verifications_carte` | Ajoute des vérifications de carte à 0,00 |
| `_fichiers_mensuels` | Découpe par mois, avec un jour de chevauchement (SAB) ou les opérations tardives après 18 h (AMERICORE) |
| `_ecrire` | Écrit le fichier dans le bon encodage, répète l'en-tête (DELTA), renvoie parfois le fichier en `_v2`, compresse en gzip |
| `export_sab`, `export_nordic`, `export_americore`, `export_delta` | Mettent la vérité au format de chaque système |
| `soldes_filiale`, `ecrire_soldes` | Calculent et écrivent le grand livre |

La compression utilise `mtime=0` : régénérer avec les mêmes graines donne exactement les mêmes fichiers, octet pour octet.

### La volatilité du change (`fct_taux_change.sql`)

```sql
ln(taux_eur / lag(taux_eur) over (partition by code_devise order by date_cours)) as rendement_log
stddev_samp(rendement_log) over (partition by code_devise order by date_cours
                                 rows between 59 preceding and current row) as volatilite_quotidienne
```

`lag` donne le cours de la veille et `ln` la variation, en logarithme. `stddev_samp` sur les 60 dernières cotations donne la volatilité quotidienne ; multipliée par √252, elle donne la volatilité annuelle. L'euro et le franc CFA ont une volatilité nulle. C'est cette volatilité qu'utilise la VaR (section 7).

## 9. Les questions probables du prof

**Vos données sont-elles réelles ?**
En partie. Les dépôts, les taux, le change et les jours fériés sont réels. Les opérations sont simulées, mais leur cumul retombe sur les vrais dépôts sur 481 dates contrôlées, avec un écart maximal de 0,00001 %.

**Pourquoi ne pas avoir utilisé de vraies transactions ?**
Aucune banque ne les publie, à cause du secret bancaire et du RGPD. Les jeux publics comme PaySim sont eux-mêmes simulés et trop courts.

**Comment savez-vous que vos opérations sont réalistes ?**
Les volumes sont calés sur les vrais dépôts, le calendrier sur les vrais jours fériés, les tickets et la composition sur des ordres de grandeur bancaires. Ces paramètres sont des hypothèses, documentées dans le code et à sourcer pour un vrai projet.

**Pourquoi injecter des défauts volontairement ?**
Parce que les vraies extractions bancaires en ont toujours. Un POC sur des données propres ne prouverait pas qu'on sait les nettoyer.

**Pourquoi la fraude est-elle si faible ?**
PaySim en contient beaucoup trop. Nous n'en gardons que 10 %, ce qui ramène la fraude à l'ordre de grandeur de la BCE, environ 0,03 % de la valeur.

**À quoi sert la taille de lot ?**
À garder un volume gérable : avec des lots de 500, le jeu tient dans Git (64 Mo) et tourne en 7 minutes. Le gros volume, en lots de 50, montre que la chaîne tient 42,7 M de lignes.

**Que se passe-t-il si une API de banque centrale ne répond pas ?**
Les séries sont gardées dans `data/sources/`, donc le pipeline fonctionne sans Internet. Une fois, l'API de la BCE a répondu en erreur et une filiale disparaissait du contrôle : depuis, les dépôts de janvier 2026 sont gardés dans un fichier.

**Pourquoi ne pas prévoir le cours de change ?**
Les études montrent qu'on ne prévoit pas mieux le change qu'avec « demain comme aujourd'hui ». On donne donc une fourchette, qui a contenu le cours réel 94 % des jours.

**Comment calculez-vous la VaR, et pourquoi l'additionner ?**
1,645 × volatilité quotidienne × exposition, × √10 pour 10 jours. L'addition par devise est prudente ; sous indépendance, elle serait d'environ 13,8 M€ au lieu de 26,6 M€.

**Pourquoi ne pas tout couvrir ?**
Cela coûterait 15,3 M€ par an. On couvre là où la protection est bon marché par rapport au risque (CAD) ou rapporte (SEK).

## 10. Les limites à assumer

- Les opérations et leurs défauts sont simulés : la précision au jour près dépend de nos hypothèses.
- Les parts de marché, les tickets, la composition des flux et les facteurs de niveau de vie sont des ordres de grandeur à sourcer.
- Le générateur crée lui-même le rythme du calendrier, ce qui avantage la régression calendaire en partie 6.
- Le Cameroun a 10 mois interpolés et n'entre pas dans le contrôle de janvier 2026.
- La VaR suppose une loi normale ; les crises réelles ont des queues plus épaisses.

## 11. Pour t'entraîner

1. Ouvre `data/sources/depots_reels_2023_2025.csv` et repère la baisse des dépôts français en 2023.
2. Ouvre un fichier de chaque système (`data/sources_internes/sab/FR/…csv.gz` avec 7-Zip, ou dans Python) et retrouve les défauts : séparateur, dates, montants, libellés.
3. Dans `etl/generateur_flux.py`, retrouve `TICKET_MOYEN_EUR`, `FACTEUR_TICKET` et `PROFILS_FLUX`.
4. Dans pgAdmin, lance :
   ```sql
   select code_filiale, date_ancrage, encours_zf_devise from raw.ancrages_zf where code_filiale = 'FR' order by 2;
   ```
5. Explique à quelqu'un, sans notes, comment le cumul des flux retombe sur les vrais dépôts.
6. Sur la page Change, choisis la NOK puis la DKK et explique pourquoi la fourchette de la DKK est si étroite.
7. Calcule à la main la VaR à 10 jours d'une exposition de 100 M€ avec une volatilité quotidienne de 0,5 % : 1,645 × 0,005 × 100 × √10 ≈ 2,6 M€.

## 12. Avec qui tu travailles

| Partie | La frontière |
|---|---|
| 1. Besoin et KPI | Pourquoi les dépôts baissent en 2023 : c'est dans les données réelles |
| 3. Chargement | Tes fichiers sont ceux qu'elle charge : formats, encodages, lignes de titre et de total |
| 4. Nettoyage | Chaque défaut que tu as injecté a sa règle de nettoyage RG-NET |
| 5. Modèle et Power BI | La page Change & couverture et la mesure DAX de la VaR affichent ton mart `mart_exposition_change` |
| 6. Prévision | La régression calendaire retrouve le calendrier que tu as créé, une limite à connaître ; la même idée de simulation et de quantiles sert à ses flux |

## Annexe : tous les fichiers de ta partie

| Fichier | Ce qu'il contient |
|---|---|
| `etl/sources_reelles.py` | Le téléchargement des dépôts et des taux directeurs réels |
| `etl/extraction_bce.py` | La lecture des cours de change de la BCE (Webstat) |
| `etl/extraction_paysim.py` | La recherche ou le téléchargement de PaySim |
| `etl/generateur_flux.py` | La génération des 3 ans |
| `etl/systemes_sources.py` | Les exports des 4 systèmes, leurs défauts et le grand livre |
| `data/sources/depots_reels_2023_2025.csv` | Les dépôts réels par pays |
| `data/sources/taux_directeurs_reels.csv` | Les taux directeurs téléchargés |
| `data/sources/taux_directeurs_cfa_manuels.csv` | Les taux de la zone CFA, remplis à la main |
| `data/sources/webstat_taux_change_bce.csv` | Les cours de change de la BCE |
| `data/sources/beac_cameroun_monnaie_scripturale.csv` | Les dépôts du Cameroun (bulletins de la BEAC) |
| `data/sources/ancrages_zf.csv` | Les dépôts réels ramenés à la taille de ZF Banque |
| `data/sources/depots_reels_janvier_2026.csv` | Les dépôts de janvier 2026, pour le contrôle a posteriori |
| `data/sources_internes/` | Les 374 fichiers des filiales et le grand livre (`comptabilite/`) |
| `data/raw/` | PaySim, à déposer à la main, jamais mis dans Git |
| `dbt/seeds/ref_taux_directeurs.csv` | Les taux directeurs, en référentiel dbt |
| `dbt/seeds/ref_devises.csv` | Les 10 devises : régime de change, parité fixe, banque centrale |
| `dbt/models/marts/faits/fct_taux_change.sql` | Les cours quotidiens et la volatilité |
| `dbt/models/marts/analyses/mart_exposition_change.sql` | L'exposition, la VaR et la décision de couverture |
| `dbt/models/marts/prevision/mart_prevision_change.sql` | La fourchette de change prévue et le cours réel |
| `etl/prevision.py`, fonction `prevoir_change` | La simulation des cours à 30 jours |
| [docs/06](../06_profil_donnees_et_choix_kpi.md), [docs/07](../07_donnees_3_ans.md), [docs/08](../08_etl_sources_et_nettoyage.md) | Le profil de PaySim, la construction des 3 ans, le format des sources |
