{#- Convertit un step PaySim (1 = première heure) en horodatage réel. -#}
{% macro heure_paysim(colonne_step) -%}
    (cast('{{ var("date_debut_paysim") }}' as timestamp) + ({{ colonne_step }} - 1) * interval '1 hour')
{%- endmacro %}
