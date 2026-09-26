-- =====================================================================================
-- Report views (Power BI / Excel friendly)
-- =====================================================================================

-- Bank-wide KPI by month with the key ratios
CREATE OR REPLACE VIEW mart.v_kpi_bank_month AS
SELECT month_end,
       sum(casa_balance) AS casa_balance, sum(td_balance) AS td_balance, sum(deposit_balance) AS deposit_balance,
       sum(loan_balance) AS loan_balance, sum(npl_balance) AS npl_balance, sum(group2_balance) AS group2_balance,
       sum(specific_provision + general_provision) AS total_provision, sum(writeoff_amount) AS writeoff_amount,
       sum(new_customers) AS new_customers, sum(active_customers) AS active_customers,
       sum(credit_cards_issued) AS credit_cards_issued, sum(credit_cards_activated) AS credit_cards_activated,
       round(sum(casa_balance) / NULLIF(sum(deposit_balance), 0), 4) AS casa_ratio,
       round(sum(npl_balance) / NULLIF(sum(loan_balance), 0), 4) AS npl_ratio,
       round(sum(loan_balance) / NULLIF(sum(deposit_balance), 0), 4) AS ldr,
       round(sum(specific_provision + general_provision) / NULLIF(sum(npl_balance), 0), 4) AS llr_coverage,
       round(sum(digital_txn_count)::numeric / NULLIF(sum(casa_txn_count), 0), 4) AS digital_share,
       sum(plan_deposit) AS plan_deposit, sum(plan_loan) AS plan_loan
FROM mart.kpi_branch_month
GROUP BY month_end;

-- T-1 daily deposit report: balance vs previous day, month start, year start
CREATE OR REPLACE VIEW mart.v_daily_deposit_report AS
WITH d AS (SELECT max(balance_date) AS t FROM mart.deposit_daily),
     x AS (
    SELECT dd.branch_code, p.product_type,
           sum(dd.balance) FILTER (WHERE dd.balance_date = d.t) AS bal_t,
           sum(dd.balance) FILTER (WHERE dd.balance_date = d.t - 1) AS bal_t1,
           sum(dd.balance) FILTER (WHERE dd.balance_date = (date_trunc('month', d.t) - interval '1 day')::date) AS bal_mtd,
           sum(dd.balance) FILTER (WHERE dd.balance_date = (date_trunc('year', d.t) - interval '1 day')::date) AS bal_ytd
    FROM mart.deposit_daily dd CROSS JOIN d JOIN dwh.dim_product p USING (product_code)
    GROUP BY 1, 2)
SELECT (SELECT t FROM d) AS report_date, b.managing_branch_name, x.branch_code, b.branch_name, x.product_type,
       x.bal_t, x.bal_t - x.bal_t1 AS chg_dod, x.bal_t - x.bal_mtd AS chg_mtd, x.bal_t - x.bal_ytd AS chg_ytd
FROM x JOIN mart.v_branch b USING (branch_code);

-- Term-deposit maturity ladder (liquidity view)
CREATE OR REPLACE VIEW mart.v_td_maturity_ladder AS
WITH asof AS (SELECT max(snapshot_date) AS d FROM dwh.fact_td_balance)
SELECT CASE WHEN t.maturity_date - a.d <= 7 THEN '1. ≤ 7 ngày'
            WHEN t.maturity_date - a.d <= 30 THEN '2. 8-30 ngày'
            WHEN t.maturity_date - a.d <= 90 THEN '3. 31-90 ngày'
            WHEN t.maturity_date - a.d <= 180 THEN '4. 91-180 ngày'
            WHEN t.maturity_date - a.d <= 365 THEN '5. 181-365 ngày'
            ELSE '6. > 1 năm' END AS bucket,
       t.product_code, count(*) AS contracts, sum(f.principal) AS principal,
       round(sum(f.principal * t.interest_rate) / NULLIF(sum(f.principal), 0), 2) AS avg_rate
FROM dwh.fact_td_balance f
JOIN asof a ON f.snapshot_date = a.d
JOIN dwh.dim_term_deposit t USING (td_id)
GROUP BY 1, 2;

-- Masked customer view: PII protection for report consumers
CREATE OR REPLACE VIEW mart.v_customer_masked AS
SELECT cif, customer_type,
       CASE WHEN customer_type = 'IND'
            THEN split_part(full_name, ' ', 1) || ' ***' ELSE full_name END AS display_name,
       gender, extract(year FROM age(current_date, date_of_birth))::int AS age,
       CASE WHEN id_number IS NULL THEN NULL ELSE left(id_number, 3) || '******' || right(id_number, 3) END AS id_masked,
       CASE WHEN phone IS NULL THEN NULL ELSE left(phone, 3) || '****' || right(phone, 3) END AS phone_masked,
       province_code, home_branch_code, segment, occupation, industry, open_date, close_date, status
FROM dwh.dim_customer WHERE is_current;
