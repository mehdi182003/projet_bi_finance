-- Lignes brutes ÉCARTÉES par le nettoyage, avec leur motif : audit et file de correction pour les filiales.
select
    id_ligne_source, systeme_source, nom_fichier, num_ligne, ref_operation, code_filiale,
    horodatage, libelle_source, montant_unitaire_devise, devise_source, client_source, statut_source,
    motif_rejet
from {{ ref('int_operations_controlees') }}
where motif_rejet is not null
