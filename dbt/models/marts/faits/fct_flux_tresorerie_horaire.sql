-- Fait principal : flux de trésorerie agrégés à l'heure x filiale x type d'opération.
-- 3 ans (2023-2025) au grain horaire : quelques centaines de milliers de lignes, import Power BI rapide.

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
group by heure_operation, date_operation, code_filiale, code_devise, code_type, est_fraude, est_gros_ticket
