-- Nettoyage technique des logs PaySim : renommage en français, typage,
-- conversion du step (heure de simulation) en date/heure réelle.
-- Toutes les lignes sont conservées ; le drapeau est_periode_analyse (RG-QUA-02)
-- est appliqué dans la couche intermediate.

with source as (
    select * from {{ source('raw', 'paysim_transactions') }}
)

select
    id_ligne                                   as id_transaction,
    step                                       as step_heure,
    (step - 1) / 24 + 1                        as jour_simulation,
    step between {{ var('step_debut_analyse') }} and {{ var('step_fin_analyse') }} as est_periode_analyse,
    {{ heure_paysim('step') }}                 as horodatage,
    cast({{ heure_paysim('step') }} as date)   as date_operation,
    upper(trim(type))                          as code_type,
    amount                                     as montant_paysim,
    trim(name_orig)                            as id_client_emetteur,
    old_balance_orig                           as solde_avant_emetteur,
    new_balance_orig                           as solde_apres_emetteur,
    trim(name_dest)                            as id_beneficiaire,
    case when name_dest like 'M%' then 'COMMERCANT' else 'CLIENT' end as type_beneficiaire,
    old_balance_dest                           as solde_avant_beneficiaire,
    new_balance_dest                           as solde_apres_beneficiaire,
    is_fraud = 1                               as est_fraude,
    is_flagged_fraud = 1                       as est_signalee_fraude
from source
where step is not null
  and amount is not null
