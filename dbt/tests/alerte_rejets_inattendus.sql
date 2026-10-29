{{ config(severity='warn') }}
-- ALERTE : rejets qui ne relèvent pas des cas connus (doublons, annulations, tests, extournes).
-- Un libellé inconnu, une devise ou un sens incohérent signale un changement de format chez une
-- filiale : à remonter à son équipe et à corriger dans les tables de correspondance.
select systeme_source, code_filiale, motif_rejet, count(*) as nb
from {{ ref('int_operations_controlees') }}
where motif_rejet in ('Filiale inconnue', 'Libellé inconnu', 'Date invalide', 'Montant invalide',
                      'Devise incohérente', 'Sens incohérent')
group by 1, 2, 3
