-- RAPPROCHEMENT COMPTABLE : pour chaque filiale et chaque jour, les crédits, débits et nombre
-- d'opérations issus des exports NETTOYÉS doivent égaler les soldes du grand livre (source
-- indépendante). Un doublon non supprimé, une extourne mal traitée ou une conversion de fuseau,
-- d'unité ou de signe erronée fait échouer ce test.
with operations as (
    select
        o.code_filiale,
        o.date_operation                                                           as date_comptable,
        sum(case when t.sens_jambe_emetteur > 0 then o.montant_devise else 0 end)  as total_credits,
        sum(case when t.sens_jambe_emetteur < 0 then o.montant_devise else 0 end)  as total_debits,
        sum(o.nb_operations)                                                       as nb_operations
    from {{ ref('int_operations_nettoyees') }} o
    join {{ ref('ref_types_transaction') }} t on t.code_type = o.code_type
    group by 1, 2
),
comptabilite as (
    select code_filiale, date_comptable, total_credits, total_debits, nb_operations
    from {{ source('raw', 'soldes_comptables') }}
)
select coalesce(o.code_filiale, c.code_filiale) as code_filiale,
       coalesce(o.date_comptable, c.date_comptable) as date_comptable,
       o.total_credits - c.total_credits as ecart_credits,
       o.total_debits - c.total_debits   as ecart_debits,
       o.nb_operations - c.nb_operations as ecart_nb_operations
from operations o
full outer join comptabilite c using (code_filiale, date_comptable)
where o.code_filiale is null or c.code_filiale is null
   or abs(o.total_credits - c.total_credits) > 1
   or abs(o.total_debits - c.total_debits) > 1
   or o.nb_operations <> c.nb_operations
