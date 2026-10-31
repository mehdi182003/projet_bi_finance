-- Système SAB (France, Benelux, Finlande) : typage et normalisation du format, AUCUNE suppression.
--   RG-NET-02 : dates jj/mm/aaaa + heure hh:mm:ss -> horodatage ; depuis la migration de juillet 2024,
--               dates AAAA-MM-JJ : les deux formats sont reconnus
--   RG-NET-04 : montant à virgule décimale, toujours positif ; sens donné par SENS (C = crédit client) ;
--               séparateur de milliers (espace ou espace insécable des fichiers retouchés sous Excel) retiré
--   RG-NET-07 : références saisies avec des espaces de bord -> trim (sinon les doublons passent)
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
    case when trim(s.date_ope) ~ '^\d{4}-\d{2}-\d{2}$'
         then to_timestamp(trim(s.date_ope) || ' ' || trim(s.heure_ope), 'YYYY-MM-DD HH24:MI:SS')
         else to_timestamp(trim(s.date_ope) || ' ' || trim(s.heure_ope), 'DD/MM/YYYY HH24:MI:SS')
    end::timestamp                                                         as horodatage,
    s.libelle_ope                                                          as libelle_source,
    {{ normaliser_libelle('s.libelle_ope') }}                              as libelle_normalise,
    nullif(trim(s.nb_ope), '')::integer                                    as nb_operations,
    replace(nullif(translate(s.montant, ' ' || chr(160), ''), ''), ',', '.')::numeric(18, 2)
                                                                           as montant_unitaire_devise,
    case upper(trim(s.sens)) when 'C' then 1 when 'D' then -1 end          as sens_source,
    s.devise                                                               as devise_source,
    s.num_client                                                           as client_source,
    upper(trim(s.ind_fraude)) = 'O'                                        as est_fraude,
    upper(trim(s.statut))                                                  as statut_source,
    cast(null as text)                                                     as reference_extournee,
    false                                                                  as est_compte_test,
    false                                                                  as est_heure_convertie_utc,
    false                                                                  as est_montant_unites_mineures,
    -- la migration (dates ISO) est un changement de format, pas un défaut de ligne : non comptée ici
    position(chr(160) in s.montant) > 0 or s.ref_ope <> trim(s.ref_ope)    as est_format_corrige
from source s
left join filiales f on f.code_entite_source = upper(trim(s.code_etab))
