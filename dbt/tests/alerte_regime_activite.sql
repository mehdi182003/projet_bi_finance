{{ config(severity='warn') }}
-- ALERTE : un jour de la fenêtre d'analyse a moins de 50 % du volume médian de la fenêtre.
-- Si la fenêtre est modifiée (vars step_*_analyse), ce test signale qu'on y a inclus des jours atypiques.
select jour_simulation, nb_transactions, volume_vs_median_pct
from {{ ref('mart_qualite_donnees') }}
where est_periode_analyse
  and volume_vs_median_pct < 50
