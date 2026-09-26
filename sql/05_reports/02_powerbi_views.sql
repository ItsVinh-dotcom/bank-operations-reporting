-- =====================================================================================
-- Report layer for Power BI (schema rpt): stable, business-friendly views.
-- Power BI imports these views only, so the DWH can evolve without breaking the report.
--   python -m python.etl.run_sql sql/05_reports/02_powerbi_views.sql
-- =====================================================================================
CREATE SCHEMA IF NOT EXISTS rpt;

CREATE OR REPLACE VIEW rpt.dim_branch AS
SELECT branch_code, branch_name, branch_level, managing_branch_code, managing_branch_name,
       province_name, region
FROM mart.v_branch;

CREATE OR REPLACE VIEW rpt.dim_date AS
SELECT full_date, year_no, quarter_no, month_no,
       'T' || lpad(month_no::text, 2, '0') || '/' || year_no AS month_label,
       year_no * 100 + month_no AS year_month_key,
       'Q' || quarter_no || '/' || year_no AS quarter_label,
       month_end, is_month_end, is_business_day, day_of_week, day_name_vi
FROM dwh.dim_date
WHERE full_date BETWEEN DATE '2023-12-01' AND DATE '2026-08-31';

CREATE OR REPLACE VIEW rpt.dim_product AS
SELECT product_code, product_name, product_group, product_type, customer_type FROM dwh.dim_product;

CREATE OR REPLACE VIEW rpt.fact_kpi_branch_month AS
SELECT month_end, branch_code, casa_balance, td_balance, deposit_balance, loan_balance, loan_retail_balance,
       loan_sme_balance, group2_balance, npl_balance, specific_provision, general_provision, writeoff_amount,
       disbursement_amount, disbursement_count, new_customers, closed_customers, active_customers,
       credit_cards_issued, credit_cards_activated, active_credit_cards, card_spend_amount, casa_txn_count,
       digital_txn_count, counter_txn_count, complaints_received, complaints_sla_breached,
       plan_deposit, plan_casa, plan_loan, plan_new_customers, plan_credit_cards
FROM mart.kpi_branch_month;

CREATE OR REPLACE VIEW rpt.fact_deposit_daily AS
SELECT balance_date, branch_code, product_code, balance FROM mart.deposit_daily;

CREATE OR REPLACE VIEW rpt.fact_loan_portfolio AS
SELECT f.snapshot_date, l.branch_code, l.product_code, f.loan_group, g.loan_group_name,
       CASE WHEN g.is_npl THEN 1 ELSE 0 END AS is_npl,
       count(*) AS loan_count, sum(f.outstanding_principal) AS outstanding, sum(f.overdue_principal) AS overdue,
       sum(f.specific_provision) AS specific_provision, sum(f.general_provision) AS general_provision
FROM dwh.fact_loan_balance f
JOIN dwh.dim_loan l USING (loan_id)
JOIN dwh.dim_loan_group g ON g.loan_group = f.loan_group
WHERE f.status IN ('ACTIVE', 'OVERDUE')
GROUP BY 1, 2, 3, 4, 5, 6;

CREATE OR REPLACE VIEW rpt.fact_loan_migration AS
SELECT month_end, product_code, from_state, to_state,
       CASE from_state WHEN 'Mới giải ngân' THEN 0 ELSE right(from_state, 1)::int END AS from_order,
       CASE WHEN to_state LIKE 'Nhóm %' THEN right(to_state, 1)::int WHEN to_state = 'Tất toán' THEN 6 ELSE 7 END AS to_order,
       loan_count, amount_from, amount_to
FROM mart.loan_migration;

CREATE OR REPLACE VIEW rpt.fact_channel_month AS
SELECT m.month_end, m.branch_code, m.channel_code, c.channel_name, c.channel_group, m.txn_type, m.customer_type,
       m.txn_count, m.amount
FROM mart.channel_month m JOIN dwh.dim_channel c USING (channel_code);

CREATE OR REPLACE VIEW rpt.fact_card_spend_month AS
SELECT month_end, product_code, mcc_group, txn_count, amount, ecom_count, intl_count, declined_count
FROM mart.card_spend_month;

CREATE OR REPLACE VIEW rpt.fact_card_cohort AS
SELECT (date_trunc('month', issue_date) + interval '1 month - 1 day')::date AS issue_month, product_code, branch_code,
       count(*) AS cards_issued, count(activation_date) AS cards_activated
FROM dwh.dim_card
WHERE product_code LIKE 'CD_CREDIT%' AND issue_date >= DATE '2024-01-01'
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW rpt.fact_atm_daily AS
SELECT report_date, atm_id, branch_code, uptime_pct, incident_count, cash_out_flag::int AS cash_out_flag,
       onus_wd_count + offus_wd_count AS withdrawal_count, onus_wd_amount + offus_wd_amount AS withdrawal_amount
FROM dwh.fact_atm_daily;

CREATE OR REPLACE VIEW rpt.fact_complaint AS
SELECT complaint_id, branch_code, received_date, channel, complaint_type,
       CASE complaint_type
            WHEN 'ATM_KHONG_NHAN_TIEN' THEN 'ATM không nhận được tiền' WHEN 'CHUYEN_TIEN_LOI' THEN 'Chuyển tiền lỗi'
            WHEN 'TRA_SOAT_THE' THEN 'Tra soát giao dịch thẻ' WHEN 'PHI_DICH_VU' THEN 'Phí dịch vụ'
            WHEN 'THAI_DO_PHUC_VU' THEN 'Thái độ phục vụ' WHEN 'LOI_UNG_DUNG' THEN 'Lỗi ứng dụng'
            WHEN 'THE_BI_KHOA' THEN 'Thẻ bị khóa' WHEN 'KHOAN_VAY' THEN 'Khoản vay' ELSE 'Khác' END AS complaint_type_name,
       sla_days, resolution_bdays, CASE WHEN is_sla_breached THEN 1 ELSE 0 END AS is_sla_breached, status, is_valid
FROM dwh.fact_complaint;

CREATE OR REPLACE VIEW rpt.fact_branch_ops AS
SELECT business_date, branch_code, counter_txn_count, service_request_count, avg_wait_minutes, pct_wait_under_15m
FROM dwh.fact_branch_ops;

CREATE OR REPLACE VIEW rpt.fact_dq AS
SELECT business_date, batch_type, rule_code, severity, dimension, description, checked_rows, failed_rows, status
FROM mart.v_dq_summary;
