-- Exposition du groupe au risque de change, par devise et par jour.
--   RG-RIS-02 : exposition = position de trésorerie détenue en devise (hors EUR), en contre-valeur EUR.
--   RG-RIS-03 : VaR paramétrique 95 % = 1,645 x volatilité quotidienne x exposition EUR ;
--               à 10 jours : x racine(10) (horizon réglementaire Bâle).
--   Les devises à parité fixe (XOF/XAF) ont une VaR nulle : leur risque est un risque
--   de rupture (dévaluation) traité par les stress tests, pas par la VaR.
--   RG-COU-02 : rapport coût / risque = coût annuel de couverture (différentiel de taux, %)
--               / volatilité annuelle (%). Plus il est bas, plus la couverture est « bon marché »
--               au regard du risque couvert => aide à la décision de couverture par devise.

with positions as (
    select
        p.date_position,
        p.code_devise,
        sum(p.position_cloture_devise)    as position_devise,
        sum(p.position_cloture_eur)       as exposition_eur,
        sum(p.effet_change_eur)           as effet_change_eur
    from {{ ref('fct_position_tresorerie_quotidienne') }} p
    group by p.date_position, p.code_devise
),

total_groupe as (
    select date_position, sum(exposition_eur) as position_groupe_eur
    from positions
    group by date_position
),

taux_directeurs as (
    select
        p.date_position,
        p.code_devise,
        (select r.taux_directeur_pct from {{ ref('ref_taux_directeurs') }} r
          where r.code_devise = p.code_devise and r.date_effet <= p.date_position
          order by r.date_effet desc limit 1) as taux_local_pct,
        (select r.taux_directeur_pct from {{ ref('ref_taux_directeurs') }} r
          where r.code_devise = 'EUR' and r.date_effet <= p.date_position
          order by r.date_effet desc limit 1) as taux_eur_pct
    from positions p
),

base as (
select
    md5(concat_ws('|', p.date_position, p.code_devise))                       as id_exposition,
    p.date_position,
    p.code_devise,
    t.regime_change,
    p.position_devise,
    p.exposition_eur,
    p.effet_change_eur,
    100 * p.exposition_eur / nullif(g.position_groupe_eur, 0)                 as part_position_groupe_pct,
    t.taux_eur,
    t.volatilite_annualisee_pct,
    {{ var('quantile_var_95') }} * t.volatilite_quotidienne * abs(p.exposition_eur)            as var_95_1j_eur,
    {{ var('quantile_var_95') }} * t.volatilite_quotidienne * abs(p.exposition_eur) * sqrt(10) as var_95_10j_eur,
    case when t.regime_change = 'flottant' then td.taux_local_pct - td.taux_eur_pct else 0 end as cout_couverture_annuel_pct
from positions p
join total_groupe g using (date_position)
join {{ ref('fct_taux_change') }} t
    on t.code_devise = p.code_devise and t.date_cours = p.date_position
join taux_directeurs td
    on td.code_devise = p.code_devise and td.date_position = p.date_position
where p.code_devise <> 'EUR'
)

select
    base.*,
    cout_couverture_annuel_pct * exposition_eur / 100                          as cout_couverture_annuel_eur,
    case when volatilite_annualisee_pct > 0
         then cout_couverture_annuel_pct / volatilite_annualisee_pct end       as rapport_cout_risque,
    case
        when regime_change = 'fixe'          then 'Pas de couverture de marché (parité fixe) : piloter par stress test'
        when volatilite_annualisee_pct < 1   then 'Couverture inutile (devise quasi ancrée à l''euro)'
        when cout_couverture_annuel_pct < 0  then 'Couvrir : la couverture rapporte (taux local < taux BCE)'
        when cout_couverture_annuel_pct / volatilite_annualisee_pct < 0.25 then 'Couverture prioritaire (coût faible au regard du risque)'
        else 'Couverture partielle à arbitrer (coût élevé au regard du risque)'
    end                                                                        as recommandation_couverture
from base
