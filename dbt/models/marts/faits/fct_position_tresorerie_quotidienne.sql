-- Position de trésorerie quotidienne de chaque filiale (fait « stock », semi-additif).
--   RG-POS-04 : encours de dépôts = encours initial réel + cumul des flux nets (retombe sur les dépôts
--               réels publiés : test assert_ancrage_depots_reels).
--   RG-POS-06 : la trésorerie est GÉRÉE : au 1er de chaque mois, la réserve est ramenée à sa cible
--               (taux de réserve x encours de dépôts de fin de mois précédent) par une opération de
--               trésorerie (refinancement si elle manque de liquidité, placement si elle en a trop).
--               Dans le mois : position = cible du mois + cumul des flux nets depuis le 1er.
--   RG-POS-07 : opération de trésorerie de fin de mois = cible du mois suivant - position de clôture
--               (> 0 : refinancement à lever ; < 0 : excédent à placer).
--   RG-POS-05 : position EUR = position devise / taux BCE du jour (réévaluation quotidienne) ;
--               l'écart avec la valorisation au cours du 1er jour = effet de change.

with flux_jour as (
    select
        date_operation                                                    as date_position,
        code_filiale,
        sum(encaissements_devise)                                         as encaissements_devise,
        sum(decaissements_devise)                                         as decaissements_devise,
        sum(flux_net_devise)                                              as flux_net_devise,
        sum(encaissements_eur)                                            as encaissements_eur,
        sum(decaissements_eur)                                            as decaissements_eur,
        sum(flux_net_eur)                                                 as flux_net_eur,
        sum(case when est_fraude then decaissements_eur else 0 end)      as decaissements_frauduleux_eur,
        sum(case when est_gros_ticket then decaissements_eur else 0 end) as decaissements_gros_tickets_eur,
        sum(nb_mouvements)                                                as nb_mouvements
    from {{ ref('fct_flux_tresorerie_horaire') }}
    group by date_operation, code_filiale
),

calendrier as (
    -- toutes les dates de la période x toutes les filiales (pas de trou si une journée est vide)
    select d.date_position, f.code_filiale, f.code_devise
    from (
        select cast(generate_series(min(date_position), max(date_position), interval '1 day') as date) as date_position
        from flux_jour
    ) d
    cross join {{ ref('ref_filiales') }} f
),

cumul as (
    select
        c.date_position,
        c.code_filiale,
        c.code_devise,
        coalesce(fj.encaissements_devise, 0)            as encaissements_devise,
        coalesce(fj.decaissements_devise, 0)            as decaissements_devise,
        coalesce(fj.flux_net_devise, 0)                 as flux_net_devise,
        coalesce(fj.encaissements_eur, 0)               as encaissements_eur,
        coalesce(fj.decaissements_eur, 0)               as decaissements_eur,
        coalesce(fj.flux_net_eur, 0)                    as flux_net_eur,
        coalesce(fj.decaissements_frauduleux_eur, 0)    as decaissements_frauduleux_eur,
        coalesce(fj.decaissements_gros_tickets_eur, 0)  as decaissements_gros_tickets_eur,
        coalesce(fj.nb_mouvements, 0)                   as nb_mouvements,
        e.taux_reference,
        e.reserve_liquidite_initiale_devise,
        e.encours_depots_initial_devise,
        f.taux_reserve_liquidite_pct,
        sum(coalesce(fj.flux_net_devise, 0)) over (
            partition by c.code_filiale order by c.date_position rows unbounded preceding
        ) as flux_net_cumule_devise,
        sum(coalesce(fj.flux_net_devise, 0)) over (
            partition by c.code_filiale, date_trunc('month', c.date_position) order by c.date_position
            rows unbounded preceding
        ) as flux_net_cumule_mois_devise
    from calendrier c
    join {{ ref('ref_filiales') }} f on f.code_filiale = c.code_filiale
    left join flux_jour fj
        on fj.date_position = c.date_position and fj.code_filiale = c.code_filiale
    join {{ ref('int_encours_initial') }} e on e.code_filiale = c.code_filiale
),

gestion as (
    select
        c.*,
        c.encours_depots_initial_devise + c.flux_net_cumule_devise                          as encours_depots_devise,
        -- encours de fin du mois précédent = encours avant les flux du mois en cours
        c.encours_depots_initial_devise + c.flux_net_cumule_devise - c.flux_net_cumule_mois_devise
                                                                                            as encours_debut_mois_devise
    from cumul c
),

positions as (
    select
        g.*,
        g.taux_reserve_liquidite_pct / 100 * g.encours_debut_mois_devise                    as cible_reserve_mois_devise,
        g.taux_reserve_liquidite_pct / 100 * g.encours_debut_mois_devise
            + g.flux_net_cumule_mois_devise                                                 as position_cloture_devise,
        g.date_position = (date_trunc('month', g.date_position) + interval '1 month - 1 day')::date
                                                                                            as est_fin_de_mois
    from gestion g
)

select
    md5(concat_ws('|', c.date_position, c.code_filiale))                                as id_position,
    c.date_position,
    c.code_filiale,
    c.code_devise,
    c.nb_mouvements,
    c.encaissements_devise,
    c.decaissements_devise,
    c.flux_net_devise,
    c.encaissements_eur,
    c.decaissements_eur,
    c.flux_net_eur,
    c.decaissements_frauduleux_eur,
    c.decaissements_gros_tickets_eur,
    c.cible_reserve_mois_devise,
    c.position_cloture_devise - c.flux_net_devise                                       as position_ouverture_devise,
    c.position_cloture_devise,
    c.encours_depots_devise,
    case when c.est_fin_de_mois
         then c.taux_reserve_liquidite_pct / 100 * c.encours_depots_devise - c.position_cloture_devise
    end                                                                                 as operation_tresorerie_devise,
    case when c.est_fin_de_mois
         then (c.taux_reserve_liquidite_pct / 100 * c.encours_depots_devise - c.position_cloture_devise) / t.taux_eur
    end                                                                                 as operation_tresorerie_eur,
    t.taux_eur                                                                          as taux_eur_jour,
    c.position_cloture_devise / t.taux_eur                                              as position_cloture_eur,
    c.position_cloture_devise / c.taux_reference                                        as position_cloture_eur_taux_constant,
    c.position_cloture_devise / t.taux_eur - c.position_cloture_devise / c.taux_reference as effet_change_eur,
    c.encours_depots_devise / t.taux_eur                                                as encours_depots_eur,
    c.position_cloture_devise / nullif(c.encours_depots_devise, 0)                      as ratio_reserve_sur_depots,
    a.encours_zf_devise                                                                 as encours_reel_publie_devise,
    a.encours_zf_devise is not null                                                     as est_date_publication
from positions c
join {{ ref('int_taux_change_journalier') }} t
    on t.code_devise = c.code_devise and t.date_cours = c.date_position
left join {{ ref('stg_zf__ancrages') }} a
    on a.code_filiale = c.code_filiale and a.date_ancrage = c.date_position
