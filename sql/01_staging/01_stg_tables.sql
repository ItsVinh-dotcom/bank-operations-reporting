-- Staging tables: one per core-banking extract, all columns TEXT (raw landing).
-- Generated from python/common/layouts.py -> keep both in sync (tests/test_layouts.py checks it).

DROP TABLE IF EXISTS stg.branch;
CREATE UNLOGGED TABLE stg.branch (
    branch_code              text,
    branch_name              text,
    branch_level             text,
    parent_branch_code       text,
    province_code            text,
    district                 text,
    open_date                text,
    status                   text,
    effective_date           text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.customer;
CREATE UNLOGGED TABLE stg.customer (
    cif                      text,
    customer_type            text,
    full_name                text,
    gender                   text,
    date_of_birth            text,
    id_number                text,
    tax_code                 text,
    phone                    text,
    province_code            text,
    home_branch_code         text,
    segment                  text,
    occupation               text,
    industry                 text,
    open_date                text,
    close_date               text,
    status                   text,
    record_action            text,
    effective_date           text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.casa_account;
CREATE UNLOGGED TABLE stg.casa_account (
    account_no               text,
    cif                      text,
    product_code             text,
    branch_code              text,
    open_date                text,
    close_date               text,
    status                   text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.casa_balance;
CREATE UNLOGGED TABLE stg.casa_balance (
    snapshot_date            text,
    account_no               text,
    balance                  text,
    accrued_interest         text,
    status                   text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.txn;
CREATE UNLOGGED TABLE stg.txn (
    txn_id                   text,
    account_no               text,
    txn_datetime             text,
    business_date            text,
    txn_type                 text,
    dr_cr                    text,
    amount                   text,
    channel_code             text,
    branch_code              text,
    atm_id                   text,
    counterparty_bank        text,
    description              text,
    is_reversal              text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.term_deposit;
CREATE UNLOGGED TABLE stg.term_deposit (
    td_id                    text,
    cif                      text,
    product_code             text,
    branch_code              text,
    open_date                text,
    maturity_date            text,
    term_months              text,
    interest_rate            text,
    principal                text,
    rollover_of              text,
    close_date               text,
    close_reason             text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.td_balance;
CREATE UNLOGGED TABLE stg.td_balance (
    snapshot_date            text,
    td_id                    text,
    principal                text,
    accrued_interest         text,
    status                   text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.loan;
CREATE UNLOGGED TABLE stg.loan (
    loan_id                  text,
    cif                      text,
    product_code             text,
    branch_code              text,
    disbursement_date        text,
    maturity_date            text,
    term_months              text,
    approved_amount          text,
    interest_rate            text,
    repayment_method         text,
    collateral_type          text,
    collateral_value         text,
    close_date               text,
    close_reason             text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.loan_balance;
CREATE UNLOGGED TABLE stg.loan_balance (
    snapshot_date            text,
    loan_id                  text,
    outstanding_principal    text,
    overdue_principal        text,
    dpd                      text,
    loan_group               text,
    cic_group                text,
    accrued_interest         text,
    status                   text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.card;
CREATE UNLOGGED TABLE stg.card (
    card_id                  text,
    masked_pan               text,
    cif                      text,
    product_code             text,
    account_ref              text,
    branch_code              text,
    issue_date               text,
    activation_date          text,
    expiry_date              text,
    credit_limit             text,
    status                   text,
    close_date               text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.card_txn;
CREATE UNLOGGED TABLE stg.card_txn (
    card_txn_id              text,
    card_id                  text,
    txn_datetime             text,
    business_date            text,
    mcc                      text,
    merchant_name            text,
    amount                   text,
    is_ecommerce             text,
    is_international         text,
    auth_status              text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.atm_daily;
CREATE UNLOGGED TABLE stg.atm_daily (
    business_date            text,
    atm_id                   text,
    branch_code              text,
    onus_wd_count            text,
    onus_wd_amount           text,
    offus_wd_count           text,
    offus_wd_amount          text,
    uptime_minutes           text,
    incident_count           text,
    cash_out_flag            text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.branch_ops;
CREATE UNLOGGED TABLE stg.branch_ops (
    business_date            text,
    branch_code              text,
    tellers                  text,
    counter_txn_count        text,
    service_request_count    text,
    avg_wait_minutes         text,
    avg_service_minutes      text,
    pct_wait_under_15m       text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.complaint;
CREATE UNLOGGED TABLE stg.complaint (
    complaint_id             text,
    cif                      text,
    branch_code              text,
    received_datetime        text,
    channel                  text,
    complaint_type           text,
    sla_days                 text,
    resolved_datetime        text,
    status                   text,
    is_valid                 text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);

DROP TABLE IF EXISTS stg.gl_balance;
CREATE UNLOGGED TABLE stg.gl_balance (
    snapshot_date            text,
    branch_code              text,
    gl_account               text,
    balance                  text,
    _row_no                  bigint GENERATED ALWAYS AS IDENTITY
);
