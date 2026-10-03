{{ config(tags=['prevision']) }}
-- Historique réalisé + projection Monte-Carlo de la position de trésorerie (graphique « cône »).
--   RG-PRV-01 : la projection est convertie en EUR au taux de la date d'arrêté (change constant),
--               pour isoler le risque de liquidité du risque de change.

with realise as (
    select
        date_position                      as date_jour,
        code_filiale,
        code_devise,
        'Réalisé'                          as type_valeur,
        position_cloture_devise            as position_p50_devise,
        position_cloture_devise            as position_p05_devise,
        position_cloture_devise            as position_p95_devise,
        position_cloture_eur               as position_p50_eur,
        position_cloture_eur               as position_p05_eur,
        position_cloture_eur               as position_p95_eur,
        flux_net_eur                       as flux_net_p50_eur,
        cast(null as double precision)     as proba_sous_besoin_liquidite
    from {{ ref('fct_position_tresorerie_quotidienne') }}
),

taux_arrete as (
    select code_filiale, taux_eur_jour
    from {{ ref('fct_position_tresorerie_quotidienne') }}
    where date_position = (select max(date_position) from {{ ref('fct_position_tresorerie_quotidienne') }})
),

prevision as (
    select
        p.date_prevision                   as date_jour,
        p.code_filiale,
        p.code_devise,
        'Prévision'                        as type_valeur,
        p.position_p50_devise,
        p.position_p05_devise,
        p.position_p95_devise,
        p.position_p50_devise / t.taux_eur_jour,
        p.position_p05_devise / t.taux_eur_jour,
        p.position_p95_devise / t.taux_eur_jour,
        p.flux_net_p50_devise / t.taux_eur_jour,
        p.proba_sous_besoin_liquidite
    from {{ source('ml', 'prevision_tresorerie_quotidienne') }} p
    join taux_arrete t on t.code_filiale = p.code_filiale
)

select md5(concat_ws('|', date_jour, code_filiale, type_valeur)) as id_prevision, *
from (
    select * from realise
    union all
    select * from prevision
) u
