-- Qualité des exports des filiales, par système, filiale et mois : défauts détectés et corrigés
-- par l'ETL (page « Qualité des données » de Power BI, pilotage de la gouvernance des données).
select
    md5(concat_ws('|', systeme_source, code_filiale, date_trunc('month', horodatage)))  as id_qualite_source,
    systeme_source,
    code_filiale,
    cast(date_trunc('month', horodatage) as date)                                     as mois,
    count(*)                                                                          as nb_lignes_brutes,
    count(*) filter (where motif_rejet is null)                                       as nb_lignes_retenues,
    count(*) filter (where motif_rejet = 'Doublon')                                   as nb_doublons,
    count(*) filter (where motif_rejet = 'Opération annulée')                         as nb_annulees,
    count(*) filter (where motif_rejet = 'Compte de test')                            as nb_comptes_test,
    count(*) filter (where motif_rejet in ('Extourne', 'Écriture extournée'))         as nb_extournes,
    count(*) filter (where motif_rejet in ('Filiale inconnue', 'Libellé inconnu', 'Date invalide',
                                           'Montant invalide', 'Devise incohérente', 'Sens incohérent'))
                                                                                      as nb_rejets_inattendus,
    count(*) filter (where not est_libelle_standard)                                  as nb_libelles_corriges,
    count(*) filter (where not est_devise_standard)                                   as nb_devises_corrigees,
    count(*) filter (where est_client_manquant)                                       as nb_clients_manquants,
    count(*) filter (where est_heure_convertie_utc)                                   as nb_heures_converties_utc,
    count(*) filter (where est_montant_unites_mineures)                               as nb_montants_unites_mineures,
    count(*) filter (where statut_source = 'SUSPICION_VIDE')                          as nb_indicateurs_fraude_vides,
    100.0 * count(*) filter (where motif_rejet is not null) / count(*)                as taux_rejet_pct
from {{ ref('int_operations_controlees') }}
group by 1, 2, 3, 4
