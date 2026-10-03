{{ config(tags=['prevision']) }}
-- Fourchette de prévision des taux de change + comparaison a posteriori avec le réalisé
-- (quand la période prévue est déjà connue, on vérifie si le taux est resté dans l'intervalle).

with historique as (
    select date_cours as date_jour, code_devise, 'Historique' as type_valeur,
           taux_eur as taux_p50, taux_eur as taux_p05, taux_eur as taux_p95,
           taux_eur as taux_realise
    from {{ ref('fct_taux_change') }}
    where regime_change = 'flottant'
      and taux_eur is not null
      and date_cours <= (select max(date_arrete) from {{ source('ml', 'prevision_change') }})
      and date_cours >  (select max(date_arrete) from {{ source('ml', 'prevision_change') }}) - 180
),

prevision as (
    select p.date_prevision as date_jour, p.code_devise, 'Prévision' as type_valeur,
           p.taux_p50, p.taux_p05, p.taux_p95,
           r.taux_eur as taux_realise
    from {{ source('ml', 'prevision_change') }} p
    left join {{ ref('fct_taux_change') }} r
        on r.code_devise = p.code_devise and r.date_cours = p.date_prevision and r.est_taux_publie
)

select
    md5(concat_ws('|', date_jour, code_devise, type_valeur)) as id_prevision_change,
    u.*,
    case when type_valeur = 'Prévision' and taux_realise is not null
         then taux_realise between taux_p05 and taux_p95 end as realise_dans_intervalle_90
from (
    select * from historique
    union all
    select * from prevision
) u
