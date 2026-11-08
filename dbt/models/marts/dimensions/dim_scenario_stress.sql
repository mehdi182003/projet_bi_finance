-- Dimension SCÉNARIO DE STRESS : le contexte « quoi » de chaque scénario (nom, ordre, crise historique
-- de référence).
-- RG-MOD-01 : les chocs chiffrés (retraits %, change %, taux en pb, multiplicateur de sorties) sont des
-- mesures : ils sont portés, tels qu'appliqués à chaque filiale, par la table de faits mart_stress_test.
-- Leur paramétrage reste dans le référentiel ref_scenarios_stress (seed dbt).
select
    code_scenario,
    libelle_scenario,
    ordre_affichage,
    reference_historique
from {{ ref('ref_scenarios_stress') }}
