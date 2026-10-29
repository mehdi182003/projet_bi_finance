-- Flux de ZF Banque 2023-2025 (générés par etl/generateur_flux.py, ancrés sur les dépôts réels).
-- Une ligne représente `poids` opérations de même montant unitaire (échantillon pondéré).

with source as (
    select * from {{ source('raw', 'transactions_zf') }}
)

select

    horodatage,
    cast(horodatage as date)                                           as date_operation,
    date_trunc('hour', horodatage)                                     as heure_operation,
    upper(trim(code_filiale))                                          as code_filiale,
    upper(trim(code_type))                                             as code_type,
    montant_devise                                                     as montant_unitaire_devise,
    poids                                                              as nb_operations,
    montant_devise * poids                                             as montant_devise,
    id_client,
    est_fraude = 1                                                     as est_fraude
from source
where montant_devise is not null
