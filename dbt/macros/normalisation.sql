{#- Normalise un libellé : majuscules, sans accents, espaces multiples réduits, sans espaces de bord. -#}
{% macro normaliser_libelle(colonne) -%}
    trim(regexp_replace(
        translate(upper({{ colonne }}), 'ÀÂÄÁÃÉÈÊËÍÎÏÓÔÖÕÚÙÛÜÇ', 'AAAAAEEEEIIIOOOOUUUUC'),
        '\s+', ' ', 'g'))
{%- endmacro %}

{#- Identifiant client normalisé : <FILIALE>-<7 chiffres> (les zéros de tête perdus sont restaurés). -#}
{% macro normaliser_client(code_filiale, colonne) -%}
    case
        when nullif(regexp_replace({{ colonne }}, '\D', '', 'g'), '') is null then {{ code_filiale }} || '-INCONNU'
        else {{ code_filiale }} || '-' || lpad(regexp_replace({{ colonne }}, '\D', '', 'g'), 7, '0')
    end
{%- endmacro %}
