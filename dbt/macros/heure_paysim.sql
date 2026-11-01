{#- Convertit un step PaySim en horodatage réel : le premier step de la fenêtre
    d'analyse (var step_debut_analyse) correspond à minuit le jour date_debut_paysim. -#}
{% macro heure_paysim(colonne_step) -%}
    (cast('{{ var("date_debut_paysim") }}' as timestamp)
        + ({{ colonne_step }} - {{ var("step_debut_analyse") }}) * interval '1 hour')
{%- endmacro %}
