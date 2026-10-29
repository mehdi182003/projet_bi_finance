-- Qualité des données PaySim, jour de simulation par jour (page « Qualité » de Power BI).
-- Montre POURQUOI la fenêtre d'analyse est restreinte (RG-QUA-02) : hors jours 6-17, le volume
-- s'effondre alors que le nombre de fraudes reste constant => artefact de simulation, pas un
-- comportement de clientèle.

with par_jour as (
    select
        jour_simulation,
        min(step_heure)                                            as step_debut,
        max(step_heure)                                            as step_fin,
        bool_and(est_periode_analyse)                              as est_periode_analyse,
        count(*)                                                   as nb_transactions,
        sum(montant_paysim)                                        as montant_paysim,
        count(*) filter (where montant_paysim = 0)                 as nb_montants_nuls,
        count(*) filter (where est_fraude)                         as nb_fraudes,
        sum(montant_paysim) filter (where est_fraude)              as montant_fraude_paysim,
        count(*) filter (where est_signalee_fraude)                as nb_fraudes_signalees,
        -- signature observée au profilage : la fraude vide le compte émetteur (montant = solde)
        count(*) filter (where code_type in ('CASH_OUT', 'TRANSFER') and montant_paysim > 0
                           and montant_paysim = solde_avant_emetteur) as nb_alertes_regle_vide_compte,
        count(*) filter (where est_fraude and code_type in ('CASH_OUT', 'TRANSFER') and montant_paysim > 0
                           and montant_paysim = solde_avant_emetteur) as nb_fraudes_detectees_regle,
        count(*) filter (where code_type in ('CASH_OUT', 'TRANSFER')
                           and montant_paysim > solde_avant_emetteur) as nb_montant_superieur_solde,
        count(*) filter (where code_type in ('CASH_OUT', 'TRANSFER')) as nb_retraits_virements
    from {{ ref('stg_paysim__transactions') }}
    group by jour_simulation
),

reference as (
    select percentile_cont(0.5) within group (order by nb_transactions) as volume_median
    from par_jour
    where est_periode_analyse
)

select
    p.jour_simulation,
    p.step_debut,
    p.step_fin,
    p.est_periode_analyse,
    p.nb_transactions,
    p.montant_paysim * {{ var('valeur_unite_paysim_eur') }}                      as montant_eur_approx,
    100.0 * p.nb_transactions / r.volume_median                                  as volume_vs_median_pct,
    p.nb_montants_nuls,
    p.nb_fraudes,
    100.0 * p.nb_fraudes / p.nb_transactions                                     as taux_fraude_pct,
    p.nb_fraudes_signalees,
    p.nb_alertes_regle_vide_compte,
    p.nb_fraudes_detectees_regle,
    100.0 * p.nb_montant_superieur_solde / nullif(p.nb_retraits_virements, 0)    as pct_montant_superieur_solde,
    case
        when p.est_periode_analyse                     then 'Retenu'
        when p.nb_transactions < 0.2 * r.volume_median then 'Exclu : activité anormalement faible'
        else 'Exclu : hors bloc continu stable'
    end                                                                          as statut
from par_jour p
cross join reference r
