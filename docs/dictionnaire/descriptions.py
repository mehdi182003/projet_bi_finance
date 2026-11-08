"""Descriptions du dictionnaire de données du projet Crésus (source unique de l'Excel livré).

Utilisé par docs/dictionnaire/generer_dictionnaire.py, qui lit la structure RÉELLE des tables dans
PostgreSQL et y associe ces descriptions. Une colonne présente en base sans description est signalée
à la génération : la compléter ici.

- TABLES   : une entrée par table (schéma.table) : type, question à laquelle elle répond, grain, description.
- COMMUNES : descriptions des colonnes qui ont le même sens dans toutes les tables.
- COLONNES : descriptions propres à une table (prioritaires sur COMMUNES).
"""

# --------------------------------------------------------------------------------------- tables
# type : Dimension / Fait (…) / Référentiel / Table brute / Vue de nettoyage / Table intermédiaire /
#        Sortie de modèle. « question » reprend la distinction du cours : les dimensions répondent à
#        qui / quoi / quand / où, les faits à « combien ».
TABLES = {
    # ===== Couche or : schéma en étoile (marts)
    "marts.dim_date": dict(
        type="Dimension", question="Quand ?", grain="1 ligne = 1 jour calendaire",
        description="Calendrier en français, partagé par tous les faits (dimension conforme). Couvre "
                    "l'historique de change, la période d'analyse 2023-2025 et l'horizon de prévision."),
    "marts.dim_filiale": dict(
        type="Dimension", question="Qui ? Où ?", grain="1 ligne = 1 filiale",
        description="Contexte des 10 filiales : identité, pays, région, devise, système bancaire source, "
                    "fuseau horaire, source des dépôts réels. Aucune mesure : les chiffres de chaque "
                    "filiale sont dans fct_situation_initiale_filiale (règle RG-MOD-01)."),
    "marts.dim_devise": dict(
        type="Dimension", question="Quoi ? (quelle monnaie)", grain="1 ligne = 1 devise",
        description="Référentiel des devises : libellé, régime de change (flottant, fixe, référence), "
                    "banque centrale, zone monétaire."),
    "marts.dim_type_transaction": dict(
        type="Dimension", question="Quoi ? (quel type d'opération)", grain="1 ligne = 1 type d'opération normalisé",
        description="Types d'opérations normalisés après nettoyage, avec leur catégorie de trésorerie et "
                    "leur sens (entrée ou sortie d'argent)."),
    "marts.dim_scenario_stress": dict(
        type="Dimension", question="Quoi ? (quelle crise)", grain="1 ligne = 1 scénario de stress",
        description="Contexte des 7 scénarios de stress : nom, ordre d'affichage et crise historique de "
                    "référence. Les chocs chiffrés appliqués à chaque filiale sont dans le fait "
                    "mart_stress_test (règle RG-MOD-01)."),
    "marts.fct_flux_tresorerie_horaire": dict(
        type="Fait transactionnel agrégé", question="Combien ? (flux)",
        grain="1 ligne = 1 heure x 1 filiale x 1 type d'opération x fraude (oui/non) x gros ticket (oui/non)",
        description="Fait principal : encaissements, décaissements et nombre d'opérations, agrégés à "
                    "l'heure. Chargement incrémental (35 derniers jours recalculés)."),
    "marts.fct_position_tresorerie_quotidienne": dict(
        type="Fait instantané périodique", question="Combien ? (position, encours)",
        grain="1 ligne = 1 jour x 1 filiale",
        description="Position de trésorerie de clôture, encours de dépôts, flux du jour et opérations de "
                    "trésorerie de fin de mois. Les positions et encours sont des stocks : on lit le "
                    "dernier jour, on ne les additionne pas dans le temps."),
    "marts.fct_situation_initiale_filiale": dict(
        type="Fait instantané (situation de départ)", question="Combien ? (point de départ)",
        grain="1 ligne = 1 filiale au 31/12/2022",
        description="Chiffres de départ et paramètres de pilotage de chaque filiale : part de marché, "
                    "taux de réserve cible, nombre de clients, encours de dépôts et réserve initiaux. "
                    "Ces nombres étaient auparavant dans dim_filiale (règle RG-MOD-01)."),
    "marts.fct_taux_change": dict(
        type="Fait instantané périodique", question="Combien ? (cours, volatilité)",
        grain="1 ligne = 1 jour x 1 devise",
        description="Cours de change quotidiens (EUR vers devise), variation du jour, volatilité "
                    "quotidienne et annualisée (60 dernières cotations), rupture de série."),
    "marts.mart_exposition_change": dict(
        type="Fait agrégé (analyse)", question="Combien ? (risque de change)", grain="1 ligne = 1 jour x 1 devise",
        description="Exposition du groupe au change par devise : position, effet de change, VaR à 95 % "
                    "(1 et 10 jours), coût de couverture et recommandation de couverture."),
    "marts.mart_liquidite_placement": dict(
        type="Fait instantané périodique (analyse)", question="Combien ? (liquidité)", grain="1 ligne = 1 jour x 1 filiale",
        description="Ratio de liquidité (LCR simplifié), consommation quotidienne, jours avant le seuil "
                    "de 100 %, liquidité excédentaire ou besoin de refinancement, gains et coûts associés."),
    "marts.mart_qualite_sources": dict(
        type="Fait agrégé (qualité)", question="Combien ? (lignes, défauts)", grain="1 ligne = 1 système x 1 filiale x 1 mois",
        description="Comptage des lignes reçues, retenues et des défauts détectés ou corrigés par l'ETL."),
    "marts.mart_qualite_defauts": dict(
        type="Fait agrégé (qualité)", question="Combien ? (lignes par défaut)",
        grain="1 ligne = 1 système x 1 filiale x 1 mois x 1 type de défaut",
        description="Catalogue des défauts des exports bruts et de leur traitement (ligne écartée ou "
                    "valeur corrigée). Non importé dans Power BI : à consulter dans pgAdmin."),
    "marts.mart_qualite_ancrage": dict(
        type="Fait instantané (contrôle)", question="Combien ? (écart réel / reconstitué)",
        grain="1 ligne = 1 filiale x 1 date publiée par la banque centrale",
        description="Contrôle de fiabilité : encours réel publié (ramené à la part de marché) comparé à "
                    "l'encours reconstitué par cumul des flux. Écart attendu : nul."),
    "marts.mart_stress_test": dict(
        type="Fait de simulation", question="Combien ? (impact d'une crise)", grain="1 ligne = 1 scénario x 1 filiale à la date d'arrêté",
        description="Résultat de chaque scénario de stress par filiale : chocs appliqués, position après "
                    "choc, horizon de survie, besoin et coût de refinancement, statut de résilience."),
    "marts.mart_prevision_tresorerie": dict(
        type="Fait de prévision", question="Combien ? (position prévue)", grain="1 ligne = 1 jour x 1 filiale (réalisé puis prévu)",
        description="Position réalisée puis projetée (fourchette bas / milieu / haut, P5 / P50 / P95) "
                    "issue de la simulation Monte-Carlo, et probabilité de passer sous le besoin de liquidité."),
    "marts.mart_prevision_change": dict(
        type="Fait de prévision", question="Combien ? (cours prévu)", grain="1 ligne = 1 jour x 1 devise (historique puis prévu)",
        description="Cours historiques puis fourchette de prévision à 30 jours, comparée au cours "
                    "réellement observé ensuite."),
    "marts.mart_controle_a_posteriori": dict(
        type="Fait de contrôle", question="Combien ? (écart prévision / réel)", grain="1 ligne = 1 filiale x 1 date de contrôle",
        description="Prévision des dépôts au 31/01/2026 confrontée aux dépôts réels publiés ensuite par "
                    "les banques centrales (test hors échantillon)."),
    "marts.mart_reserve_optimale": dict(
        type="Fait de prévision", question="Combien ? (réserve requise)", grain="1 ligne = 1 filiale à la date d'arrêté",
        description="Réserve requise pour rester au-dessus du besoin de liquidité dans 99 % des "
                    "simulations, comparée à la réserve actuelle : liquidité libérable et gain annuel."),
    "marts.mart_backtest_journalier": dict(
        type="Fait de prévision", question="Combien ? (réel / prévu)",
        grain="1 ligne = 1 origine x 1 filiale x 1 série x 1 modèle x 1 jour",
        description="Valeurs réelles et prévues jour par jour sur les 3 mois de backtest, pour les 3 "
                    "modèles comparés. Sert au calcul de l'erreur de prévision (WAPE)."),
    # ===== Prédictif (ml) : sorties Python, reprises par les marts de prévision
    "ml.backtest_prevision": dict(
        type="Sortie de modèle", question="Combien ? (réel / prévu)", grain="1 ligne = 1 origine x 1 filiale x 1 série x 1 modèle x 1 jour",
        description="Résultats bruts du backtest des 3 modèles (etl/prevision.py), en devise locale."),
    "ml.controle_depots_reels": dict(
        type="Sortie de modèle", question="Combien ? (écart prévision / réel)", grain="1 ligne = 1 filiale x 1 date de contrôle",
        description="Résultat du contrôle a posteriori (etl/controle_a_posteriori.py)."),
    "ml.prevision_change": dict(
        type="Sortie de modèle", question="Combien ? (cours prévu)", grain="1 ligne = 1 jour prévu x 1 devise",
        description="Fourchette de prévision des cours de change (mouvement brownien géométrique)."),
    "ml.prevision_tresorerie_quotidienne": dict(
        type="Sortie de modèle", question="Combien ? (position prévue)", grain="1 ligne = 1 jour prévu x 1 filiale",
        description="Quantiles de la simulation Monte-Carlo (1 000 trajectoires) des flux, de la position "
                    "et des dépôts pour janvier 2026."),
    "ml.reserve_optimale": dict(
        type="Sortie de modèle", question="Combien ? (réserve requise)", grain="1 ligne = 1 filiale",
        description="Réserve requise à 99 % issue de la simulation, liquidité libérable et gain annuel."),
    # ===== Référentiels (seeds dbt)
    "referentiel.ref_filiales": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 filiale",
        description="Paramétrage des filiales (fichier dbt/seeds/ref_filiales.csv) : identité, devise, "
                    "hypothèses (part de marché, taux de réserve), système source, fuseau horaire."),
    "referentiel.ref_devises": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 devise",
        description="Paramétrage des devises (régime de change, parité fixe, banque centrale)."),
    "referentiel.ref_types_transaction": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 type d'opération",
        description="Types d'opérations normalisés et leur sens de trésorerie."),
    "referentiel.ref_scenarios_stress": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 scénario",
        description="Paramétrage des 7 scénarios de stress : chocs par devise, choc de retraits, choc de "
                    "taux, multiplicateur de sorties, crise de référence."),
    "referentiel.ref_taux_directeurs": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 devise x 1 date de changement de taux",
        description="Historique des taux directeurs réels des banques centrales (sources officielles)."),
    "referentiel.ref_correspondance_libelles": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 libellé normalisé d'un système",
        description="Table de correspondance libellé source vers type d'opération (RG-NET-05), y compris "
                    "les libellés à l'encodage cassé."),
    "referentiel.ref_correspondance_devises": dict(
        type="Référentiel", question="Paramétrage", grain="1 ligne = 1 écriture de devise rencontrée",
        description="Table de correspondance des écritures de devise vers le code ISO (RG-NET-06)."),
    # ===== Couche bronze (raw) : données telles que reçues
    "raw.src_sab": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 ligne d'export SAB",
        description="Exports bruts du système SAB (France, Benelux, Finlande), chargés tels quels en texte."),
    "raw.src_nordic": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 ligne d'export NORDIC",
        description="Exports bruts du système NORDIC (Suède, Danemark, Norvège), chargés tels quels en texte."),
    "raw.src_americore": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 ligne d'export AMERICORE",
        description="Exports bruts du système AMERICORE (Canada, États-Unis), chargés tels quels en texte."),
    "raw.src_delta": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 ligne d'export DELTA",
        description="Exports bruts du système DELTA (Côte d'Ivoire, Cameroun), chargés tels quels en texte."),
    "raw.soldes_comptables": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 filiale x 1 jour",
        description="Totaux journaliers du grand livre (source indépendante) servant au rapprochement comptable."),
    "raw.ancrages_zf": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 filiale x 1 date publiée",
        description="Dépôts à vue réels publiés par les banques centrales, ramenés à l'échelle de ZF Banque."),
    "raw.bce_taux_change": dict(
        type="Table brute", question="Données reçues", grain="1 ligne = 1 jour x 1 devise",
        description="Cours de référence de la BCE (export Webstat de la Banque de France)."),
    "raw.journal_chargement": dict(
        type="Table technique", question="Traçabilité", grain="1 ligne = 1 fichier chargé",
        description="Journal du chargement incrémental : empreinte MD5, lignes lues et annoncées par fichier."),
    # ===== Couche argent : staging (vues) et intermediate
    "staging.stg_sab__operations": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 ligne brute SAB",
        description="Opérations SAB typées : dates multi-formats, montants à virgule, sens C/D, codes entité."),
    "staging.stg_nordic__operations": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 ligne brute NORDIC",
        description="Opérations NORDIC typées : heures UTC converties, montants signés, öre divisés par 100."),
    "staging.stg_americore__operations": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 ligne brute AMERICORE",
        description="Opérations AMERICORE typées : dates MM/JJ/AAAA AM/PM, colonnes débit / crédit, "
                    "format comptable et symboles de devise retirés."),
    "staging.stg_delta__operations": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 ligne brute DELTA",
        description="Opérations DELTA typées : dates aaaammjj, sens déduit de la nature, filiale lue dans "
                    "le nom du fichier."),
    "staging.stg_bce__taux_change": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 jour x 1 devise",
        description="Cours de référence BCE typés."),
    "staging.stg_zf__ancrages": dict(
        type="Vue de nettoyage", question="Données typées", grain="1 ligne = 1 filiale x 1 date publiée",
        description="Dépôts réels ramenés à l'échelle de ZF Banque, typés."),
    "intermediate.int_operations_controlees": dict(
        type="Table intermédiaire", question="Contrôle", grain="1 ligne = 1 ligne brute (des 4 systèmes)",
        description="Union des 4 systèmes avec toutes les règles de nettoyage appliquées et le motif de "
                    "rejet éventuel : aucune ligne n'est supprimée en silence."),
    "intermediate.int_operations_nettoyees": dict(
        type="Table intermédiaire", question="Données propres", grain="1 ligne = 1 lot d'opérations retenu",
        description="Opérations retenues après nettoyage (sans motif de rejet)."),
    "intermediate.int_operations_rejetees": dict(
        type="Table intermédiaire", question="Contrôle", grain="1 ligne = 1 ligne brute écartée",
        description="Lignes écartées par le nettoyage, avec leur motif."),
    "intermediate.int_mouvements_tresorerie": dict(
        type="Table intermédiaire", question="Données propres", grain="1 ligne = 1 mouvement de trésorerie (lot)",
        description="Opérations retenues converties en mouvements de trésorerie signés, en devise et en euros."),
    "intermediate.int_taux_change_journalier": dict(
        type="Table intermédiaire", question="Données propres", grain="1 ligne = 1 jour calendaire x 1 devise",
        description="Cours quotidiens complétés : week-ends et jours fériés reportés, parités fixes et euro ajoutés."),
    "intermediate.int_encours_initial": dict(
        type="Table intermédiaire", question="Données propres", grain="1 ligne = 1 filiale",
        description="Situation de départ de chaque filiale au 31/12/2022 (encours, réserve, clients)."),
}

# ------------------------------------------------------------------------------ colonnes communes
COMMUNES = {
    # clés et contexte
    "code_filiale": "Code de la filiale ZF Banque (FR, BNL, FI, SE, DK, NO, CI, CM, CA, US).",
    "code_devise": "Code ISO 4217 de la devise (EUR, SEK, DKK, NOK, XOF, XAF, CAD, USD).",
    "code_type": "Code du type d'opération normalisé (voir dim_type_transaction).",
    "code_scenario": "Code du scénario de stress (BASE, RUEE_MODEREE, RUEE_SEVERE, CHOC_DOLLAR, CHOC_NORDIQUE, DEVALUATION_CFA, COMBINE).",
    "systeme_source": "Système bancaire d'origine des données : SAB, NORDIC, AMERICORE ou DELTA.",
    "regime_change": "Régime de change de la devise : flottant, fixe (parité avec l'euro) ou référence (EUR).",
    "libelle_devise": "Nom de la devise en français.",
    "nom_filiale": "Nom de la filiale.",
    "pays": "Pays de la filiale.",
    "code_pays_iso": "Code pays ISO 3166 (2 lettres).",
    "region": "Région du groupe : Europe, Europe du Nord, Afrique ou Amérique du Nord.",
    "ordre_affichage": "Ordre de tri dans les rapports (clé de tri, pas une quantité).",
    "source_depots": "Source officielle des dépôts réels de la filiale (banque centrale et série).",
    "profil_paie": "Profil du calendrier de paie et de prélèvements utilisé par la génération des flux.",
    "fuseau_horaire": "Fuseau horaire de la filiale (heure locale des opérations).",
    "code_calendrier": "Code pays du calendrier des jours fériés.",
    "code_entite_source": "Code de l'entité dans le système source (ex. ZF-FR, SE01).",
    "banque_centrale": "Banque centrale de la devise.",
    "zone_monetaire": "Zone monétaire de la devise.",
    "remarque": "Commentaire sur la devise.",
    "parite_fixe_par_eur": "Parité fixe : unités de devise pour 1 euro (655,957 pour les francs CFA) ; vide pour une devise flottante.",
    "libelle_scenario": "Nom du scénario de stress.",
    "reference_historique": "Crise historique dont le scénario s'inspire.",
    "libelle_type": "Libellé du type d'opération.",
    "categorie_tresorerie": "Catégorie de trésorerie de l'opération (encaissement, décaissement, interbancaire…).",
    "description": "Description du type d'opération.",
    # dates
    "date_jour": "Jour (clé vers dim_date).",
    "date_position": "Jour de la position (clé vers dim_date).",
    "date_operation": "Jour local de l'opération (clé vers dim_date).",
    "date_cours": "Jour de cotation du cours de change (clé vers dim_date).",
    "date_arrete": "Date d'arrêté des données utilisées pour le calcul (31/12/2025).",
    "date_calcul": "Date et heure d'exécution du calcul Python (traçabilité).",
    "date_controle": "Date à laquelle la prévision est comparée au réel (31/01/2026).",
    "date_prevision": "Jour prévu.",
    "date_ancrage": "Date de publication des dépôts réels par la banque centrale.",
    "origine": "Date d'origine du backtest : dernier jour connu avant la période prévue.",
    "horodatage": "Date et heure locales de l'opération (fuseau de la filiale).",
    "heure_operation": "Date et heure de l'opération tronquées à l'heure pleine.",
    "mois": "Mois concerné (premier jour du mois).",
    # traçabilité
    "nom_fichier": "Nom du fichier d'export dont provient la ligne (traçabilité).",
    "num_ligne": "Numéro de la ligne dans le fichier d'export (traçabilité).",
    "_fichier": "Nom du fichier d'export chargé (traçabilité).",
    "_ligne": "Numéro de la ligne dans le fichier d'export (traçabilité).",
    "_date_chargement": "Date et heure du chargement dans la zone brute.",
    "id_ligne_source": "Identifiant technique de la ligne brute (système, fichier, ligne).",
    "source": "Source de la donnée (organisme et série).",
    # opérations (staging / intermediate)
    "ref_operation": "Référence de l'opération dans le système source, sans espaces de bord.",
    "libelle_source": "Libellé de l'opération tel que reçu (texte libre du système source).",
    "libelle_normalise": "Libellé en majuscules, sans accents ni espaces superflus, prêt pour la correspondance (RG-NET-05).",
    "nb_operations": "Nombre d'opérations réelles représentées par la ligne (1 ligne = 1 lot d'opérations).",
    "montant_unitaire_devise": "Montant d'une opération du lot, positif, en devise locale, après correction du format (RG-NET-04).",
    "montant_devise": "Montant total du lot (montant unitaire x nombre d'opérations), en devise locale.",
    "montant_eur": "Montant total du lot converti en euros au cours du jour.",
    "sens_source": "Sens lu dans la source : +1 entrée d'argent, -1 sortie.",
    "devise_source": "Devise telle que reçue, non normalisée (ex. €, eur, FCFA).",
    "client_source": "Identifiant client tel que reçu (peut être vide ou codé NULL, N/A, ?, 0000000).",
    "statut_source": "Statut de l'opération dans la source (VALIDE, ANNULE, BOOKED, REVERSAL, PENDING…).",
    "reference_extournee": "Référence de l'opération annulée par cette extourne (NORDIC).",
    "est_fraude": "Vrai si l'opération est signalée comme suspecte de fraude (indicateur vide = non suspect, RG-NET-11).",
    "est_compte_test": "Vrai si le compte est un compte de test (exclu, RG-NET-08).",
    "est_heure_convertie_utc": "Vrai si l'heure a été convertie d'UTC vers l'heure locale (RG-NET-03).",
    "est_montant_unites_mineures": "Vrai si le montant était en unités mineures (öre) et a été divisé par 100.",
    "est_format_corrige": "Vrai si un format a dû être corrigé (espace insécable, format comptable, symbole de devise, code entité…).",
    "est_gros_ticket": "Vrai si le montant unitaire de l'opération dépasse 10 000 EUR.",
    "id_client": "Identifiant client normalisé <FILIALE>-<7 chiffres> ; <FILIALE>-INCONNU si absent ou codé nul (RG-NET-09).",
    "motif_rejet": "Motif d'écartement de la ligne (Doublon, Opération annulée, Compte de test, Extourne…) ; vide si la ligne est retenue.",
    # change
    "taux_eur": "Cours de change : unités de la devise pour 1 euro (cours de référence BCE ; parité fixe pour les francs CFA).",
    "volatilite_annualisee_pct": "Volatilité annuelle du cours (écart-type des variations quotidiennes x racine de 252).",
    # paramètres de filiale
    "part_de_marche_depots_pct": "Part de marché supposée de ZF Banque dans les dépôts à vue du pays (hypothèse).",
    "taux_reserve_liquidite_pct": "Taux de réserve de liquidité cible de la filiale, en % des dépôts (politique actuelle).",
    "nb_clients": "Nombre de clients distincts observés dans les opérations retenues (2023-2025).",
    "encours_depots_initial_devise": "Encours de dépôts au 31/12/2022 = dépôts réels du pays x part de marché (RG-POS-01).",
    "reserve_liquidite_initiale_devise": "Réserve de liquidité au 31/12/2022 = encours initial x taux de réserve cible (RG-POS-02).",
    # stress
    "choc_retraits_pct": "Part des dépôts retirés immédiatement dans le scénario.",
    "choc_taux_bp": "Hausse du coût de refinancement dans le scénario, en points de base (100 pb = 1 point de %).",
    "multiplicateur_sorties": "Coefficient appliqué aux décaissements quotidiens dans le scénario (1 = normal).",
    "choc_change_usd_pct": "Variation du dollar US face à l'euro dans le scénario.",
    "choc_change_cad_pct": "Variation du dollar canadien face à l'euro dans le scénario.",
    "choc_change_cfa_pct": "Variation des francs CFA face à l'euro dans le scénario (dévaluation).",
    "choc_change_nordiques_pct": "Variation des couronnes suédoise et norvégienne face à l'euro dans le scénario.",
    # prévision
    "serie": "Série prévue : encaissements ou décaissements.",
    "modele": "Modèle de prévision : naïf hebdomadaire, Holt-Winters ou régression calendaire.",
    "est_champion": "Vrai si le modèle est le meilleur (plus faible WAPE) pour cette filiale et cette série.",
    "type_valeur": "Nature de la ligne : Réalisé / Historique (passé) ou Prévision (futur).",
    "taux_directeur_pct": "Taux directeur de la banque centrale de la devise à la date d'arrêté.",
    "taux_reserve_actuel_pct": "Taux de réserve de liquidité actuel de la filiale (politique fixe).",
    "reserve_requise_p99_pct": "Réserve requise, en % des dépôts, pour rester au-dessus du besoin de liquidité dans 99 % des simulations.",
    "liquidite_liberable_devise": "Liquidité libérable (> 0, sur-réserve) ou à lever (< 0), en devise locale.",
    "liquidite_liberable_eur": "Liquidité libérable (> 0, sur-réserve) ou à lever (< 0), en euros.",
    "gain_annuel_eur": "Gain annuel si la liquidité libérable est placée au taux directeur (négatif : coût du complément).",
    "proba_sous_100_politique_actuelle": "Probabilité de passer sous 100 % de liquidité le mois suivant avec la réserve actuelle.",
    "encours_depots_devise": "Encours de dépôts à vue de la filiale, en devise locale.",
    "depots_reels_devise": "Dépôts réels publiés par la banque centrale, ramenés à la part de marché, en devise locale.",
    "depots_p05_devise": "Dépôts prévus, bas de la fourchette (P5), en devise locale.",
    "depots_p50_devise": "Dépôts prévus, milieu de la fourchette (P50), en devise locale.",
    "depots_p95_devise": "Dépôts prévus, haut de la fourchette (P95), en devise locale.",
    "erreur_p50_pct": "Écart entre la prévision centrale (P50) et les dépôts réels, en % du réel.",
    "dans_intervalle_90": "Vrai si les dépôts réels tombent dans la fourchette P5-P95.",
    "taux_p05": "Cours prévu, bas de la fourchette (P5), en unités de devise pour 1 euro.",
    "taux_p50": "Cours prévu, milieu de la fourchette (P50), en unités de devise pour 1 euro.",
    "taux_p95": "Cours prévu, haut de la fourchette (P95), en unités de devise pour 1 euro.",
    "proba_sous_besoin_liquidite": "Probabilité que la position passe sous le besoin de liquidité (10 % des dépôts) ce jour-là.",
}

# ----------------------------------------------------------------------- colonnes par table
COLONNES = {
    "dim_date": {
        "date_jour": "Jour, clé primaire de la dimension.",
        "id_date": "Jour au format entier AAAAMMJJ.",
        "annee": "Année.", "trimestre": "Trimestre (1 à 4).", "mois": "Numéro du mois (1 à 12).",
        "libelle_mois": "Nom du mois en français.", "annee_mois": "Année et mois (AAAA-MM).",
        "jour_semaine": "Numéro du jour dans la semaine (1 = lundi, 7 = dimanche).",
        "libelle_jour": "Nom du jour en français.", "semaine_iso": "Numéro de semaine ISO.",
        "est_week_end": "Vrai le samedi et le dimanche.",
        "est_periode_analyse": "Vrai entre le 01/01/2023 et le 31/12/2025.",
        "est_futur_prevision": "Vrai après le 31/12/2025 (horizon de prévision).",
    },
    "dim_filiale": {"code_filiale": "Code de la filiale, clé primaire de la dimension.",
                    "code_devise": "Devise de la filiale (clé vers dim_devise)."},
    "dim_devise": {"code_devise": "Code ISO 4217, clé primaire de la dimension.",
                   "a_une_filiale": "Vrai si au moins une filiale opère dans cette devise."},
    "dim_type_transaction": {"code_type": "Code du type d'opération, clé primaire de la dimension.",
                             "sens_jambe_emetteur": "Code de sens pour le compte de la filiale : +1 entrée d'argent, -1 sortie.",
                             "genere_jambe_beneficiaire": "Vrai si l'opération crée aussi une écriture chez le bénéficiaire (virement interne)."},
    "dim_scenario_stress": {"code_scenario": "Code du scénario, clé primaire de la dimension."},
    "fct_flux_tresorerie_horaire": {
        "id_flux": "Identifiant de la ligne (empreinte des clés du grain).",
        "horodatage": "Heure pleine des opérations agrégées (heure locale).",
        "heure": "Heure de la journée (0 à 23).",
        "nb_mouvements": "Nombre d'opérations.",
        "encaissements_devise": "Entrées d'argent, en devise locale.",
        "decaissements_devise": "Sorties d'argent (montant positif), en devise locale.",
        "flux_net_devise": "Encaissements - décaissements, en devise locale.",
        "encaissements_eur": "Entrées d'argent, en euros au cours du jour.",
        "decaissements_eur": "Sorties d'argent (montant positif), en euros au cours du jour.",
        "flux_net_eur": "Encaissements - décaissements, en euros au cours du jour.",
    },
    "fct_position_tresorerie_quotidienne": {
        "id_position": "Identifiant de la ligne (jour, filiale).",
        "code_devise": "Devise de la filiale (clé vers dim_devise).",
        "nb_mouvements": "Nombre d'opérations du jour.",
        "encaissements_devise": "Entrées d'argent du jour, en devise locale.",
        "decaissements_devise": "Sorties d'argent du jour (positif), en devise locale.",
        "flux_net_devise": "Flux net du jour, en devise locale.",
        "encaissements_eur": "Entrées d'argent du jour, en euros.",
        "decaissements_eur": "Sorties d'argent du jour (positif), en euros.",
        "flux_net_eur": "Flux net du jour, en euros.",
        "decaissements_frauduleux_eur": "Part des décaissements du jour signalés comme suspects de fraude, en euros.",
        "decaissements_gros_tickets_eur": "Part des décaissements du jour faite d'opérations de plus de 10 000 EUR, en euros.",
        "cible_reserve_mois_devise": "Réserve cible du mois = taux de réserve x encours de fin du mois précédent (RG-POS-06).",
        "position_ouverture_devise": "Position de trésorerie en début de journée, en devise locale.",
        "position_cloture_devise": "Position de trésorerie en fin de journée, en devise locale.",
        "encours_depots_devise": "Encours de dépôts à vue en fin de journée = encours initial + cumul des flux (RG-POS-04).",
        "operation_tresorerie_devise": "Opération de fin de mois pour revenir à la cible : > 0 refinancement à lever, < 0 excédent à placer (RG-POS-07). Vide hors fin de mois.",
        "operation_tresorerie_eur": "Même opération de fin de mois, en euros.",
        "taux_eur_jour": "Cours BCE du jour utilisé pour la conversion (unités de devise pour 1 euro).",
        "position_cloture_eur": "Position de fin de journée en euros au cours du jour (RG-POS-05).",
        "position_cloture_eur_taux_constant": "Position de fin de journée en euros au cours du 01/01/2023 (sans effet de change).",
        "effet_change_eur": "Effet de change cumulé : position au cours du jour - position au cours de départ.",
        "encours_depots_eur": "Encours de dépôts en euros au cours du jour.",
        "ratio_reserve_sur_depots": "Position de clôture / encours de dépôts (0,15 = 15 %).",
        "encours_reel_publie_devise": "Encours réel publié ce jour-là par la banque centrale (x part de marché) ; vide les autres jours.",
        "est_date_publication": "Vrai si la banque centrale a publié les dépôts ce jour-là.",
    },
    "fct_situation_initiale_filiale": {
        "id_situation": "Identifiant de la ligne (filiale).",
        "date_situation": "Date de la situation de départ (31/12/2022).",
        "code_devise": "Devise de la filiale (clé vers dim_devise).",
        "taux_eur_reference": "Cours de départ utilisé pour la conversion (unités de devise pour 1 euro au 01/01/2023).",
        "encours_depots_initial_eur": "Encours de dépôts de départ, en euros au cours de départ.",
        "reserve_liquidite_initiale_eur": "Réserve de liquidité de départ, en euros au cours de départ.",
    },
    "fct_taux_change": {
        "id_taux": "Identifiant de la ligne (jour, devise).",
        "valeur_eur_par_unite": "Valeur en euros d'une unité de devise (1 / taux_eur).",
        "est_taux_publie": "Vrai si la BCE a publié un cours ce jour-là (faux : cours du dernier jour publié reporté).",
        "jours_depuis_publication": "Nombre de jours depuis le dernier cours publié.",
        "variation_jour_pct": "Variation du cours par rapport au jour publié précédent.",
        "volatilite_quotidienne": "Écart-type des variations quotidiennes sur les 60 dernières cotations (0,003 = 0,3 %).",
        "est_rupture_serie": "Vrai si le cours n'est plus publié (cas du rouble depuis le 01/03/2022).",
    },
    "mart_exposition_change": {
        "id_exposition": "Identifiant de la ligne (jour, devise).",
        "position_devise": "Trésorerie détenue dans la devise par l'ensemble des filiales, en devise.",
        "exposition_eur": "Contre-valeur en euros de cette trésorerie : montant exposé au change (RG-RIS-02).",
        "effet_change_eur": "Effet de change cumulé depuis le 01/01/2023 sur cette devise.",
        "part_position_groupe_pct": "Part de l'exposition dans la trésorerie totale du groupe.",
        "taux_eur": "Cours du jour (unités de devise pour 1 euro).",
        "var_95_1j_eur": "Perte de change qui ne sera pas dépassée dans 95 % des cas sur 1 jour (RG-RIS-03).",
        "var_95_10j_eur": "Perte de change qui ne sera pas dépassée dans 95 % des cas sur 10 jours = VaR 1 jour x racine de 10.",
        "cout_couverture_annuel_pct": "Coût annuel d'une couverture de change = écart entre le taux directeur local et celui de l'euro (négatif : la couverture rapporte).",
        "cout_couverture_annuel_eur": "Coût annuel de la couverture de toute l'exposition, en euros.",
        "rapport_cout_risque": "Coût de couverture / volatilité annuelle : plus il est bas, plus la couverture est intéressante (RG-COU-02).",
        "recommandation_couverture": "Décision proposée : À couvrir, Prioritaire, À arbitrer, Inutile ou Parité fixe.",
    },
    "mart_liquidite_placement": {
        "id_liquidite": "Identifiant de la ligne (jour, filiale).",
        "position_cloture_eur": "Position de trésorerie de fin de journée, en euros.",
        "encours_depots_eur": "Encours de dépôts de fin de journée, en euros.",
        "flux_net_moyen_eur": "Flux net quotidien moyen sur les 30 derniers jours, en euros.",
        "consommation_quotidienne_pct": "Part de la position consommée chaque jour en moyenne (RG-LIQ-05).",
        "besoin_liquidite_30j_eur": "Besoin de liquidité à 30 jours = 10 % des dépôts (fuite Bâle III simplifiée, RG-LIQ-01).",
        "cible_pilotage_eur": "Cible de pilotage = besoin à 30 jours x 110 %.",
        "ratio_couverture_liquidite_pct": "Ratio de liquidité (LCR simplifié) = position / besoin à 30 jours ; minimum réglementaire 100 % (RG-LIQ-02).",
        "jours_avant_seuil_100pct": "Jours avant de passer sous 100 % au rythme actuel ; 0 si déjà dessous ; vide si la position ne baisse pas (RG-LIQ-06).",
        "liquidite_excedentaire_eur": "Liquidité au-dessus de la cible de pilotage, plaçable (RG-LIQ-03).",
        "besoin_refinancement_eur": "Liquidité manquante sous la cible de pilotage, à emprunter (RG-LIQ-04).",
        "taux_directeur_local_pct": "Taux directeur de la banque centrale de la filiale ce jour-là.",
        "taux_directeur_eur_pct": "Taux de dépôt de la BCE ce jour-là.",
        "gain_placement_annuel_eur": "Gain annuel si la liquidité excédentaire est placée au taux directeur local.",
        "cout_refinancement_annuel_eur": "Coût annuel du refinancement = besoin x (taux directeur + marge de 0,5 point).",
        "economie_anticipation_annuelle_eur": "Économie annuelle d'un refinancement préparé plutôt qu'en urgence (0,25 point d'écart).",
        "cout_couverture_change_annuel_eur": "Coût annuel de couverture de change de la position (0 pour l'euro et les francs CFA).",
    },
    "mart_qualite_sources": {
        "id_qualite_source": "Identifiant de la ligne (système, filiale, mois).",
        "nb_lignes_brutes": "Lignes reçues dans les exports.",
        "nb_lignes_retenues": "Lignes conservées après nettoyage.",
        "nb_doublons": "Lignes écartées comme doublons (RG-NET-07).",
        "nb_annulees": "Opérations annulées écartées (RG-NET-08).",
        "nb_comptes_test": "Lignes de comptes de test écartées (RG-NET-08).",
        "nb_extournes": "Extournes et écritures extournées écartées (RG-NET-08).",
        "nb_rejets_inattendus": "Rejets non prévus (libellé inconnu, devise ou sens incohérent) : 0 attendu.",
        "nb_libelles_corriges": "Libellés non standard ramenés à un type connu (RG-NET-05).",
        "nb_devises_corrigees": "Devises non ISO corrigées (RG-NET-06).",
        "nb_clients_manquants": "Identifiants client absents ou codés nuls (RG-NET-09).",
        "nb_heures_converties_utc": "Heures converties d'UTC en heure locale (RG-NET-03).",
        "nb_montants_unites_mineures": "Montants en öre divisés par 100.",
        "nb_indicateurs_fraude_vides": "Indicateurs de fraude vides traités comme non suspects (RG-NET-11).",
        "taux_rejet_pct": "Lignes écartées / lignes reçues.",
    },
    "mart_qualite_defauts": {
        "id_defaut": "Identifiant de la ligne (système, filiale, mois, défaut).",
        "type_defaut": "Type de défaut détecté (doublon, format, devise non ISO, libellé, client manquant…).",
        "traitement": "Ligne écartée (avec motif de rejet) ou Valeur corrigée (ligne conservée).",
        "nb_lignes": "Nombre de lignes concernées par le défaut.",
    },
    "mart_qualite_ancrage": {
        "id_ancrage": "Identifiant de la ligne (filiale, date publiée).",
        "date_ancrage": "Date publiée par la banque centrale (clé vers dim_date).",
        "source_depots": "Publication d'où vient l'encours réel de cette date (traçabilité de la mesure).",
        "est_interpole": "Vrai si l'encours réel a été interpolé (mois non publié, Cameroun).",
        "encours_reel_devise": "Encours réel publié x part de marché, en devise locale.",
        "encours_reconstitue_devise": "Encours reconstitué par cumul des flux nettoyés, en devise locale.",
        "ecart_devise": "Encours reconstitué - encours réel, en devise locale (0 attendu).",
        "ecart_pct": "Écart en % de l'encours réel (0 attendu).",
        "encours_reconstitue_eur": "Encours reconstitué en euros au cours du jour.",
    },
    "mart_stress_test": {
        "id_stress": "Identifiant de la ligne (scénario, filiale).",
        "choc_change_pct": "Choc de change appliqué à la devise de la filiale dans ce scénario (0 pour l'euro).",
        "position_avant_choc_eur": "Position de trésorerie à la date d'arrêté, avant choc.",
        "impact_change_eur": "Variation de la position due au choc de change.",
        "impact_retraits_eur": "Variation de la position due aux retraits massifs (négative).",
        "position_stressee_eur": "Position après les chocs de change et de retraits.",
        "flux_net_quotidien_stresse_eur": "Flux net quotidien moyen (30 jours) après le multiplicateur de sorties et le choc de change.",
        "horizon_survie_jours": "Jours avant épuisement de la position au rythme stressé ; vide si la position ne baisse pas.",
        "besoin_refinancement_eur": "Liquidité à trouver pour couvrir 30 jours de sorties stressées.",
        "cout_refinancement_annuel_eur": "Coût annuel de ce refinancement = besoin x (taux directeur + marge + choc de taux).",
        "statut_resilience": "1 - Résilient (30 jours ou plus), 2 - Vigilance (7 à 30 jours), 3 - Critique (moins de 7 jours).",
    },
    "mart_prevision_tresorerie": {
        "id_prevision": "Identifiant de la ligne (jour, filiale, nature).",
        "position_p50_devise": "Position prévue, milieu de la fourchette (P50), en devise ; position réelle pour le passé.",
        "position_p05_devise": "Position prévue, bas de la fourchette (P5), en devise.",
        "position_p95_devise": "Position prévue, haut de la fourchette (P95), en devise.",
        "position_p50_eur": "Position prévue (P50) en euros au cours de la date d'arrêté (change constant, RG-PRV-01).",
        "position_p05_eur": "Position prévue (P5) en euros, change constant.",
        "position_p95_eur": "Position prévue (P95) en euros, change constant.",
        "flux_net_p50_eur": "Flux net du jour, prévu (P50) ou réel, en euros.",
    },
    "mart_prevision_change": {
        "id_prevision_change": "Identifiant de la ligne (jour, devise, nature).",
        "taux_p50": "Cours prévu, milieu de la fourchette (P50) ; cours réel pour l'historique.",
        "taux_realise": "Cours réellement observé ce jour-là (vide s'il n'est pas encore connu).",
        "realise_dans_intervalle_90": "Vrai si le cours réel est resté dans la fourchette P5-P95.",
    },
    "mart_controle_a_posteriori": {
        "id_controle": "Identifiant de la ligne (filiale).",
        "dans_la_fourchette": "Oui si les dépôts réels tombent dans la fourchette P5-P95 prévue, sinon Non.",
        "source": "Source des dépôts réels publiés.",
    },
    "mart_reserve_optimale": {
        "id_reserve": "Identifiant de la ligne (filiale).",
        "encours_depots_devise": "Encours de dépôts à la date d'arrêté, en devise locale.",
        "ecart_reserve_pts": "Réserve actuelle - réserve requise, en points de % (> 0 : sur-réserve).",
        "diagnostic": "Sur-réserve : liquidité à placer, ou Réserve insuffisante : liquidité à lever.",
    },
    "mart_backtest_journalier": {
        "id_backtest": "Identifiant de la ligne (origine, filiale, série, modèle, jour).",
        "reel_devise": "Montant réel du jour, en devise locale.",
        "prevu_devise": "Montant prévu par le modèle, en devise locale.",
        "reel_eur": "Montant réel du jour, en euros (sert au WAPE du groupe).",
        "prevu_eur": "Montant prévu, en euros.",
    },
    # ---- ml
    "backtest_prevision": {"reel": "Montant réel du jour, en devise locale.", "prevu": "Montant prévu, en devise locale."},
    "controle_depots_reels": {"source": "Source des dépôts réels publiés."},
    "prevision_change": {
        "taux_depart": "Cours à la date d'arrêté, point de départ de la simulation.",
        "volatilite_annuelle_pct": "Volatilité annuelle utilisée pour la simulation (250 dernières cotations).",
        "methode": "Méthode de simulation utilisée.",
    },
    "prevision_tresorerie_quotidienne": {
        "flux_net_p05_devise": "Flux net prévu, bas de la fourchette (P5), en devise.",
        "flux_net_p50_devise": "Flux net prévu, milieu (P50), en devise.",
        "flux_net_p95_devise": "Flux net prévu, haut de la fourchette (P95), en devise.",
        "position_p05_devise": "Position prévue, bas de la fourchette (P5), en devise.",
        "position_p50_devise": "Position prévue, milieu (P50), en devise.",
        "position_p95_devise": "Position prévue, haut de la fourchette (P95), en devise.",
        "modele_encaissements": "Modèle champion retenu pour les encaissements.",
        "modele_decaissements": "Modèle champion retenu pour les décaissements.",
        "methode_simulation": "Méthode de simulation (Monte-Carlo par blocs d'erreurs + choc mensuel).",
    },
    "reserve_optimale": {"encours_depots_devise": "Encours de dépôts à la date d'arrêté, en devise locale."},
    # ---- référentiels
    "ref_correspondance_devises": {
        "valeur_normalisee": "Écriture de devise rencontrée dans les exports, normalisée (ex. €, FCFA, F CFA).",
        "est_code_iso": "Vrai si l'écriture est déjà le code ISO.",
    },
    "ref_correspondance_libelles": {
        "est_libelle_officiel": "Vrai si le libellé est la forme officielle du système (sinon variante corrigée).",
    },
    "ref_taux_directeurs": {
        "libelle_taux": "Nom du taux directeur (ex. taux de la facilité de dépôt de la BCE).",
        "date_effet": "Date d'entrée en vigueur du taux.",
        "a_verifier": "Vrai si la valeur est déduite et reste à confirmer (BCEAO, décembre 2022).",
    },
    "ref_types_transaction": {
        "sens_jambe_emetteur": "Sens pour le compte de la filiale : +1 entrée d'argent, -1 sortie.",
        "genere_jambe_beneficiaire": "Vrai si l'opération crée aussi une écriture chez le bénéficiaire.",
    },
    # ---- raw
    "src_sab": {
        "ref_ope": "Référence d'opération, parfois avec espaces de bord.", "code_etab": "Code de l'entité (ZF-FR, ZF-BE, ZF-FI).",
        "date_ope": "Date jj/mm/aaaa, puis aaaa-mm-jj après la migration de juillet 2024.", "heure_ope": "Heure hh:mm:ss.",
        "num_client": "Identifiant client, parfois vide ou codé NULL, N/A, ?, 0000000.",
        "libelle_ope": "Libellé libre en français, avec variantes.", "nb_ope": "Nombre d'opérations du lot.",
        "montant": "Montant positif, virgule décimale, parfois espace insécable (fichiers retouchés sous Excel).",
        "sens": "C crédit (entrée) ou D débit (sortie).", "devise": "Devise non normalisée (EUR, €, eur…).",
        "ind_fraude": "O ou N.", "statut": "VALIDE ou ANNULE.",
    },
    "src_nordic": {
        "txn_id": "Référence d'opération.", "entity": "Code entité, casse variable (SE01, se01…).",
        "booking_ts": "Horodatage ISO 8601 en UTC.", "customer_ref": "Identifiant client.",
        "txn_type": "Code anglais du type d'opération, casse variable.", "txn_count": "Nombre d'opérations du lot.",
        "amount": "Montant signé.", "amount_unit": "MINOR si le montant est en öre (Suède), sinon vide.",
        "currency_code": "Devise non normalisée.", "fraud_flag": "Indicateur de fraude.",
        "record_status": "BOOKED, REVERSAL ou PENDING (pré-autorisation carte).",
        "reversal_of": "Référence de l'écriture extournée.",
        "channel": "Canal (CARD, ATM, BATCH, ONLINE, BRANCH), colonne apparue en janvier 2025 (dérive de schéma).",
    },
    "src_americore": {
        "txnref": "Référence d'opération.", "entity": "Code entité, casse variable.",
        "txndate": "Date MM/JJ/AAAA.", "txntime": "Heure hh:mm:ss AM/PM.",
        "accountno": "Numéro de compte (zéros de tête parfois perdus, comptes TEST-…).",
        "txncode": "Code numérique du type (100 dépôt, 200 retrait, 210 carte…).", "description": "Libellé.",
        "itemcount": "Nombre d'opérations du lot.",
        "debitamount": "Montant au débit (séparateur de milliers, format comptable (…), symbole US$ / C$).",
        "creditamount": "Montant au crédit (mêmes formats).", "currency": "Devise non normalisée.",
        "fraudflag": "Indicateur de fraude.",
    },
    "src_delta": {
        "numope": "Référence d'opération.", "dateope": "Date aaaammjj.", "heureope": "Heure hhmmss.",
        "client": "Identifiant client.", "nature": "Libellé sans norme (accents, abréviations, encodage cassé).",
        "nbope": "Nombre d'opérations du lot.", "montant": "Montant entier positif (sens déduit de la nature).",
        "devise": "XOF, XAF, FCFA, F CFA, F.CFA.", "suspicion": "1, 0 ou vide.",
    },
    "soldes_comptables": {
        "date_comptable": "Jour comptable.", "total_credits": "Total des crédits du jour au grand livre, en devise.",
        "total_debits": "Total des débits du jour au grand livre, en devise.",
        "nb_operations": "Nombre d'opérations du jour au grand livre.",
    },
    "ancrages_zf": {
        "encours_zf_devise": "Dépôts réels du pays x part de marché de ZF Banque, en devise.",
        "est_point_initial": "Vrai pour le point de départ du 31/12/2022.",
        "est_interpole": "Vrai si la valeur a été interpolée (mois non publié).",
    },
    "bce_taux_change": {"taux": "Cours de référence BCE (unités de devise pour 1 euro)."},
    "journal_chargement": {
        "empreinte_md5": "Empreinte MD5 du fichier : un fichier inchangé n'est pas rechargé.",
        "nb_lignes_lues": "Lignes de données lues dans le fichier.",
        "nb_lignes_annoncees": "Lignes annoncées par le pied de fichier (DELTA).",
        "total_annonce": "Total des montants annoncé par le pied de fichier (DELTA).",
        "ligne_titre": "Ligne de titre du fichier (DELTA).",
        "date_chargement": "Date et heure du chargement.",
    },
    # ---- staging / intermediate
    "stg_bce__taux_change": {"source_taux": "Source du cours (Webstat ou fichier historique BCE)."},
    "stg_zf__ancrages": {
        "encours_zf_devise": "Dépôts réels du pays x part de marché de ZF Banque, en devise.",
        "est_point_initial": "Vrai pour le point de départ du 31/12/2022.",
        "est_interpole": "Vrai si la valeur a été interpolée.",
    },
    "int_operations_controlees": {
        "est_libelle_standard": "Vrai si le libellé reçu était déjà la forme officielle.",
        "sens_attendu": "Sens attendu pour le type d'opération (+1 / -1), pour contrôler la cohérence.",
        "devise_filiale": "Devise de la filiale, pour contrôler la devise reçue.",
        "est_devise_standard": "Vrai si la devise reçue était déjà le code ISO.",
        "est_client_manquant": "Vrai si l'identifiant client était absent ou codé nul.",
        "est_ecriture_extournee": "Vrai si l'écriture a été annulée par une extourne.",
        "rang_occurrence": "Rang de la ligne parmi celles de même référence (1 = gardée, > 1 = doublon).",
        "est_doublon": "Vrai si la ligne est un doublon (RG-NET-07).",
    },
    "int_mouvements_tresorerie": {"sens": "Sens de trésorerie : +1 entrée, -1 sortie (RG-SEN-01)."},
    "int_taux_change_journalier": {
        "id_groupe_publication": "Numéro du dernier cours publié (sert au report des week-ends et jours fériés).",
        "est_taux_publie": "Vrai si la BCE a publié un cours ce jour-là.",
        "jours_depuis_publication": "Nombre de jours depuis le dernier cours publié.",
    },
    "int_encours_initial": {"taux_reference": "Cours au 01/01/2023 (unités de devise pour 1 euro)."},
}
