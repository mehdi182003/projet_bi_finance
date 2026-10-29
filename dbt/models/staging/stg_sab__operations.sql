-- Système SAB (France, Benelux, Finlande) : typage et normalisation du format, AUCUNE suppression.
--   RG-NET-02 : dates jj/mm/aaaa + heure hh:mm:ss -> horodatage
--   RG-NET-04 : montant à virgule décimale, toujours positif ; sens donné par SENS (C = crédit client)
--   Les lignes annulées (STATUT = ANNULE) sont signalées ici et écartées en couche intermediate.
with source as (
    select * from {{ source('raw', 'src_sab') }}
),

filiales as (
    select code_filiale, code_entite_source from {{ ref('ref_filiales') }} where systeme_source = 'SAB'
)

select
    'SAB'                                                                  as systeme_source,
    s._fichier                                                             as nom_fichier,
    s._ligne                                                               as num_ligne,
    trim(s.ref_ope)                                                        as ref_operation,
    f.code_filiale,
    to_timestamp(trim(s.date_ope) || ' ' || trim(s.heure_ope), 'DD/MM/YYYY HH24:MI:SS')::timestamp as horodatage,
    s.libelle_ope                                                          as libelle_source,
    {{ normaliser_libelle('s.libelle_ope') }}                              as libelle_normalise,
    nullif(trim(s.nb_ope), '')::integer                                    as nb_operations,
    replace(nullif(trim(s.montant), ''), ',', '.')::numeric(18, 2)         as montant_unitaire_devise,
    case upper(trim(s.sens)) when 'C' then 1 when 'D' then -1 end          as sens_source,
    s.devise                                                               as devise_source,
    s.num_client                                                           as client_source,
    upper(trim(s.ind_fraude)) = 'O'                                        as est_fraude,
    upper(trim(s.statut))                                                  as statut_source,
    cast(null as text)                                                     as reference_extournee,
    false                                                                  as est_compte_test,
    false                                                                  as est_heure_convertie_utc,
    false                                                                  as est_montant_unites_mineures
from source s
left join filiales f on f.code_entite_source = trim(s.code_etab)
