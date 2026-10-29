-- Transforme chaque ligne de flux de ZF Banque en mouvement de trésorerie valorisé en devise
-- locale et en EUR.
--   RG-SEN-01 : sens de trésorerie défini par ref_types_transaction (+1 entrée, -1 sortie).
--   RG-VAL-02 : contre-valeur EUR = montant devise / cours BCE du jour de l'opération.
--   RG-VOL-01 : une ligne représente `nb_operations` opérations (échantillon pondéré) :
--               montant total = montant unitaire x nb_operations.
--   RG-QUA-01 : les lignes de montant nul sont exclues.
--   (La v1 du POC répartissait les clients PaySim entre filiales par hachage : devenu inutile,
--    les flux 2023-2025 sont générés directement par filiale à partir des dépôts réels du pays.)

with flux as (
    select *
    from {{ ref('stg_zf__transactions') }}
    where montant_unitaire_devise > 0
),

filiales as (
    select code_filiale, code_devise from {{ ref('ref_filiales') }}
),

taux as (
    select date_cours, code_devise, taux_eur
    from {{ ref('int_taux_change_journalier') }}
)

select
    f.horodatage,
    f.heure_operation,
    f.date_operation,
    f.code_filiale,
    fi.code_devise,
    f.code_type,
    f.est_fraude,
    ty.sens_jambe_emetteur                                          as sens,
    f.nb_operations,
    f.montant_devise,
    f.montant_devise / t.taux_eur                                   as montant_eur,
    f.montant_unitaire_devise / t.taux_eur >= {{ var('seuil_gros_ticket_eur') }} as est_gros_ticket,
    f.id_client
from flux f
join filiales fi on fi.code_filiale = f.code_filiale
join {{ ref('ref_types_transaction') }} ty on ty.code_type = f.code_type
join taux t on t.code_devise = fi.code_devise and t.date_cours = f.date_operation
