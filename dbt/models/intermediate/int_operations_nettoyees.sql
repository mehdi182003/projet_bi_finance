-- Opérations RETENUES après nettoyage : une ligne par opération réelle (lot), au format unique du groupe.
-- Lignage conservé (système, fichier, ligne, référence) pour remonter à la source brute.
select
    ref_operation,
    systeme_source,
    nom_fichier,
    num_ligne,
    horodatage,
    cast(horodatage as date)                    as date_operation,
    date_trunc('hour', horodatage)              as heure_operation,
    code_filiale,
    code_type,
    montant_unitaire_devise,
    nb_operations,
    montant_unitaire_devise * nb_operations     as montant_devise,
    id_client,
    est_fraude
from {{ ref('int_operations_controlees') }}
where motif_rejet is null
