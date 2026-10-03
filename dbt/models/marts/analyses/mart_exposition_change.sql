-- Exposition du groupe au risque de change, par devise et par jour.
--   RG-RIS-02 : exposition = position de trésorerie détenue en devise (hors EUR), en contre-valeur EUR.
--   RG-RIS-03 : VaR paramétrique 95 % = 1,645 x volatilité quotidienne x exposition EUR ;
--               à 10 jours : x racine(10) (horizon réglementaire Bâle).
--   Les devises à parité fixe (XOF/XAF) ont une VaR nulle : leur risque est un risque
--   de rupture (dévaluation) traité par les stress tests, pas par la VaR.

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
)

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
    {{ var('quantile_var_95') }} * t.volatilite_quotidienne * abs(p.exposition_eur) * sqrt(10) as var_95_10j_eur
from positions p
join total_groupe g using (date_position)
join {{ ref('fct_taux_change') }} t
    on t.code_devise = p.code_devise and t.date_cours = p.date_position
where p.code_devise <> 'EUR'
