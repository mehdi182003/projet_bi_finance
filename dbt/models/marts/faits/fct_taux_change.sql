-- Taux de change quotidiens + indicateurs de risque (variation, volatilité, rupture de série).
--   RG-RIS-01 : volatilité calculée sur les 60 dernières cotations publiées (~3 mois),
--               annualisée par racine(252 jours ouvrés).

with taux as (
    select date_cours, code_devise, regime_change, id_groupe_publication,
           est_taux_publie, jours_depuis_publication, taux_eur
    from {{ ref('int_taux_change_journalier') }}
),

publies as (
    select
        code_devise,
        date_cours,
        ln(taux_eur / lag(taux_eur) over (partition by code_devise order by date_cours)) as rendement_log
    from taux
    where est_taux_publie
      and regime_change = 'flottant'
),

volatilite as (
    select
        code_devise,
        date_cours,
        rendement_log,
        stddev_samp(rendement_log) over (
            partition by code_devise order by date_cours rows between 59 preceding and current row
        ) as volatilite_quotidienne
    from publies
),

jointe as (
    select
        t.date_cours, t.code_devise, t.regime_change, t.id_groupe_publication,
        t.est_taux_publie, t.jours_depuis_publication, t.taux_eur,
        v.rendement_log,
        v.volatilite_quotidienne as volatilite_publiee
    from taux t
    left join volatilite v
        on v.code_devise = t.code_devise and v.date_cours = t.date_cours
)

select
    md5(concat_ws('|', date_cours, code_devise))                           as id_taux,
    date_cours,
    code_devise,
    regime_change,
    taux_eur,
    case when taux_eur > 0 then 1 / taux_eur end                           as valeur_eur_par_unite,
    est_taux_publie,
    jours_depuis_publication,
    100 * (exp(rendement_log) - 1)                                         as variation_jour_pct,
    case
        when regime_change <> 'flottant' then 0
        else first_value(volatilite_publiee) over (
            partition by code_devise, id_groupe_publication order by date_cours)
    end                                                                    as volatilite_quotidienne,
    case
        when regime_change <> 'flottant' then 0
        else 100 * sqrt(252) * first_value(volatilite_publiee) over (
            partition by code_devise, id_groupe_publication order by date_cours)
    end                                                                    as volatilite_annualisee_pct,
    taux_eur is null                                                       as est_rupture_serie
from jointe
