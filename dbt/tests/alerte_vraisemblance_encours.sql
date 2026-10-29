{{ config(severity='warn') }}
-- Contrôle de vraisemblance d'un chiffre métier : dans une banque de détail, les décaissements
-- quotidiens représentent une petite fraction des dépôts. Hors de [0,05 % ; 5 %], l'encours
-- reconstitué à partir des soldes PaySim (peu fiables) doit être remis en cause.
select
    code_filiale,
    100 * avg(decaissements_eur) / avg(encours_depots_eur) as sorties_quotidiennes_sur_depots_pct
from {{ ref('fct_position_tresorerie_quotidienne') }}
group by code_filiale
having 100 * avg(decaissements_eur) / avg(encours_depots_eur) not between 0.05 and 5
