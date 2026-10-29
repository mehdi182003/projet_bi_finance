-- Complétude : chaque ligne de flux non nulle se retrouve valorisée dans les mouvements
-- (aucune perte lors des jointures filiale / type / taux de change).
with attendu as (
    select count(*) as nb, sum(nb_operations) as ops
    from {{ ref('stg_zf__transactions') }}
    where montant_unitaire_devise > 0
),
obtenu as (
    select count(*) as nb, sum(nb_operations) as ops
    from {{ ref('int_mouvements_tresorerie') }}
)
select a.nb as attendu, o.nb as obtenu
from attendu a, obtenu o
where a.nb <> o.nb or a.ops <> o.ops
