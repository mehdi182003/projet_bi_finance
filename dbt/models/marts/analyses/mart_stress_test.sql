-- Stress tests réglementaires simplifiés : scénarios (ref_scenarios_stress) x filiales,
-- appliqués à la dernière position connue (date d'arrêté).
--   RG-STR-01 : choc de change = dépréciation de la devise locale contre EUR
--               (la position et les dépôts perdent choc % de leur contre-valeur EUR).
--   RG-STR-02 : choc de retraits = sortie immédiate de choc_retraits_pct % des dépôts.
--   RG-STR-03 : sorties quotidiennes stressées = encaissements moyens - décaissements moyens x multiplicateur.
--   RG-STR-04 : horizon de survie = position stressée / sortie nette quotidienne stressée (jours).
--   RG-STR-05 : besoin de refinancement = sorties stressées sur 30 j - position stressée (si > 0),
--               au taux directeur local + marge + choc de taux.
--   Le même calcul est rejoué en temps réel dans Power BI via des paramètres « What-if ».

with date_arrete as (
    select max(date_position) as date_arrete
    from {{ ref('fct_position_tresorerie_quotidienne') }}
),

moyennes as (
    select
        p.code_filiale,
        avg(p.encaissements_eur) as encaissements_moyens_eur,
        avg(p.decaissements_eur) as decaissements_moyens_eur
    from {{ ref('fct_position_tresorerie_quotidienne') }} p, date_arrete a
    where p.date_position > a.date_arrete - {{ var('fenetre_moyenne_flux_jours') }}
    group by p.code_filiale
),

situation as (
    select
        l.date_position as date_arrete,
        l.code_filiale,
        l.code_devise,
        l.position_cloture_eur,
        l.encours_depots_eur,
        l.taux_directeur_local_pct,
        m.encaissements_moyens_eur,
        m.decaissements_moyens_eur
    from {{ ref('mart_liquidite_placement') }} l
    join date_arrete a on l.date_position = a.date_arrete
    join moyennes m on m.code_filiale = l.code_filiale
),

chocs as (
    select
        s.*,
        sc.code_scenario,
        sc.libelle_scenario,
        sc.ordre_affichage,
        sc.choc_retraits_pct,
        sc.choc_taux_bp,
        sc.multiplicateur_sorties,
        case s.code_devise
            when 'USD' then sc.choc_change_usd_pct
            when 'CAD' then sc.choc_change_cad_pct
            when 'XOF' then sc.choc_change_cfa_pct
            when 'XAF' then sc.choc_change_cfa_pct
            -- la couronne danoise est ancrée à l'euro (MCE II) : seules SEK et NOK sont choquées
            when 'SEK' then sc.choc_change_nordiques_pct
            when 'NOK' then sc.choc_change_nordiques_pct
            else 0
        end as choc_change_pct
    from situation s
    cross join {{ ref('ref_scenarios_stress') }} sc
),

calculs as (
    select
        c.*,
        c.position_cloture_eur * (1 + c.choc_change_pct / 100)                  as position_apres_change_eur,
        c.encours_depots_eur * (1 + c.choc_change_pct / 100)
            * c.choc_retraits_pct / 100                                         as retraits_massifs_eur,
        (c.encaissements_moyens_eur - c.decaissements_moyens_eur * c.multiplicateur_sorties)
            * (1 + c.choc_change_pct / 100)                                     as flux_net_quotidien_stresse_eur
    from chocs c
),

resultats as (
    select
        k.*,
        k.position_apres_change_eur - k.retraits_massifs_eur                    as position_stressee_eur,
        greatest(-k.flux_net_quotidien_stresse_eur, 0) * 30                     as sorties_30j_stressees_eur
    from calculs k
)

select
    md5(concat_ws('|', code_scenario, code_filiale))                            as id_stress,
    date_arrete,
    code_scenario,
    libelle_scenario,
    ordre_affichage,
    code_filiale,
    code_devise,
    choc_retraits_pct,
    choc_change_pct,
    choc_taux_bp,
    multiplicateur_sorties,
    position_cloture_eur                                                         as position_avant_choc_eur,
    position_apres_change_eur - position_cloture_eur                             as impact_change_eur,
    -retraits_massifs_eur                                                        as impact_retraits_eur,
    position_stressee_eur,
    flux_net_quotidien_stresse_eur,
    case when flux_net_quotidien_stresse_eur < 0
         then greatest(position_stressee_eur, 0) / -flux_net_quotidien_stresse_eur
    end                                                                          as horizon_survie_jours,
    greatest(sorties_30j_stressees_eur - position_stressee_eur, 0)              as besoin_refinancement_eur,
    greatest(sorties_30j_stressees_eur - position_stressee_eur, 0)
      * (taux_directeur_local_pct + {{ var('marge_refinancement_pct') }} + choc_taux_bp / 100) / 100
                                                                                 as cout_refinancement_annuel_eur,
    case
        when position_stressee_eur <= 0                                       then '3 - Critique'
        when flux_net_quotidien_stresse_eur >= 0                              then '1 - Résilient'
        when position_stressee_eur / -flux_net_quotidien_stresse_eur >= 30    then '1 - Résilient'
        when position_stressee_eur / -flux_net_quotidien_stresse_eur >= 7     then '2 - Vigilance'
        else '3 - Critique'
    end                                                                          as statut_resilience
from resultats
