-- Fait SITUATION INITIALE : les chiffres de départ et les paramètres de pilotage de chaque filiale.
-- Grain : 1 ligne par filiale, au 31/12/2022 (veille du début de la période d'analyse).
-- RG-MOD-01 : ces nombres étaient auparavant dans dim_filiale ; ils sont des mesures (« combien ? »)
--             et non du contexte, d'où cette table de faits dédiée.
--   RG-POS-01 : encours initial = encours réel du pays x part de marché de ZF Banque.
--   RG-POS-02 : réserve initiale = encours initial x taux de réserve cible de la filiale.
-- Additivité : l'encours et la réserve en EUR s'additionnent entre filiales ; les montants en
-- devise locale ne s'additionnent jamais entre filiales ; les pourcentages ne s'additionnent pas.
-- Le nombre de clients, qui ne servait à aucun indicateur, a été retiré du modèle (09/11/2026).
select
    md5(f.code_filiale)                                                    as id_situation,
    cast('{{ var("date_debut_analyse") }}' as date) - 1                    as date_situation,
    f.code_filiale,
    f.code_devise,
    f.part_de_marche_depots_pct,
    f.taux_reserve_liquidite_pct,
    e.taux_reference                                                       as taux_eur_reference,
    e.encours_depots_initial_devise,
    e.reserve_liquidite_initiale_devise,
    e.encours_depots_initial_devise / nullif(e.taux_reference, 0)          as encours_depots_initial_eur,
    e.reserve_liquidite_initiale_devise / nullif(e.taux_reference, 0)      as reserve_liquidite_initiale_eur
from {{ ref('ref_filiales') }} f
join {{ ref('int_encours_initial') }} e on e.code_filiale = f.code_filiale
