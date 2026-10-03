-- Dimension calendrier (libellés en français) couvrant l'historique de change,
-- la période PaySim rejouée et l'horizon de prévision.
with jours as (
    select distinct date_cours as date_jour
    from {{ ref('int_taux_change_journalier') }}
)

select
    date_jour,
    cast(to_char(date_jour, 'YYYYMMDD') as integer)                     as id_date,
    extract(year from date_jour)::int                                   as annee,
    extract(quarter from date_jour)::int                                as trimestre,
    extract(month from date_jour)::int                                  as mois,
    (array['janvier','février','mars','avril','mai','juin','juillet','août',
           'septembre','octobre','novembre','décembre'])[extract(month from date_jour)::int] as libelle_mois,
    to_char(date_jour, 'YYYY-MM')                                       as annee_mois,
    extract(isodow from date_jour)::int                                 as jour_semaine,
    (array['lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche'])[extract(isodow from date_jour)::int] as libelle_jour,
    extract(week from date_jour)::int                                   as semaine_iso,
    extract(isodow from date_jour) in (6, 7)                            as est_week_end,
    date_jour between cast('{{ var("date_debut_paysim") }}' as date)
                  and cast('{{ var("date_debut_paysim") }}' as date) + 30 as est_periode_paysim
from jours
