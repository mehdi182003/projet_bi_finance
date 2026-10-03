{{ config(severity='warn') }}
-- ALERTE (non bloquante) : devise surveillée dont la série BCE est interrompue à la date d'arrêté.
-- Cas attendu sur données réelles : RUB (cotation suspendue par la BCE le 01/03/2022).
-- Un modèle prédictif ne doit pas être alimenté par une série figée => devise exclue des prévisions.
select code_devise, jours_depuis_publication
from {{ ref('int_taux_change_journalier') }}
where date_cours = cast('{{ var("date_debut_paysim") }}' as date)
  and regime_change = 'flottant'
  and (taux_eur is null or jours_depuis_publication > {{ var('jours_report_max_taux') }})
