select
    f.code_filiale,
    f.nom_filiale,
    f.pays,
    f.code_pays_iso,
    f.region,
    f.code_devise,
    d.libelle_devise,
    d.regime_change,
    f.part_de_marche_depots_pct,
    f.source_depots,
    f.profil_paie,
    f.taux_reserve_liquidite_pct,
    f.ordre_affichage,
    e.nb_clients,
    e.encours_depots_initial_devise,
    e.reserve_liquidite_initiale_devise
from {{ ref('ref_filiales') }} f
join {{ ref('ref_devises') }} d on d.code_devise = f.code_devise
left join {{ ref('int_encours_initial') }} e on e.code_filiale = f.code_filiale
