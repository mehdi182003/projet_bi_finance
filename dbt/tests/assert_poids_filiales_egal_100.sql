-- La répartition des clients entre filiales doit couvrir 100 % des seaux de hachage.
select sum(poids_clientele_pct) as total
from {{ ref('ref_filiales') }}
having sum(poids_clientele_pct) <> 100
