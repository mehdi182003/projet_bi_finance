-- Fait principal : flux de trésorerie agrégés à l'heure x filiale x type d'opération.
-- Grain réduit (quelques dizaines de milliers de lignes au lieu de 6,8 M de jambes)
-- => import Power BI rapide, sans perte d'information utile au pilotage.

select
    md5(concat_ws('|', horodatage, code_filiale, code_type, role_jambe, est_intragroupe, est_fraude, est_gros_ticket)) as id_flux,
    horodatage,
    date_operation,
    extract(hour from horodatage)::int                                       as heure,
    code_filiale,
    code_devise,
    code_type,
    role_jambe,
    est_intragroupe,
    est_fraude,
    est_gros_ticket,
    count(*)                                                                  as nb_mouvements,
    sum(case when sens > 0 then montant_devise else 0 end)                    as encaissements_devise,
    sum(case when sens < 0 then montant_devise else 0 end)                    as decaissements_devise,
    sum(sens * montant_devise)                                                as flux_net_devise,
    sum(case when sens > 0 then montant_eur else 0 end)                       as encaissements_eur,
    sum(case when sens < 0 then montant_eur else 0 end)                       as decaissements_eur,
    sum(sens * montant_eur)                                                   as flux_net_eur
from {{ ref('int_mouvements_tresorerie') }}
group by horodatage, date_operation, code_filiale, code_devise, code_type, role_jambe, est_intragroupe, est_fraude, est_gros_ticket
