-- Aide à la décision : ratio de liquidité, date de franchissement du seuil, placement / refinancement,
-- coût de couverture. Choix des indicateurs justifiés dans docs/06_profil_donnees_et_choix_kpi.md.
--   RG-LIQ-01 (v2) : besoin de liquidité à 30 j = encours de dépôts x taux de fuite Bâle III
--                    var('taux_fuite_depots_lcr_pct'). La v1 y ajoutait la tendance des flux nets :
--                    double comptage, ratio toujours < 100 % et KPI de placement figés à 0.
--   RG-LIQ-02      : ratio de liquidité (LCR simplifié) = position / besoin (réglementaire >= 100 %).
--   RG-LIQ-05      : consommation quotidienne = - flux net moyen (fenêtre glissante) / position.
--   RG-LIQ-06      : jours avant 100 % = (position - besoin) / sortie nette moyenne. C'est l'indicateur
--                    d'anticipation : il dit QUAND se refinancer, pas seulement combien.
--   RG-LIQ-03 (v2) : liquidité excédentaire = max(position - besoin x seuil de pilotage, 0)
--                    => gain annuel si placée au taux directeur local.
--   RG-LIQ-04 (v2) : besoin de refinancement = max(besoin x seuil de pilotage - position, 0)
--                    => coût au taux directeur + marge ; économie si anticipé (taux programmé vs urgence).
--   RG-COU-01      : coût annuel de couverture d'une position en devise flottante contre EUR
--                    ~ différentiel de taux (taux local - taux BCE) x exposition (parité des taux d'intérêt).

with positions as (
    select
        p.date_position,
        p.code_filiale,
        p.code_devise,
        p.position_cloture_eur,
        p.encours_depots_eur,
        avg(p.flux_net_eur) over (
            partition by p.code_filiale order by p.date_position
            rows between {{ var('fenetre_moyenne_flux_jours') - 1 }} preceding and current row
        ) as flux_net_moyen_eur
    from {{ ref('fct_position_tresorerie_quotidienne') }} p
),

taux_directeurs as (
    -- taux en vigueur à chaque date (dernier taux dont la date d'effet est passée)
    select
        p.date_position,
        p.code_filiale,
        (select r.taux_directeur_pct from {{ ref('ref_taux_directeurs') }} r
          where r.code_devise = p.code_devise and r.date_effet <= p.date_position
          order by r.date_effet desc limit 1)                                  as taux_directeur_local_pct,
        (select r.taux_directeur_pct from {{ ref('ref_taux_directeurs') }} r
          where r.code_devise = 'EUR' and r.date_effet <= p.date_position
          order by r.date_effet desc limit 1)                                  as taux_directeur_eur_pct
    from positions p
),

calculs as (
    select
        p.date_position,
        p.code_filiale,
        p.code_devise,
        d.regime_change,
        p.position_cloture_eur,
        p.encours_depots_eur,
        p.flux_net_moyen_eur,
        p.encours_depots_eur * {{ var('taux_fuite_depots_lcr_pct') }} / 100     as besoin_liquidite_30j_eur,
        p.encours_depots_eur * {{ var('taux_fuite_depots_lcr_pct') }} / 100
            * {{ var('seuil_pilotage_lcr_pct') }} / 100                         as cible_pilotage_eur,
        t.taux_directeur_local_pct,
        t.taux_directeur_eur_pct
    from positions p
    join taux_directeurs t using (date_position, code_filiale)
    join {{ ref('ref_devises') }} d on d.code_devise = p.code_devise
)

select
    md5(concat_ws('|', date_position, code_filiale))                           as id_liquidite,
    date_position,
    code_filiale,
    code_devise,
    regime_change,
    position_cloture_eur,
    encours_depots_eur,
    flux_net_moyen_eur,
    100 * -flux_net_moyen_eur / nullif(position_cloture_eur, 0)               as consommation_quotidienne_pct,
    besoin_liquidite_30j_eur,
    cible_pilotage_eur,
    100 * position_cloture_eur / nullif(besoin_liquidite_30j_eur, 0)           as ratio_couverture_liquidite_pct,
    case
        when position_cloture_eur < besoin_liquidite_30j_eur then 0
        when flux_net_moyen_eur >= 0                         then null      -- pas de consommation : pas d'échéance
        else (position_cloture_eur - besoin_liquidite_30j_eur) / -flux_net_moyen_eur
    end                                                                        as jours_avant_seuil_100pct,
    greatest(position_cloture_eur - cible_pilotage_eur, 0)                     as liquidite_excedentaire_eur,
    greatest(cible_pilotage_eur - position_cloture_eur, 0)                     as besoin_refinancement_eur,
    taux_directeur_local_pct,
    taux_directeur_eur_pct,
    greatest(position_cloture_eur - cible_pilotage_eur, 0)
      * taux_directeur_local_pct / 100                                         as gain_placement_annuel_eur,
    greatest(cible_pilotage_eur - position_cloture_eur, 0)
      * (taux_directeur_local_pct + {{ var('marge_refinancement_pct') }}) / 100 as cout_refinancement_annuel_eur,
    greatest(cible_pilotage_eur - position_cloture_eur, 0)
      * {{ var('ecart_urgence_vs_programme_pct') }} / 100                      as economie_anticipation_annuelle_eur,
    case when regime_change = 'flottant'
         then position_cloture_eur * (taux_directeur_local_pct - taux_directeur_eur_pct) / 100
         else 0 end                                                            as cout_couverture_change_annuel_eur
from calculs
