{{ config(tags=['prevision']) }}
-- Précision des modèles de flux sur la période de backtest (jours exclus de l'apprentissage).
--   WAPE  = somme |réel - prévu| / somme réel   (robuste aux jours à faible volume)
--   MAPE  = moyenne des |réel - prévu| / réel
--   Biais = somme(prévu - réel) / somme réel   (> 0 : le modèle surestime)
--   Le modèle au WAPE le plus faible est le « champion » utilisé pour la prévision.

select
    md5(concat_ws('|', code_filiale, serie, modele))               as id_qualite,
    code_filiale,
    serie,
    modele,
    bool_or(est_champion)                                           as est_champion,
    count(*)                                                        as nb_jours_testes,
    min(date_jour)                                                  as debut_test,
    max(date_jour)                                                  as fin_test,
    sum(reel)                                                       as total_reel_devise,
    sum(prevu)                                                      as total_prevu_devise,
    100 * sum(abs(reel - prevu)) / nullif(sum(reel), 0)            as wape_pct,
    100 * avg(abs(reel - prevu) / nullif(reel, 0))                 as mape_pct,
    100 * sum(prevu - reel) / nullif(sum(reel), 0)                 as biais_pct
from {{ source('ml', 'backtest_prevision') }}
group by code_filiale, serie, modele
