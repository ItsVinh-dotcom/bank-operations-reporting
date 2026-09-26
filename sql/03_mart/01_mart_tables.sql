-- =====================================================================================
-- Reporting marts (consumed by Power BI & Excel). Rebuilt per month by mart.sp_refresh().
-- Amounts in VND.
-- =====================================================================================

-- KPI by branch and month (month-end balances + in-month flows + plan)
CREATE TABLE IF NOT EXISTS mart.kpi_branch_month (
    month_end              date NOT NULL,
    branch_code            text NOT NULL,
    casa_balance           numeric(20,0) NOT NULL DEFAULT 0,
    td_balance             numeric(20,0) NOT NULL DEFAULT 0,
    deposit_balance        numeric(20,0) NOT NULL DEFAULT 0,
    loan_balance           numeric(20,0) NOT NULL DEFAULT 0,
    loan_retail_balance    numeric(20,0) NOT NULL DEFAULT 0,
    loan_sme_balance       numeric(20,0) NOT NULL DEFAULT 0,
    group2_balance         numeric(20,0) NOT NULL DEFAULT 0,
    npl_balance            numeric(20,0) NOT NULL DEFAULT 0,
    specific_provision     numeric(20,0) NOT NULL DEFAULT 0,
    general_provision      numeric(20,0) NOT NULL DEFAULT 0,
    writeoff_amount        numeric(20,0) NOT NULL DEFAULT 0,
    disbursement_amount    numeric(20,0) NOT NULL DEFAULT 0,
    disbursement_count     int NOT NULL DEFAULT 0,
    new_customers          int NOT NULL DEFAULT 0,
    closed_customers       int NOT NULL DEFAULT 0,
    active_customers       int NOT NULL DEFAULT 0,
    credit_cards_issued    int NOT NULL DEFAULT 0,
    credit_cards_activated int NOT NULL DEFAULT 0,
    active_credit_cards    int NOT NULL DEFAULT 0,
    card_spend_amount      numeric(20,0) NOT NULL DEFAULT 0,
    casa_txn_count         int NOT NULL DEFAULT 0,
    digital_txn_count      int NOT NULL DEFAULT 0,
    counter_txn_count      int NOT NULL DEFAULT 0,
    atm_uptime_pct         numeric(6,4),
    avg_wait_minutes       numeric(6,2),
    complaints_received    int NOT NULL DEFAULT 0,
    complaints_sla_breached int NOT NULL DEFAULT 0,
    plan_deposit           numeric(20,0),
    plan_casa              numeric(20,0),
    plan_loan              numeric(20,0),
    plan_new_customers     numeric(12,0),
    plan_credit_cards      numeric(12,0),
    refreshed_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (month_end, branch_code)
);

-- Daily deposit balances (value-date) by branch and product: source of the T-1 daily report
CREATE TABLE IF NOT EXISTS mart.deposit_daily (
    balance_date  date NOT NULL,
    branch_code   text NOT NULL,
    product_code  text NOT NULL,
    balance       numeric(20,0) NOT NULL,
    PRIMARY KEY (balance_date, branch_code, product_code)
);

-- Loan-group migration matrix (month over month)
CREATE TABLE IF NOT EXISTS mart.loan_migration (
    month_end      date NOT NULL,
    product_code   text NOT NULL,
    from_state     text NOT NULL,     -- 'Nhóm 1'..'Nhóm 5' or 'Mới giải ngân'
    to_state       text NOT NULL,     -- 'Nhóm 1'..'Nhóm 5', 'Tất toán', 'Xử lý rủi ro', 'Thu hồi TSĐB'
    loan_count     int NOT NULL,
    amount_from    numeric(20,0) NOT NULL,   -- outstanding at start of month
    amount_to      numeric(20,0) NOT NULL,   -- outstanding at end of month
    PRIMARY KEY (month_end, product_code, from_state, to_state)
);

-- Transactions by channel
CREATE TABLE IF NOT EXISTS mart.channel_month (
    month_end     date NOT NULL,
    branch_code   text NOT NULL,
    channel_code  text NOT NULL,
    txn_type      text NOT NULL,
    customer_type text NOT NULL,
    txn_count     int NOT NULL,
    amount        numeric(20,0) NOT NULL,
    PRIMARY KEY (month_end, branch_code, channel_code, txn_type, customer_type)
);

-- Credit-card spend
CREATE TABLE IF NOT EXISTS mart.card_spend_month (
    month_end       date NOT NULL,
    product_code    text NOT NULL,
    mcc_group       text NOT NULL,
    txn_count       int NOT NULL,
    amount          numeric(20,0) NOT NULL,
    ecom_count      int NOT NULL,
    intl_count      int NOT NULL,
    declined_count  int NOT NULL,
    PRIMARY KEY (month_end, product_code, mcc_group)
);

-- Customer base
CREATE TABLE IF NOT EXISTS mart.customer_month (
    month_end        date NOT NULL,
    branch_code      text NOT NULL,
    customer_type    text NOT NULL,
    segment          text NOT NULL,
    active_customers int NOT NULL,
    new_customers    int NOT NULL,
    closed_customers int NOT NULL,
    with_loan        int NOT NULL,
    with_td          int NOT NULL,
    with_credit_card int NOT NULL,
    PRIMARY KEY (month_end, branch_code, customer_type, segment)
);

-- Data-quality summary (view)
CREATE OR REPLACE VIEW mart.v_dq_summary AS
SELECT r.business_date, b.batch_type, r.rule_code, q.entity, q.dimension, q.severity, q.description,
       r.checked_rows, r.failed_rows, r.failed_amount, r.status,
       CASE WHEN r.checked_rows > 0 THEN round(100.0 * r.failed_rows / r.checked_rows, 4) END AS failed_pct
FROM dq.result r
JOIN dq.rule q USING (rule_code)
JOIN ctl.batch b USING (batch_id);

-- Current-state branch view (for slicers)
CREATE OR REPLACE VIEW mart.v_branch AS
SELECT b.branch_code, b.branch_name, b.branch_level, b.managing_branch_code, m.branch_name AS managing_branch_name,
       b.province_code, p.province_name, p.region, b.district, b.open_date
FROM dwh.dim_branch b
JOIN dwh.dim_branch m ON m.branch_code = b.managing_branch_code AND m.is_current
LEFT JOIN dwh.dim_province p ON p.province_code = b.province_code
WHERE b.is_current;
