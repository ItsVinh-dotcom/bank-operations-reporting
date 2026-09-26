-- =====================================================================================
-- DWH facts
-- =====================================================================================

-- CASA transactions (partitioned by business date, one partition per year)
CREATE TABLE IF NOT EXISTS dwh.fact_casa_txn (
    txn_id            text NOT NULL,
    account_no        text NOT NULL,
    txn_datetime      timestamp NOT NULL,
    business_date     date NOT NULL,
    date_key          int NOT NULL,
    txn_type          text NOT NULL,
    dr_cr             char(1) NOT NULL,
    amount            bigint NOT NULL,
    signed_amount     bigint NOT NULL,        -- + credit / - debit
    channel_code      text NOT NULL,
    branch_code       text NOT NULL,
    atm_id            text,
    counterparty_bank text,
    description       text,
    is_reversal       boolean NOT NULL,
    batch_id          int NOT NULL,
    PRIMARY KEY (txn_id, business_date)
) PARTITION BY RANGE (business_date);
CREATE TABLE IF NOT EXISTS dwh.fact_casa_txn_2024 PARTITION OF dwh.fact_casa_txn FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE IF NOT EXISTS dwh.fact_casa_txn_2025 PARTITION OF dwh.fact_casa_txn FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE IF NOT EXISTS dwh.fact_casa_txn_2026 PARTITION OF dwh.fact_casa_txn FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE IF NOT EXISTS dwh.fact_casa_txn_default PARTITION OF dwh.fact_casa_txn DEFAULT;
CREATE INDEX IF NOT EXISTS ix_casa_txn_account ON dwh.fact_casa_txn(account_no, business_date);

-- Month-end balance snapshots (periodic snapshot facts)
CREATE TABLE IF NOT EXISTS dwh.fact_casa_balance (
    snapshot_date   date NOT NULL,
    account_no      text NOT NULL,
    balance         bigint NOT NULL,
    accrued_interest bigint NOT NULL DEFAULT 0,
    status          text NOT NULL,
    batch_id        int NOT NULL,
    PRIMARY KEY (snapshot_date, account_no)
);

CREATE TABLE IF NOT EXISTS dwh.fact_td_balance (
    snapshot_date    date NOT NULL,
    td_id            text NOT NULL,
    principal        bigint NOT NULL,
    accrued_interest bigint NOT NULL,
    status           text NOT NULL,
    batch_id         int NOT NULL,
    PRIMARY KEY (snapshot_date, td_id)
);

CREATE TABLE IF NOT EXISTS dwh.fact_loan_balance (
    snapshot_date          date NOT NULL,
    loan_id                text NOT NULL,
    outstanding_principal  bigint NOT NULL,
    overdue_principal      bigint NOT NULL,
    dpd                    int NOT NULL,
    core_loan_group        smallint NOT NULL,     -- group reported by core banking
    cic_group              smallint,
    dpd_group              smallint NOT NULL,     -- recomputed in DWH from DPD
    loan_group             smallint NOT NULL,     -- final = max(dpd_group, cic_group)
    accrued_interest       bigint NOT NULL,
    specific_provision     bigint NOT NULL,
    general_provision      bigint NOT NULL,
    status                 text NOT NULL,         -- ACTIVE / OVERDUE / MATURED / PREPAID / WRITTEN_OFF / RECOVERED / CLOSED
    batch_id               int NOT NULL,
    PRIMARY KEY (snapshot_date, loan_id)
);

CREATE TABLE IF NOT EXISTS dwh.fact_card_txn (
    card_txn_id      text PRIMARY KEY,
    card_id          text NOT NULL,
    txn_datetime     timestamp NOT NULL,
    business_date    date NOT NULL,
    date_key         int NOT NULL,
    mcc              text NOT NULL,
    merchant_name    text,
    amount           bigint NOT NULL,
    is_ecommerce     boolean NOT NULL,
    is_international boolean NOT NULL,
    auth_status      text NOT NULL,
    batch_id         int NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_card_txn_card ON dwh.fact_card_txn(card_id, business_date);

CREATE TABLE IF NOT EXISTS dwh.fact_atm_daily (
    report_date      date NOT NULL,
    atm_id           text NOT NULL,
    branch_code      text NOT NULL,
    onus_wd_count    int NOT NULL,
    onus_wd_amount   bigint NOT NULL,
    offus_wd_count   int NOT NULL,
    offus_wd_amount  bigint NOT NULL,
    uptime_minutes   int NOT NULL,
    uptime_pct       numeric(6,4) NOT NULL,
    incident_count   int NOT NULL,
    cash_out_flag    boolean NOT NULL,
    batch_id         int NOT NULL,
    PRIMARY KEY (report_date, atm_id)
);

CREATE TABLE IF NOT EXISTS dwh.fact_branch_ops (
    business_date          date NOT NULL,
    branch_code            text NOT NULL,
    tellers                int NOT NULL,
    counter_txn_count      int NOT NULL,
    service_request_count  int NOT NULL,
    avg_wait_minutes       numeric(6,1) NOT NULL,
    avg_service_minutes    numeric(6,1) NOT NULL,
    pct_wait_under_15m     numeric(5,3) NOT NULL,
    batch_id               int NOT NULL,
    PRIMARY KEY (business_date, branch_code)
);

-- Accumulating snapshot: one row per complaint, updated when resolved
CREATE TABLE IF NOT EXISTS dwh.fact_complaint (
    complaint_id       text PRIMARY KEY,
    cif                text NOT NULL,
    branch_code        text NOT NULL,
    received_datetime  timestamp NOT NULL,
    received_date      date NOT NULL,
    channel            text NOT NULL,
    complaint_type     text NOT NULL,
    sla_days           int NOT NULL,
    sla_due_date       date NOT NULL,
    resolved_datetime  timestamp,
    resolution_bdays   int,
    is_sla_breached    boolean,
    status             text NOT NULL,
    is_valid           text,
    batch_id           int NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.fact_gl_balance (
    snapshot_date date NOT NULL,
    branch_code   text NOT NULL,
    gl_account    text NOT NULL,
    balance       bigint NOT NULL,
    batch_id      int NOT NULL,
    PRIMARY KEY (snapshot_date, branch_code, gl_account)
);

-- Business plan (loaded from Excel by python/etl/load_plan.py)
CREATE TABLE IF NOT EXISTS dwh.fact_plan (
    plan_month   date NOT NULL,         -- month end
    branch_code  text NOT NULL,
    kpi_code     text NOT NULL,         -- HUY_DONG / CASA / DU_NO / KH_MOI / THE_TD
    plan_value   numeric(20,2) NOT NULL,
    plan_version text NOT NULL DEFAULT 'V1',
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (plan_month, branch_code, kpi_code, plan_version)
);
