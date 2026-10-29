-- Système AMERICORE (Canada, États-Unis) : typage et normalisation du format, AUCUNE suppression.
--   RG-NET-02 : dates MM/JJ/AAAA + heure hh:mm:ss AM/PM -> horodatage
--   RG-NET-04 : montant dans DebitAmount OU CreditAmount, avec séparateur de milliers (« 1,234.56 »)
--   Les comptes de test (AccountNo commençant par TEST) sont signalés et écartés en couche intermediate.
with source as (
    select * from {{ source('raw', 'src_americore') }}
),

filiales as (
    select code_filiale, code_entite_source from {{ ref('ref_filiales') }} where systeme_source = 'AMERICORE'
)

select
    'AMERICORE'                                                            as systeme_source,
    s._fichier                                                             as nom_fichier,
    s._ligne                                                               as num_ligne,
    trim(s.txnref)                                                         as ref_operation,
    f.code_filiale,
    to_timestamp(trim(s.txndate) || ' ' || trim(s.txntime), 'MM/DD/YYYY HH12:MI:SS AM')::timestamp as horodatage,
    s.txncode                                                              as libelle_source,
    trim(s.txncode)                                                        as libelle_normalise,
    nullif(trim(s.itemcount), '')::integer                                 as nb_operations,
    replace(coalesce(nullif(trim(s.debitamount), ''), nullif(trim(s.creditamount), '')), ',', '')::numeric(18, 2)
                                                                           as montant_unitaire_devise,
    case when nullif(trim(s.creditamount), '') is not null then 1
         when nullif(trim(s.debitamount), '') is not null then -1 end      as sens_source,
    s.currency                                                             as devise_source,
    s.accountno                                                            as client_source,
    upper(trim(s.fraudflag)) = 'Y'                                         as est_fraude,
    cast(null as text)                                                     as statut_source,
    cast(null as text)                                                     as reference_extournee,
    upper(trim(s.accountno)) like 'TEST%'                                  as est_compte_test,
    false                                                                  as est_heure_convertie_utc,
    false                                                                  as est_montant_unites_mineures
from source s
left join filiales f on f.code_entite_source = trim(s.entity)
