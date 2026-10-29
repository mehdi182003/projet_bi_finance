{{ config(tags=['prevision']) }}
-- Valeur de la prévision : réserve de liquidité requise pour rester au-dessus du besoin Bâle III
-- (10 % des dépôts) pendant tout le mois suivant dans 99 % des trajectoires simulées, comparée à la
-- réserve fixée aujourd'hui par la politique de la filiale (ref_filiales.taux_reserve_liquidite_pct).
--   > 0 : liquidité libérable (sur-réserve) -> placée au taux directeur réel en vigueur ;
--   < 0 : réserve insuffisante -> liquidité à lever.
select
    md5(code_filiale)                                   as id_reserve,
    code_filiale,
    code_devise,
    date_arrete,
    encours_depots_devise,
    taux_reserve_actuel_pct,
    reserve_requise_p99_pct,
    taux_reserve_actuel_pct - reserve_requise_p99_pct  as ecart_reserve_pts,
    liquidite_liberable_devise,
    liquidite_liberable_eur,
    taux_directeur_pct,
    gain_annuel_eur,
    proba_sous_100_politique_actuelle,
    case
        when liquidite_liberable_eur > 0 then 'Sur-réserve : liquidité à placer'
        else 'Réserve insuffisante : liquidité à lever'
    end                                                 as diagnostic
from {{ source('ml', 'reserve_optimale') }}
