select
    code_scenario,
    libelle_scenario,
    ordre_affichage,
    choc_retraits_pct,
    choc_change_usd_pct,
    choc_change_cad_pct,
    choc_change_cfa_pct,
    choc_change_nordiques_pct,
    choc_taux_bp,
    multiplicateur_sorties,
    reference_historique
from {{ ref('ref_scenarios_stress') }}
