-- Prépare la clé de répartition des clients entre filiales.
-- Chaque filiale reçoit une plage de seaux [borne_min, borne_max[ sur 0..9999,
-- proportionnelle à son poids dans la clientèle du groupe (ref_filiales).

select
    code_filiale,
    code_devise,
    poids_clientele_pct,
    taux_reserve_liquidite_pct,
    cast(100 * (sum(poids_clientele_pct) over (order by ordre_affichage) - poids_clientele_pct) as integer) as borne_min,
    cast(100 * sum(poids_clientele_pct) over (order by ordre_affichage) as integer)                         as borne_max
from {{ ref('ref_filiales') }}
