{#- Tests génériques réutilisables (évite une dépendance à dbt_utils / dbt_expectations). -#}

{% test entre_bornes(model, column_name, min_value=none, max_value=none) %}
select *
from {{ model }}
where {{ column_name }} is not null
  and (
      {% if min_value is not none %} {{ column_name }} < {{ min_value }} {% else %} false {% endif %}
      or
      {% if max_value is not none %} {{ column_name }} > {{ max_value }} {% else %} false {% endif %}
  )
{% endtest %}

{% test unicite_combinee(model, colonnes) %}
select {{ colonnes | join(', ') }}, count(*) as nb
from {{ model }}
group by {{ colonnes | join(', ') }}
having count(*) > 1
{% endtest %}
