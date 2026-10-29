{{ config(materialized='table') }}
-- Union des 4 systèmes sources + application des règles de NETTOYAGE. Toutes les lignes brutes sont
-- conservées avec leurs indicateurs de qualité et, le cas échéant, un MOTIF DE REJET : rien n'est
-- supprimé en silence (les rejets sont consultables dans int_operations_rejetees).
--   RG-NET-05 : libellé ou code d'opération -> type normalisé (ref_correspondance_libelles,
--               après normalisation : majuscules, accents, espaces)
--   RG-NET-06 : code devise -> code ISO (ref_correspondance_devises) ; « FCFA » -> devise CFA de la filiale ;
--               contrôle : la devise doit être celle de la filiale
--   RG-NET-07 : doublons : même référence d'opération dans le même système (renvoi de lignes,
--               fichiers mensuels qui se chevauchent) -> on garde la première occurrence
--   RG-NET-08 : exclusions métier : opérations annulées (SAB), comptes de test (AMERICORE),
--               extournes et écritures extournées (NORDIC)
--   RG-NET-09 : identifiant client -> <FILIALE>-<7 chiffres> ; absent -> <FILIALE>-INCONNU
--   RG-NET-10 : contrôles de validité : filiale, date dans la période, montant > 0, sens cohérent

with sources as (
    select * from {{ ref('stg_sab__operations') }}
    union all select * from {{ ref('stg_nordic__operations') }}
    union all select * from {{ ref('stg_americore__operations') }}
    union all select * from {{ ref('stg_delta__operations') }}
),

extournees as (
    select distinct systeme_source, reference_extournee as ref_operation
    from sources
    where reference_extournee is not null
),

enrichies as (
    select
        s.*,
        l.code_type,
        coalesce(l.est_libelle_officiel and s.libelle_source = s.libelle_normalise, false) as est_libelle_standard,
        ty.sens_jambe_emetteur                                                        as sens_attendu,
        fi.code_devise                                                                as devise_filiale,
        case when d.code_devise = 'CFA' and fi.code_devise in ('XOF', 'XAF') then fi.code_devise
             else d.code_devise end                                                   as code_devise,
        coalesce(d.est_code_iso and s.devise_source = d.valeur_normalisee, false)     as est_devise_standard,
        {{ normaliser_client('s.code_filiale', 's.client_source') }}                   as id_client,
        nullif(regexp_replace(s.client_source, '\D', '', 'g'), '') is null           as est_client_manquant,
        e.ref_operation is not null                                                   as est_ecriture_extournee,
        row_number() over (partition by s.systeme_source, s.ref_operation
                           order by s.nom_fichier, s.num_ligne)                       as rang_occurrence
    from sources s
    left join {{ ref('ref_correspondance_libelles') }} l
        on l.systeme_source = s.systeme_source and l.libelle_normalise = s.libelle_normalise
    left join {{ ref('ref_types_transaction') }} ty on ty.code_type = l.code_type
    left join {{ ref('ref_filiales') }} fi on fi.code_filiale = s.code_filiale
    left join {{ ref('ref_correspondance_devises') }} d on d.valeur_normalisee = upper(trim(s.devise_source))
    left join extournees e on e.systeme_source = s.systeme_source and e.ref_operation = s.ref_operation
)

select
    md5(concat_ws('|', systeme_source, nom_fichier, num_ligne))                       as id_ligne_source,
    *,
    rang_occurrence > 1                                                               as est_doublon,
    case
        when code_filiale is null                                       then 'Filiale inconnue'
        when rang_occurrence > 1                                        then 'Doublon'
        when statut_source = 'ANNULE'                                   then 'Opération annulée'
        when est_compte_test                                            then 'Compte de test'
        when statut_source = 'REVERSAL'                                 then 'Extourne'
        when est_ecriture_extournee                                     then 'Écriture extournée'
        when code_type is null                                          then 'Libellé inconnu'
        when horodatage is null
          or cast(horodatage as date) not between cast('{{ var("date_debut_analyse") }}' as date)
                                              and cast('{{ var("date_fin_analyse") }}' as date)
                                                                        then 'Date invalide'
        when montant_unitaire_devise is null or montant_unitaire_devise <= 0 then 'Montant invalide'
        when code_devise is distinct from devise_filiale                then 'Devise incohérente'
        when sens_source is not null and sens_source <> sens_attendu    then 'Sens incohérent'
    end                                                                               as motif_rejet
from enrichies
