{#-
  Répartit de façon déterministe un identifiant dans un « seau » entre 0 et modulo-1.
  hashtext() renvoie un entier signé 32 bits : on le décale pour obtenir un nombre positif.
  Le même client tombe toujours dans le même seau -> toujours dans la même filiale.
-#}
{% macro seau_hachage(expression, modulo) -%}
    mod(hashtext({{ expression }})::bigint + 2147483648, {{ modulo }})
{%- endmacro %}
