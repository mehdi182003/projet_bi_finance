-- Encours de dépôts à vue RÉELS (banques centrales) ramenés à l'échelle de ZF Banque
-- (encours national x part de marché de ref_filiales), aux dates de publication.
select
    upper(trim(code_filiale))  as code_filiale,
    date_ancrage,
    encours_zf_devise,
    est_point_initial,
    est_interpole,
    source                     as source_depots
from {{ source('raw', 'ancrages_zf') }}
