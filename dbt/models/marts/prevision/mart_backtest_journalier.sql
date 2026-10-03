{{ config(tags=['prevision']) }}
-- Détail jour par jour du backtest (graphique « réel vs prévu » dans Power BI).
select
    md5(concat_ws('|', code_filiale, serie, modele, date_jour)) as id_backtest,
    code_filiale,
    serie,
    modele,
    est_champion,
    date_jour,
    reel  as reel_devise,
    prevu as prevu_devise
from {{ source('ml', 'backtest_prevision') }}
