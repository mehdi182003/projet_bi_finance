{#- Convertit les colonnes numeric d'un mart en double precision, à la fin de sa construction.
    Power BI lit un numeric PostgreSQL en System.Decimal, limité à 28 chiffres. Les calculs non arrondis
    (divisions, écarts-types) en produisent jusqu'à 74 : l'import échoue alors sur ces tables.
    Le modèle Power BI déclare déjà ces colonnes en double. Contrôle : tests/assert_marts_sans_numeric.sql. -#}
{% macro convertir_numeric_en_double() -%}
    {%- if execute -%}
        {%- set colonnes = adapter.get_columns_in_relation(this) | selectattr('dtype', 'equalto', 'numeric') | list -%}
        {%- if colonnes -%}
            alter table {{ this }}
            {%- for colonne in colonnes %}
                alter column {{ adapter.quote(colonne.name) }} type double precision{{ ',' if not loop.last }}
            {%- endfor %}
        {%- endif -%}
    {%- endif -%}
{%- endmacro %}
