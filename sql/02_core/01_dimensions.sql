-- =====================================================================================
-- DWH dimensions
-- =====================================================================================

-- Date dimension (populated by dwh.sp_build_dim_date)
CREATE TABLE IF NOT EXISTS dwh.dim_date (
    date_key        int PRIMARY KEY,           -- yyyymmdd
    full_date       date NOT NULL UNIQUE,
    day_of_month    smallint NOT NULL,
    day_of_week     smallint NOT NULL,         -- 1 = Monday
    day_name_vi     text NOT NULL,
    week_of_year    smallint NOT NULL,
    month_no        smallint NOT NULL,
    month_name_vi   text NOT NULL,
    quarter_no      smallint NOT NULL,
    year_no         smallint NOT NULL,
    year_month      text NOT NULL,             -- 2025-06
    month_start     date NOT NULL,
    month_end       date NOT NULL,
    is_weekend      boolean NOT NULL,
    is_holiday      boolean NOT NULL,
    holiday_name    text,
    is_business_day boolean NOT NULL,
    is_month_end    boolean NOT NULL,
    is_quarter_end  boolean NOT NULL,
    business_day_seq int NOT NULL              -- running number of business days (for SLA maths)
);

CREATE TABLE IF NOT EXISTS dwh.ref_holiday (
    holiday_date date PRIMARY KEY,
    holiday_name text NOT NULL
);

-- Provinces (34 units after 01/07/2025) and old -> new mapping (63 old units)
CREATE TABLE IF NOT EXISTS dwh.dim_province (
    province_code   text PRIMARY KEY,
    province_name   text NOT NULL,
    province_type   text NOT NULL,
    region          text NOT NULL,
    is_merged_2025  boolean NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.map_province_old_new (
    old_province_code text PRIMARY KEY,
    old_province_name text NOT NULL,
    new_province_code text NOT NULL REFERENCES dwh.dim_province(province_code)
);

-- Branch (SCD Type 2: province changes on 01/07/2025)
CREATE TABLE IF NOT EXISTS dwh.dim_branch (
    branch_sk           serial PRIMARY KEY,
    branch_code         text NOT NULL,
    branch_name         text NOT NULL,
    branch_level        text NOT NULL,             -- CN / PGD
    parent_branch_code  text,
    managing_branch_code text NOT NULL,            -- CN code (self for CN)
    province_code       text NOT NULL,
    province_name       text,
    region              text,
    district            text,
    open_date           date,
    status              text,
    valid_from          date NOT NULL,
    valid_to            date NOT NULL DEFAULT '9999-12-31',
    is_current          boolean NOT NULL DEFAULT true
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_branch_code_from ON dwh.dim_branch(branch_code, valid_from);
CREATE INDEX IF NOT EXISTS ix_dim_branch_current ON dwh.dim_branch(branch_code) WHERE is_current;

-- Customer (SCD Type 2 on segment, province, home branch, status; Type 1 on the rest)
CREATE TABLE IF NOT EXISTS dwh.dim_customer (
    customer_sk       serial PRIMARY KEY,
    cif               text NOT NULL,
    customer_type     text NOT NULL,               -- IND / SME
    full_name         text,
    gender            text,
    date_of_birth     date,
    id_number         text,
    tax_code          text,
    phone             text,
    province_code     text,
    home_branch_code  text,
    segment           text,
    occupation        text,
    industry          text,
    open_date         date,
    close_date        date,
    status            text,
    valid_from        date NOT NULL,
    valid_to          date NOT NULL DEFAULT '9999-12-31',
    is_current        boolean NOT NULL DEFAULT true,
    batch_id          int
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_customer_cif_from ON dwh.dim_customer(cif, valid_from);
CREATE INDEX IF NOT EXISTS ix_dim_customer_current ON dwh.dim_customer(cif) WHERE is_current;

-- Static reference dimensions
CREATE TABLE IF NOT EXISTS dwh.dim_product (
    product_code    text PRIMARY KEY,
    product_name    text NOT NULL,
    product_group   text NOT NULL,     -- Huy động / Tín dụng / Thẻ
    product_type    text NOT NULL,     -- CASA / TERM / LOAN / CARD
    customer_type   text NOT NULL,
    term_months_min int,
    term_months_max int
);
CREATE TABLE IF NOT EXISTS dwh.dim_channel (
    channel_code  text PRIMARY KEY,
    channel_name  text NOT NULL,
    channel_group text NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.dim_loan_group (
    loan_group              smallint PRIMARY KEY,
    loan_group_name         text NOT NULL,
    dpd_from                int NOT NULL,
    dpd_to                  int NOT NULL,
    is_npl                  boolean NOT NULL,
    specific_provision_rate numeric(5,4) NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.dim_mcc (
    mcc       text PRIMARY KEY,
    mcc_name  text NOT NULL,
    mcc_group text NOT NULL
);
CREATE TABLE IF NOT EXISTS dwh.dim_gl_account (
    gl_account text PRIMARY KEY,
    gl_name    text NOT NULL,
    gl_group   text NOT NULL,
    sign       char(1) NOT NULL
);
-- collateral deduction factors used for specific provisions (simplified)
CREATE TABLE IF NOT EXISTS dwh.ref_collateral_factor (
    collateral_type text PRIMARY KEY,
    deduction_rate  numeric(4,2) NOT NULL
);

-- Contract-level dimensions (Type 1: latest state from core)
CREATE TABLE IF NOT EXISTS dwh.dim_casa_account (
    account_no    text PRIMARY KEY,
    cif           text NOT NULL,
    product_code  text NOT NULL,
    branch_code   text NOT NULL,
    open_date     date NOT NULL,
    close_date    date,
    status        text NOT NULL,
    batch_id      int
);
CREATE INDEX IF NOT EXISTS ix_casa_account_cif ON dwh.dim_casa_account(cif);

CREATE TABLE IF NOT EXISTS dwh.dim_term_deposit (
    td_id          text PRIMARY KEY,
    cif            text NOT NULL,
    product_code   text NOT NULL,
    branch_code    text NOT NULL,
    open_date      date NOT NULL,
    maturity_date  date NOT NULL,
    term_months    smallint NOT NULL,
    interest_rate  numeric(6,2) NOT NULL,
    principal      bigint NOT NULL,
    rollover_of    text,
    close_date     date,
    close_reason   text,
    batch_id       int
);
CREATE INDEX IF NOT EXISTS ix_td_cif ON dwh.dim_term_deposit(cif);

CREATE TABLE IF NOT EXISTS dwh.dim_loan (
    loan_id            text PRIMARY KEY,
    cif                text NOT NULL,
    product_code       text NOT NULL,
    branch_code        text NOT NULL,
    disbursement_date  date NOT NULL,
    maturity_date      date,
    term_months        smallint,
    term_bucket        text,               -- Ngắn hạn / Trung hạn / Dài hạn
    approved_amount    bigint NOT NULL,
    interest_rate      numeric(6,2),
    repayment_method   text,
    collateral_type    text,
    collateral_value   bigint,
    close_date         date,
    close_reason       text,
    batch_id           int
);
CREATE INDEX IF NOT EXISTS ix_loan_cif ON dwh.dim_loan(cif);

CREATE TABLE IF NOT EXISTS dwh.dim_card (
    card_id          text PRIMARY KEY,
    masked_pan       text,
    cif              text NOT NULL,
    product_code     text NOT NULL,
    account_ref      text,
    branch_code      text,
    issue_date       date NOT NULL,
    activation_date  date,
    expiry_date      date,
    credit_limit     bigint,
    status           text,
    close_date       date,
    batch_id         int
);

CREATE TABLE IF NOT EXISTS dwh.dim_atm (
    atm_id       text PRIMARY KEY,
    branch_code  text NOT NULL,
    first_seen   date
);
