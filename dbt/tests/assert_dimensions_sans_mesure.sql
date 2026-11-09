-- RG-MOD-01 : une table de dimensions décrit le contexte (qui, quoi, quand, où) et ne porte aucune
-- mesure (combien). Ce test échoue si une colonne numérique apparaît dans une dimension du schéma
-- marts, hors codes et clés autorisés ci-dessous (ce ne sont pas des quantités à additionner).
--   dim_date             : id_date, annee, trimestre, mois, jour_semaine, semaine_iso (découpage calendaire)
--   dim_filiale / dim_scenario_stress : ordre_affichage (clé de tri)
--   dim_devise           : parite_fixe_par_eur (constante de définition du régime fixe, 655,957)
--   dim_type_transaction : sens_jambe_emetteur (code de sens +1 / -1)
-- depends_on: {{ ref('dim_date') }} {{ ref('dim_filiale') }} {{ ref('dim_devise') }}
-- depends_on: {{ ref('dim_type_transaction') }} {{ ref('dim_scenario_stress') }}
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'marts'
  and table_name like 'dim\_%'
  and data_type in ('numeric', 'double precision', 'integer', 'bigint', 'smallint', 'real')
  and (table_name, column_name) not in (
      ('dim_date', 'id_date'), ('dim_date', 'annee'), ('dim_date', 'trimestre'), ('dim_date', 'mois'),
      ('dim_date', 'jour_semaine'), ('dim_date', 'semaine_iso'),
      ('dim_filiale', 'ordre_affichage'), ('dim_scenario_stress', 'ordre_affichage'),
      ('dim_devise', 'parite_fixe_par_eur'),
      ('dim_type_transaction', 'sens_jambe_emetteur')
  )
