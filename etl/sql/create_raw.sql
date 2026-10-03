-- Couche RAW : données brutes, chargées telles quelles (approche ELT).
-- Aucune transformation métier ici : tout est fait ensuite dans dbt.
-- Script rejouable : les tables sont créées si besoin puis vidées (TRUNCATE), sans DROP,
-- car les vues dbt (couche staging) en dépendent.
create schema if not exists raw;
create schema if not exists ml;

-- Logs transactionnels PaySim (proxy des flux de la banque de détail)
create table if not exists raw.paysim_transactions (
    id_ligne          bigint generated always as identity primary key,
    step              integer,          -- 1 step = 1 heure de simulation (743 steps ~ 31 jours)
    type              text,             -- CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER
    amount            numeric(18, 2),
    name_orig         text,             -- client émetteur
    old_balance_orig  numeric(18, 2),
    new_balance_orig  numeric(18, 2),
    name_dest         text,             -- bénéficiaire (C... = client, M... = commerçant)
    old_balance_dest  numeric(18, 2),
    new_balance_dest  numeric(18, 2),
    is_fraud          smallint,
    is_flagged_fraud  smallint,
    _date_chargement  timestamp default now()
);

-- Taux de change de référence BCE (format long : 1 ligne = 1 date x 1 devise)
create table if not exists raw.bce_taux_change (
    date_cours        date,
    code_devise       text,
    taux              numeric(18, 6),  -- unités de devise pour 1 EUR
    source            text,
    _date_chargement  timestamp default now()
);

truncate table raw.paysim_transactions restart identity;
truncate table raw.bce_taux_change;
