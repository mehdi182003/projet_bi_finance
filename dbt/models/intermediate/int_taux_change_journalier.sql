{{ config(materialized='table') }}
-- Grille quotidienne complète (y compris week-ends et jours fériés) des taux EUR -> devise.
-- Règles de gestion :
--   RG-CHG-01 : EUR = 1 (devise de consolidation).
--   RG-CHG-02 : XOF / XAF = parité fixe 655,957 (non cotés par la BCE).
--   RG-CHG-03 : un jour sans cotation reprend le dernier cours publié (report),
--               dans la limite de var('jours_report_max_taux') jours.
--   RG-CHG-04 : au-delà, le taux est laissé à NULL => rupture de série détectée (cas du RUB).

with devises as (
    select code_devise, regime_change, parite_fixe_par_eur
    from {{ ref('ref_devises') }}
),

cotations as (
    select date_cours, code_devise, taux_eur
    from {{ ref('stg_bce__taux_change') }}
),

bornes as (
    select
        cast('{{ var("date_debut_paysim") }}' as date) - interval '{{ var("annees_historique_change") }} years' as date_min,
        greatest(
            (select max(date_cours) from cotations),
            cast('{{ var("date_debut_paysim") }}' as date) + 90
        ) as date_max
),

calendrier as (
    select cast(generate_series(date_min, date_max, interval '1 day') as date) as date_cours
    from bornes
),

grille as (
    select
        c.date_cours,
        d.code_devise,
        d.regime_change,
        case
            when d.regime_change = 'reference' then 1.0
            when d.regime_change = 'fixe'      then d.parite_fixe_par_eur
            else t.taux_eur
        end as taux_publie
    from calendrier c
    cross join devises d
    left join cotations t
        on t.date_cours = c.date_cours
       and t.code_devise = d.code_devise
),

groupes as (
    select
        *,
        -- chaque nouvelle publication ouvre un groupe ; les jours suivants sans cotation en font partie
        count(taux_publie) over (partition by code_devise order by date_cours) as id_groupe_publication
    from grille
),

reportes as (
    select
        date_cours,
        code_devise,
        regime_change,
        id_groupe_publication,
        taux_publie is not null as est_taux_publie,
        first_value(taux_publie) over (partition by code_devise, id_groupe_publication order by date_cours) as taux_reporte,
        date_cours - max(case when taux_publie is not null then date_cours end)
            over (partition by code_devise order by date_cours) as jours_depuis_publication
    from groupes
)

select
    date_cours,
    code_devise,
    regime_change,
    id_groupe_publication,
    est_taux_publie,
    jours_depuis_publication,
    case
        when jours_depuis_publication <= {{ var('jours_report_max_taux') }} then taux_reporte
    end as taux_eur
from reportes
