-- Contrôle de cohérence : un virement entre deux filiales sort d'une filiale et entre dans
-- une autre pour la même contre-valeur EUR => la somme des flux intragroupe est nulle chaque jour.
select date_operation, sum(flux_net_eur) as ecart_eur
from {{ ref('fct_flux_tresorerie_horaire') }}
where est_intragroupe
group by date_operation
having abs(sum(flux_net_eur)) > 0.01
