-- Fiabilité des données : comparaison, à chaque date publiée par une banque centrale, entre
-- l'encours de dépôts RÉEL (ramené à l'échelle de ZF Banque) et l'encours reconstitué en cumulant
-- les flux quotidiens générés. L'écart doit être nul (test assert_ancrage_depots_reels).
select
    md5(concat_ws('|', a.code_filiale, a.date_ancrage))                     as id_ancrage,
    a.code_filiale,
    a.date_ancrage,
    a.source_depots,
    a.est_interpole,
    a.encours_zf_devise                                                     as encours_reel_devise,
    p.encours_depots_devise                                                 as encours_reconstitue_devise,
    p.encours_depots_devise - a.encours_zf_devise                           as ecart_devise,
    100 * (p.encours_depots_devise - a.encours_zf_devise) / a.encours_zf_devise as ecart_pct,
    p.encours_depots_eur                                                    as encours_reconstitue_eur
from {{ ref('stg_zf__ancrages') }} a
join {{ ref('fct_position_tresorerie_quotidienne') }} p
    on p.code_filiale = a.code_filiale and p.date_position = a.date_ancrage
where not a.est_point_initial
