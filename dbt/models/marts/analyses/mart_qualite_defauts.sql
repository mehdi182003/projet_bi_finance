-- Catalogue des défauts des exports des filiales, en format long (système, filiale, mois, type de défaut) :
-- lignes écartées par motif de rejet, et valeurs corrigées sur les lignes conservées (libellés, devises,
-- clients, formats). Complète mart_qualite_sources pour la gouvernance des données.
with controlees as (
    select
        systeme_source,
        code_filiale,
        cast(date_trunc('month', horodatage) as date) as mois,
        motif_rejet,
        est_libelle_standard,
        est_devise_standard,
        est_client_manquant,
        est_format_corrige,
        statut_source
    from {{ ref('int_operations_controlees') }}
),

defauts as (
    select systeme_source, code_filiale, mois, motif_rejet as type_defaut, 'Ligne écartée' as traitement, count(*) as nb_lignes
    from controlees where motif_rejet is not null group by 1, 2, 3, 4
    union all
    select systeme_source, code_filiale, mois, 'Libellé non standard', 'Valeur corrigée', count(*)
    from controlees where motif_rejet is null and not est_libelle_standard group by 1, 2, 3
    union all
    select systeme_source, code_filiale, mois, 'Devise non standard', 'Valeur corrigée', count(*)
    from controlees where motif_rejet is null and not est_devise_standard group by 1, 2, 3
    union all
    select systeme_source, code_filiale, mois, 'Client manquant ou codé nul', 'Valeur corrigée', count(*)
    from controlees where motif_rejet is null and est_client_manquant group by 1, 2, 3
    union all
    select systeme_source, code_filiale, mois, 'Format non standard (date, montant, entité, encodage)', 'Valeur corrigée', count(*)
    from controlees where motif_rejet is null and est_format_corrige group by 1, 2, 3
    union all
    select systeme_source, code_filiale, mois, 'Indicateur de fraude vide', 'Valeur corrigée', count(*)
    from controlees where motif_rejet is null and statut_source = 'SUSPICION_VIDE' group by 1, 2, 3
)

select
    md5(concat_ws('|', systeme_source, code_filiale, mois, type_defaut)) as id_defaut,
    systeme_source,
    code_filiale,
    mois,
    type_defaut,
    traitement,
    nb_lignes
from defauts
