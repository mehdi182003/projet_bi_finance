-- Cours de référence BCE : 1 EUR = taux_eur unités de la devise.
with source as (
    select * from {{ source('raw', 'bce_taux_change') }}
)

select
    date_cours,
    upper(trim(code_devise)) as code_devise,
    taux                     as taux_eur,
    source                   as source_taux
from source
where taux > 0
  and date_cours >= cast('{{ var("date_debut_analyse") }}' as date)
                    - interval '{{ var("annees_historique_change") }} years'
