{{ config(materialized='table') }}
-- Situation de départ de chaque filiale au 31/12/2022.
--   RG-POS-01 (v2) : encours de dépôts initial = encours RÉEL du pays (banque centrale) x part de
--                    marché de ZF Banque (ref_filiales.part_de_marche_depots_pct). Remplace la v1
--                    fondée sur les soldes PaySim, jugés peu fiables lors du profilage.
--   RG-POS-02      : réserve de liquidité initiale = encours x taux de réserve de la filiale.

with initial as (
    select code_filiale, encours_zf_devise
    from {{ ref('stg_zf__ancrages') }}
    where est_point_initial
),

clients as (
    select code_filiale, count(distinct id_client) as nb_clients
    from {{ ref('stg_zf__transactions') }}
    group by code_filiale
),

taux_reference as (
    select code_devise, taux_eur as taux_reference
    from {{ ref('int_taux_change_journalier') }}
    where date_cours = cast('{{ var("date_debut_analyse") }}' as date)
)

select
    f.code_filiale,
    f.code_devise,
    coalesce(c.nb_clients, 0)                                    as nb_clients,
    t.taux_reference,
    i.encours_zf_devise                                          as encours_depots_initial_devise,
    i.encours_zf_devise * f.taux_reserve_liquidite_pct / 100     as reserve_liquidite_initiale_devise
from {{ ref('ref_filiales') }} f
join initial i on i.code_filiale = f.code_filiale
left join clients c on c.code_filiale = f.code_filiale
left join taux_reference t on t.code_devise = f.code_devise
