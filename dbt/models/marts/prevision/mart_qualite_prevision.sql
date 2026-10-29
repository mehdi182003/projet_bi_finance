{{ config(tags=['prevision']) }}
-- Précision des modèles de flux sur le backtest (3 origines : fin sept., oct. et nov. 2025 ; horizon 1 mois).
--   WAPE  = somme |réel - prévu| / somme réel   (robuste aux jours à faible volume)
--   MAPE  = moyenne des |réel - prévu| / réel
--   Biais = somme(prévu - réel) / somme réel   (> 0 : le modèle surestime)
--   Le modèle au WAPE le plus faible est le « champion » utilisé pour la prévision.
--   Un modèle jugé divergent par le garde-fou Python a des prévisions NULL => est_divergent = vrai.

select
    md5(concat_ws('|', code_filiale, serie, modele))               as id_qualite,
    code_filiale,
    serie,
    modele,
    bool_or(est_champion)                                           as est_champion,
    bool_or(prevu is null or prevu = 'NaN'::float)                  as est_divergent,
    count(*)                                                        as nb_jours_testes,
    min(date_jour)                                                  as debut_test,
    max(date_jour)                                                  as fin_test,
    sum(reel)                                                       as total_reel_devise,
    sum(prevu) filter (where prevu <> 'NaN'::float)                 as total_prevu_devise,
    case when bool_or(prevu = 'NaN'::float) then null
         else 100 * sum(abs(reel - prevu)) / nullif(sum(reel), 0) end as wape_pct,
    case when bool_or(prevu = 'NaN'::float) then null
         else 100 * avg(abs(reel - prevu) / nullif(reel, 0)) end       as mape_pct,
    case when bool_or(prevu = 'NaN'::float) then null
         else 100 * sum(prevu - reel) / nullif(sum(reel), 0) end       as biais_pct
from {{ source('ml', 'backtest_prevision') }}
group by code_filiale, serie, modele
