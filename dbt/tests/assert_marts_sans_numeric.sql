-- COMPATIBILITÉ POWER BI : aucune colonne numeric ne doit rester dans marts, sinon l'import peut échouer
-- sur les valeurs de plus de 28 chiffres (voir macros/compatibilite_power_bi.sql).
-- depends_on: {{ ref('fct_position_tresorerie_quotidienne') }}
-- depends_on: {{ ref('fct_taux_change') }}
-- depends_on: {{ ref('mart_exposition_change') }}
-- depends_on: {{ ref('mart_liquidite_placement') }}
-- depends_on: {{ ref('mart_stress_test') }}
select table_name, column_name
from information_schema.columns
where table_schema = 'marts'
  and data_type = 'numeric'
