-- Contrôle de complétude : chaque transaction de la fenêtre d'analyse, non nulle et non neutralisée, se retrouve
-- dans le fait agrégé (aucune perte de ligne pendant les jointures filiale / taux).
with attendu as (
    select count(*) as nb
    from {{ ref('stg_paysim__transactions') }}
    where montant_paysim > 0
      and est_periode_analyse
),
obtenu as (
    select count(*) as nb
    from {{ ref('int_mouvements_tresorerie') }}
    where role_jambe = 'EMETTEUR'
),
neutralises as (
    -- virements internes à une même filiale (RG-SEN-03), recalculés indépendamment
    select count(*) as nb
    from {{ ref('stg_paysim__transactions') }} t
    join {{ ref('int_filiales_affectation') }} f
      on {{ seau_hachage('t.id_client_emetteur', 10000) }} >= f.borne_min
     and {{ seau_hachage('t.id_client_emetteur', 10000) }} <  f.borne_max
    left join {{ ref('int_filiales_affectation') }} fb
      on {{ seau_hachage("t.id_beneficiaire || '|filiale'", 10000) }} >= fb.borne_min
     and {{ seau_hachage("t.id_beneficiaire || '|filiale'", 10000) }} <  fb.borne_max
    where t.code_type = 'TRANSFER' and t.montant_paysim > 0 and t.est_periode_analyse
      and ({{ seau_hachage('t.id_beneficiaire', 100) }} < {{ var('part_virements_domestiques_pct') }}
           or fb.code_filiale = f.code_filiale)
)
select a.nb as attendu, o.nb as obtenu, n.nb as neutralises
from attendu a, obtenu o, neutralises n
where a.nb <> o.nb + n.nb
