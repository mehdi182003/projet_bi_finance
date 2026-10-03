-- Cœur des règles de gestion : transforme chaque transaction PaySim en mouvement(s)
-- de trésorerie pour une filiale de ZF Banque, en devise locale et en EUR.
--
--   RG-AFF-01 : chaque client est rattaché à UNE filiale de façon déterministe
--               (hachage de son identifiant, au prorata de ref_filiales.poids_clientele_pct).
--   RG-AFF-02 : pour un virement (TRANSFER), le bénéficiaire est dans la même filiale
--               avec une probabilité var('part_virements_domestiques_pct'), sinon dans une
--               autre filiale (flux intragroupe, potentiellement multidevise).
--   RG-VAL-01 : montant en devise locale = montant PaySim x var('valeur_unite_paysim_eur')
--               x taux EUR->devise du premier jour (calibrage fixe des volumes).
--   RG-VAL-02 : contre-valeur EUR = montant devise / taux BCE DU JOUR de l'opération.
--   RG-SEN-01 : sens de trésorerie défini par ref_types_transaction (+1 entrée, -1 sortie).
--   RG-SEN-02 : un virement génère 2 jambes (débit émetteur, crédit bénéficiaire).
--   RG-SEN-03 : un virement entre 2 clients de la même filiale est neutre => exclu.
--   RG-QUA-01 : les transactions de montant nul sont exclues.

with transactions as (
    select *
    from {{ ref('stg_paysim__transactions') }}
    where montant_paysim > 0
),

filiales as (
    select * from {{ ref('int_filiales_affectation') }}
),

types as (
    select * from {{ ref('ref_types_transaction') }}
),

taux as (
    select date_cours, code_devise, taux_eur
    from {{ ref('int_taux_change_journalier') }}
),

taux_reference as (
    select code_devise, taux_eur as taux_reference
    from taux
    where date_cours = cast('{{ var("date_debut_paysim") }}' as date)
),

seaux as (
    select
        t.*,
        {{ seau_hachage('t.id_client_emetteur', 10000) }}                 as seau_emetteur,
        {{ seau_hachage('t.id_beneficiaire', 100) }}                      as seau_domestique,
        {{ seau_hachage("t.id_beneficiaire || '|filiale'", 10000) }}      as seau_beneficiaire
    from transactions t
),

affectees as (
    select
        s.*,
        fe.code_filiale as code_filiale_emetteur,
        fe.code_devise  as code_devise_emetteur,
        case
            when s.code_type <> 'TRANSFER' then null
            when s.seau_domestique < {{ var('part_virements_domestiques_pct') }} then fe.code_filiale
            else fb.code_filiale
        end as code_filiale_beneficiaire
    from seaux s
    join filiales fe
        on s.seau_emetteur >= fe.borne_min and s.seau_emetteur < fe.borne_max
    left join filiales fb
        on s.seau_beneficiaire >= fb.borne_min and s.seau_beneficiaire < fb.borne_max
),

valorisees as (
    select
        a.*,
        a.montant_paysim * {{ var('valeur_unite_paysim_eur') }} * tr.taux_reference as montant_devise_emetteur,
        a.montant_paysim * {{ var('valeur_unite_paysim_eur') }} * tr.taux_reference / tj.taux_eur as montant_eur
    from affectees a
    join taux_reference tr on tr.code_devise = a.code_devise_emetteur
    join taux tj           on tj.code_devise = a.code_devise_emetteur
                          and tj.date_cours  = a.date_operation
    -- RG-SEN-03 : virement interne à une filiale => aucun impact de trésorerie
    where not (a.code_type = 'TRANSFER' and a.code_filiale_beneficiaire = a.code_filiale_emetteur)
),

jambe_emetteur as (
    select
        v.id_transaction,
        'EMETTEUR'                                          as role_jambe,
        v.horodatage,
        v.date_operation,
        v.code_type,
        v.est_fraude,
        v.code_filiale_emetteur                             as code_filiale,
        v.code_devise_emetteur                              as code_devise,
        ty.sens_jambe_emetteur                              as sens,
        v.montant_devise_emetteur                           as montant_devise,
        v.montant_eur,
        v.code_filiale_beneficiaire is not null             as est_intragroupe
    from valorisees v
    join types ty on ty.code_type = v.code_type
),

jambe_beneficiaire as (
    select
        v.id_transaction,
        'BENEFICIAIRE'                                      as role_jambe,
        v.horodatage,
        v.date_operation,
        v.code_type,
        v.est_fraude,
        v.code_filiale_beneficiaire                         as code_filiale,
        fb.code_devise                                      as code_devise,
        1                                                   as sens,
        v.montant_eur * tb.taux_eur                         as montant_devise,
        v.montant_eur,
        true                                                as est_intragroupe
    from valorisees v
    join types ty     on ty.code_type = v.code_type and ty.genere_jambe_beneficiaire
    join filiales fb  on fb.code_filiale = v.code_filiale_beneficiaire
    join taux tb      on tb.code_devise = fb.code_devise and tb.date_cours = v.date_operation
)

select * from jambe_emetteur
union all
select * from jambe_beneficiaire
