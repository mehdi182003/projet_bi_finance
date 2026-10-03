select
    d.code_devise,
    d.libelle_devise,
    d.regime_change,
    d.parite_fixe_par_eur,
    d.banque_centrale,
    d.zone_monetaire,
    d.remarque,
    exists (select 1 from {{ ref('ref_filiales') }} f where f.code_devise = d.code_devise) as a_une_filiale
from {{ ref('ref_devises') }} d
