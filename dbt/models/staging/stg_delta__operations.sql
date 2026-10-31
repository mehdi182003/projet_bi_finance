-- Système DELTA (Côte d'Ivoire, Cameroun) : typage et normalisation du format, AUCUNE suppression.
--   La filiale n'est pas une colonne : elle est lue dans le nom du fichier (DELTA_<entité>_<aaaamm>).
--   RG-NET-02 : date aaaammjj + heure hhmmss -> horodatage
--   RG-NET-04 : montants entiers (le franc CFA n'a pas de centimes), toujours positifs ; le sens est
--               déduit de la nature d'opération (couche intermediate)
--   RG-NET-11 : indicateur de suspicion vide => non suspect (et compté comme valeur manquante)
--   RG-NET-05 : libellés à l'encodage cassé (UTF-8 relu en cp1252 : « DÃ‰PÃ”T ») reconnus par la table
--               de correspondance ; l'en-tête répété à chaque page de l'état est écarté au chargement
with source as (
    select * from {{ source('raw', 'src_delta') }}
),

filiales as (
    select code_filiale, code_entite_source from {{ ref('ref_filiales') }} where systeme_source = 'DELTA'
)

select
    'DELTA'                                                                as systeme_source,
    s._fichier                                                             as nom_fichier,
    s._ligne                                                               as num_ligne,
    trim(s.numope)                                                         as ref_operation,
    f.code_filiale,
    to_timestamp(trim(s.dateope) || lpad(trim(s.heureope), 6, '0'), 'YYYYMMDDHH24MISS')::timestamp as horodatage,
    s.nature                                                               as libelle_source,
    {{ normaliser_libelle('s.nature') }}                                   as libelle_normalise,
    nullif(trim(s.nbope), '')::integer                                     as nb_operations,
    nullif(trim(s.montant), '')::numeric(18, 2)                            as montant_unitaire_devise,
    cast(null as integer)                                                  as sens_source,
    s.devise                                                               as devise_source,
    s.client                                                               as client_source,
    coalesce(trim(s.suspicion) = '1', false)                               as est_fraude,
    -- un champ vide arrive en NULL dans la zone raw (COPY CSV) : on teste les deux cas
    case when coalesce(trim(s.suspicion), '') = '' then 'SUSPICION_VIDE' end as statut_source,
    cast(null as text)                                                     as reference_extournee,
    false                                                                  as est_compte_test,
    false                                                                  as est_heure_convertie_utc,
    false                                                                  as est_montant_unites_mineures,
    s.nature like '%Ã%'                                                    as est_format_corrige
from source s
left join filiales f on f.code_entite_source = substring(s._fichier from 'DELTA_([A-Z0-9]+)_')
