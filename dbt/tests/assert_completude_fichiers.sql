-- COMPLÉTUDE : chaque fichier est chargé en entier (lignes en base = lignes lues), et pour les
-- fichiers DELTA, lignes lues = lignes annoncées et somme des montants = total de contrôle du pied.
with en_base as (
    select _fichier as nom_fichier, count(*) as nb, null::numeric as total from {{ source('raw', 'src_sab') }} group by 1
    union all select _fichier, count(*), null from {{ source('raw', 'src_nordic') }} group by 1
    union all select _fichier, count(*), null from {{ source('raw', 'src_americore') }} group by 1
    union all select _fichier, count(*), sum(nullif(trim(montant), '')::numeric) from {{ source('raw', 'src_delta') }} group by 1
)
select j.nom_fichier, j.nb_lignes_lues, j.nb_lignes_annoncees, b.nb as nb_en_base, j.total_annonce, b.total
from {{ source('raw', 'journal_chargement') }} j
left join en_base b using (nom_fichier)
where b.nb is distinct from j.nb_lignes_lues
   or (j.nb_lignes_annoncees is not null and j.nb_lignes_annoncees <> j.nb_lignes_lues)
   or (j.total_annonce is not null and b.total <> j.total_annonce)
