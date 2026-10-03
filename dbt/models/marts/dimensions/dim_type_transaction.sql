select
    code_type,
    libelle_type,
    categorie_tresorerie,
    sens_jambe_emetteur,
    genere_jambe_beneficiaire,
    description
from {{ ref('ref_types_transaction') }}
