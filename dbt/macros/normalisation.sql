{#- Normalise un libellé : majuscules, sans accents, espaces multiples réduits, sans espaces de bord. -#}
{% macro normaliser_libelle(colonne) -%}
    trim(regexp_replace(
        translate(upper({{ colonne }}), 'ÀÂÄÁÃÉÈÊËÍÎÏÓÔÖÕÚÙÛÜÇ', 'AAAAAEEEEIIIOOOOUUUUC'),
        '\s+', ' ', 'g'))
{%- endmacro %}

{#- Identifiant client normalisé : <FILIALE>-<7 chiffres> (les zéros de tête perdus sont restaurés).
    Valeurs nulles codées par les agences (vide, NULL, N/A, ?, 0000000) -> <FILIALE>-INCONNU. -#}
{% macro normaliser_client(code_filiale, colonne) -%}
    case
        when {{ client_manquant(colonne) }} then {{ code_filiale }} || '-INCONNU'
        else {{ code_filiale }} || '-' || lpad(regexp_replace({{ colonne }}, '\D', '', 'g'), 7, '0')
    end
{%- endmacro %}

{#- Vrai si l'identifiant client ne contient aucun chiffre significatif (vide, NULL, N/A, ?, 0000000). -#}
{% macro client_manquant(colonne) -%}
    nullif(ltrim(regexp_replace({{ colonne }}, '\D', '', 'g'), '0'), '') is null
{%- endmacro %}
