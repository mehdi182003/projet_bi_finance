-- Système NORDIC (Suède, Danemark, Norvège) : typage et normalisation du format, AUCUNE suppression.
--   RG-NET-03 : horodatage ISO 8601 en UTC -> heure locale de la filiale (fuseau de ref_filiales)
--   RG-NET-04 : montant signé (négatif = sortie) ; amount_unit = MINOR => montant en centimes (öre) / 100
--   RG-NET-01 : code entité saisi en minuscules ou avec espaces -> majuscules sans espaces de bord
--   Les extournes (REVERSAL), les écritures qu'elles annulent et les pré-autorisations carte (PENDING)
--   sont écartées en couche intermediate. La colonne « channel » (exports depuis 2025) n'est pas utilisée.
with source as (
    select * from {{ source('raw', 'src_nordic') }}
),

filiales as (
    select code_filiale, code_entite_source, fuseau_horaire from {{ ref('ref_filiales') }} where systeme_source = 'NORDIC'
),

typee as (
    select
        s.*,
        f.code_filiale,
        f.fuseau_horaire,
        nullif(trim(s.amount), '')::numeric
            / case when upper(trim(s.amount_unit)) = 'MINOR' then 100 else 1 end as montant_signe
    from source s
    left join filiales f on f.code_entite_source = upper(trim(s.entity))
)

select
    'NORDIC'                                                               as systeme_source,
    _fichier                                                               as nom_fichier,
    _ligne                                                                 as num_ligne,
    trim(txn_id)                                                           as ref_operation,
    code_filiale,
    (cast(booking_ts as timestamptz) at time zone fuseau_horaire)          as horodatage,
    txn_type                                                               as libelle_source,
    {{ normaliser_libelle('txn_type') }}                                   as libelle_normalise,
    nullif(trim(txn_count), '')::integer                                   as nb_operations,
    abs(montant_signe)::numeric(18, 2)                                     as montant_unitaire_devise,
    sign(montant_signe)::integer                                           as sens_source,
    currency_code                                                          as devise_source,
    customer_ref                                                           as client_source,
    lower(trim(fraud_flag)) = 'true'                                       as est_fraude,
    upper(trim(record_status))                                             as statut_source,
    nullif(trim(reversal_of), '')                                          as reference_extournee,
    false                                                                  as est_compte_test,
    true                                                                   as est_heure_convertie_utc,
    upper(trim(amount_unit)) = 'MINOR'                                     as est_montant_unites_mineures,
    entity <> upper(trim(entity))                                          as est_format_corrige
from typee
