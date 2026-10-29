-- FIABILITÉ : à chaque date publiée par une banque centrale, l'encours reconstitué à partir des
-- flux quotidiens doit égaler l'encours réel (à l'échelle de ZF Banque) à 0,01 % près.
select code_filiale, date_ancrage, ecart_pct
from {{ ref('mart_qualite_ancrage') }}
where abs(ecart_pct) > 0.01
