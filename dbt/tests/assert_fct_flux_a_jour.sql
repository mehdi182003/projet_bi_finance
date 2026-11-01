-- FRAÎCHEUR DU FAIT INCRÉMENTAL : fct_flux_tresorerie_horaire ne recalcule que ses 35 derniers jours.
-- Si des données plus anciennes changent (régénération, changement de jeu de données), il faut le
-- reconstruire (python pipeline.py --etapes dbt --full-refresh) : sinon les tableaux de bord afficheraient
-- d'anciens flux alors que tous les autres contrôles, calculés en amont, resteraient verts.
with source as (
    select date_operation, code_filiale, sum(nb_operations) as nb_operations, sum(sens * montant_eur) as flux_net_eur
    from {{ ref('int_mouvements_tresorerie') }}
    group by 1, 2
),
fait as (
    select date_operation, code_filiale, sum(nb_mouvements) as nb_operations, sum(flux_net_eur) as flux_net_eur
    from {{ ref('fct_flux_tresorerie_horaire') }}
    group by 1, 2
)
select date_operation, code_filiale,
       s.nb_operations as nb_source, f.nb_operations as nb_fait,
       s.flux_net_eur as flux_source, f.flux_net_eur as flux_fait
from source s
full outer join fait f using (date_operation, code_filiale)
where s.code_filiale is null or f.code_filiale is null
   or s.nb_operations <> f.nb_operations
   or abs(s.flux_net_eur - f.flux_net_eur) > 1
