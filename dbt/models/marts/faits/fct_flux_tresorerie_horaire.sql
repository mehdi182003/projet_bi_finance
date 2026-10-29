{{ config(
    materialized='incremental',
    unique_key='id_flux',
    incremental_strategy='delete+insert',
    on_schema_change='append_new_columns'
) }}
-- Fait principal : flux de trésorerie agrégés à l'heure x filiale x type d'opération.
--   Grain        : 1 ligne = 1 heure x 1 filiale x 1 type d'opération x (fraude oui/non) x (gros ticket oui/non)
--   Mesures      : additives (montants, nombre d'opérations) sur toutes les dimensions
--   Chargement   : INCRÉMENTAL. Seuls les jours récents (fenêtre de 35 jours, pour absorber les fichiers
--                  arrivés en retard ou renvoyés) sont recalculés et remplacent les lignes existantes
--                  (delete + insert sur id_flux) => idempotent. Reconstruction complète : dbt build --full-refresh.

select
    md5(concat_ws('|', heure_operation, code_filiale, code_type, est_fraude, est_gros_ticket)) as id_flux,
    heure_operation                                                           as horodatage,
    date_operation,
    extract(hour from heure_operation)::int                                  as heure,
    code_filiale,
    code_devise,
    code_type,
    est_fraude,
    est_gros_ticket,
    sum(nb_operations)                                                        as nb_mouvements,
    sum(case when sens > 0 then montant_devise else 0 end)                    as encaissements_devise,
    sum(case when sens < 0 then montant_devise else 0 end)                    as decaissements_devise,
    sum(sens * montant_devise)                                                as flux_net_devise,
    sum(case when sens > 0 then montant_eur else 0 end)                       as encaissements_eur,
    sum(case when sens < 0 then montant_eur else 0 end)                       as decaissements_eur,
    sum(sens * montant_eur)                                                   as flux_net_eur
from {{ ref('int_mouvements_tresorerie') }}
{% if is_incremental() %}
where date_operation >= (select max(date_operation) - 35 from {{ this }})
{% endif %}
group by heure_operation, date_operation, code_filiale, code_devise, code_type, est_fraude, est_gros_ticket
