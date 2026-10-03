{{ config(materialized='table') }}
-- Position de départ de chaque filiale (le jour 1 de la période rejouée).
--   RG-POS-01 : encours de dépôts initial = somme des soldes d'ouverture (oldbalanceOrg)
--               des clients lors de leur PREMIÈRE apparition dans les logs.
--   RG-POS-02 : réserve de liquidité initiale = encours x taux de réserve de la filiale
--               (ref_filiales.taux_reserve_liquidite_pct, hypothèse paramétrable).
--   Montants convertis en devise locale au taux du premier jour (voir int_mouvements_tresorerie).

with premiere_apparition as (
    select distinct on (id_client_emetteur)
        id_client_emetteur,
        solde_avant_emetteur
    from {{ ref('stg_paysim__transactions') }}
    where id_client_emetteur like 'C%'
    order by id_client_emetteur, step_heure, id_transaction
),

par_filiale as (
    select
        f.code_filiale,
        sum(p.solde_avant_emetteur) as encours_initial_paysim,
        count(*)                    as nb_clients
    from premiere_apparition p
    join {{ ref('int_filiales_affectation') }} f
        on {{ seau_hachage('p.id_client_emetteur', 10000) }} >= f.borne_min
       and {{ seau_hachage('p.id_client_emetteur', 10000) }} <  f.borne_max
    group by f.code_filiale
),

taux_reference as (
    select code_devise, taux_eur as taux_reference
    from {{ ref('int_taux_change_journalier') }}
    where date_cours = cast('{{ var("date_debut_paysim") }}' as date)
)

select
    f.code_filiale,
    f.code_devise,
    coalesce(p.nb_clients, 0)                                                   as nb_clients,
    t.taux_reference,
    coalesce(p.encours_initial_paysim, 0) * {{ var('valeur_unite_paysim_eur') }} * t.taux_reference
                                                                                as encours_depots_initial_devise,
    coalesce(p.encours_initial_paysim, 0) * {{ var('valeur_unite_paysim_eur') }} * t.taux_reference
        * f.taux_reserve_liquidite_pct / 100                                    as reserve_liquidite_initiale_devise
from {{ ref('int_filiales_affectation') }} f
left join par_filiale p on p.code_filiale = f.code_filiale
left join taux_reference t on t.code_devise = f.code_devise
