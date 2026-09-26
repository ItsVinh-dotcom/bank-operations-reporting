-- =====================================================================================
-- Mart refresh: recompute all months from p_from (inclusive) to the latest loaded date
-- =====================================================================================

CREATE OR REPLACE PROCEDURE mart.sp_refresh(p_from date, p_to date DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE
    v_from date := greatest(date_trunc('month', p_from)::date,
                            COALESCE((SELECT date_trunc('month', min(snapshot_date))::date FROM dwh.fact_casa_balance),
                                     date_trunc('month', p_from)::date));
    v_to   date := COALESCE(p_to, (SELECT max(business_date) FROM dwh.fact_casa_txn));
    v_bal_from date;
BEGIN
    -- ---------------------------------------------------------------- KPI by branch & month
    DELETE FROM mart.kpi_branch_month WHERE month_end >= v_from;
    CREATE TEMP TABLE _months ON COMMIT DROP AS
    SELECT DISTINCT month_end FROM dwh.dim_date WHERE full_date BETWEEN v_from AND v_to;

    INSERT INTO mart.kpi_branch_month (month_end, branch_code)
    SELECT m.month_end, b.branch_code
    FROM _months m CROSS JOIN (SELECT DISTINCT branch_code FROM dwh.dim_branch) b
    JOIN dwh.dim_branch ob ON ob.branch_code = b.branch_code AND ob.is_current AND ob.open_date <= m.month_end;

    -- balances
    UPDATE mart.kpi_branch_month k SET casa_balance = s.v
    FROM (SELECT f.snapshot_date, a.branch_code, sum(f.balance) v FROM dwh.fact_casa_balance f
          JOIN dwh.dim_casa_account a USING (account_no) WHERE f.snapshot_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.snapshot_date AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET td_balance = s.v
    FROM (SELECT f.snapshot_date, t.branch_code, sum(f.principal) v FROM dwh.fact_td_balance f
          JOIN dwh.dim_term_deposit t USING (td_id) WHERE f.snapshot_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.snapshot_date AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k
    SET loan_balance = COALESCE(s.bal, 0), loan_retail_balance = COALESCE(s.retail, 0),
        loan_sme_balance = COALESCE(s.sme, 0), group2_balance = COALESCE(s.g2, 0), npl_balance = COALESCE(s.npl, 0),
        specific_provision = COALESCE(s.sp, 0), general_provision = COALESCE(s.gp, 0), writeoff_amount = COALESCE(s.wo, 0)
    FROM (SELECT f.snapshot_date, l.branch_code,
                 sum(f.outstanding_principal) FILTER (WHERE f.status IN ('ACTIVE', 'OVERDUE')) bal,
                 sum(f.outstanding_principal) FILTER (WHERE f.status IN ('ACTIVE', 'OVERDUE') AND l.product_code NOT LIKE 'LN_SME%') retail,
                 sum(f.outstanding_principal) FILTER (WHERE f.status IN ('ACTIVE', 'OVERDUE') AND l.product_code LIKE 'LN_SME%') sme,
                 sum(f.outstanding_principal) FILTER (WHERE f.status IN ('ACTIVE', 'OVERDUE') AND f.loan_group = 2) g2,
                 sum(f.outstanding_principal) FILTER (WHERE f.status IN ('ACTIVE', 'OVERDUE') AND f.loan_group >= 3) npl,
                 sum(f.specific_provision) sp, sum(f.general_provision) gp,
                 sum(p.outstanding_principal) FILTER (WHERE f.status = 'WRITTEN_OFF') wo
          FROM dwh.fact_loan_balance f
          JOIN dwh.dim_loan l USING (loan_id)
          LEFT JOIN dwh.fact_loan_balance p ON p.loan_id = f.loan_id
               AND p.snapshot_date = (date_trunc('month', f.snapshot_date) - interval '1 day')::date
          WHERE f.snapshot_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.snapshot_date AND k.branch_code = s.branch_code;
    UPDATE mart.kpi_branch_month SET deposit_balance = casa_balance + td_balance WHERE month_end >= v_from;

    -- flows
    UPDATE mart.kpi_branch_month k SET disbursement_amount = s.amt, disbursement_count = s.n
    FROM (SELECT d.month_end, l.branch_code, sum(l.approved_amount) amt, count(*) n
          FROM dwh.dim_loan l JOIN dwh.dim_date d ON d.full_date = l.disbursement_date
          WHERE l.disbursement_date >= v_from AND l.product_code <> 'LN_CREDITCARD' GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET new_customers = s.n
    FROM (SELECT d.month_end, c.home_branch_code b, count(DISTINCT c.cif) n FROM dwh.dim_customer c
          JOIN dwh.dim_date d ON d.full_date = c.open_date WHERE c.open_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.b;

    UPDATE mart.kpi_branch_month k SET closed_customers = s.n
    FROM (SELECT d.month_end, c.home_branch_code b, count(DISTINCT c.cif) n FROM dwh.dim_customer c
          JOIN dwh.dim_date d ON d.full_date = c.close_date WHERE c.is_current AND c.close_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.b;

    UPDATE mart.kpi_branch_month k SET active_customers = s.n
    FROM (SELECT m.month_end, c.home_branch_code b, count(*) n
          FROM _months m JOIN dwh.dim_customer c
            ON c.valid_from <= m.month_end AND c.valid_to >= m.month_end AND c.status = 'ACTIVE'
          GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.b;

    UPDATE mart.kpi_branch_month k SET credit_cards_issued = s.iss, credit_cards_activated = s.act
    FROM (SELECT m.month_end, c.branch_code,
                 count(*) FILTER (WHERE c.issue_date BETWEEN date_trunc('month', m.month_end) AND m.month_end) iss,
                 count(*) FILTER (WHERE c.activation_date BETWEEN date_trunc('month', m.month_end) AND m.month_end) act
          FROM _months m JOIN dwh.dim_card c ON c.product_code LIKE 'CD_CREDIT%'
          GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET active_credit_cards = s.n
    FROM (SELECT m.month_end, c.branch_code, count(*) n
          FROM _months m JOIN dwh.dim_card c ON c.product_code LIKE 'CD_CREDIT%'
               AND c.activation_date <= m.month_end AND (c.close_date IS NULL OR c.close_date > m.month_end)
          GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET card_spend_amount = s.v
    FROM (SELECT d.month_end, c.branch_code, sum(t.amount) v FROM dwh.fact_card_txn t
          JOIN dwh.dim_card c USING (card_id) JOIN dwh.dim_date d ON d.full_date = t.business_date
          WHERE t.business_date >= v_from AND t.auth_status = 'APPROVED' GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k
    SET casa_txn_count = s.n, digital_txn_count = s.dig, counter_txn_count = s.cnt
    FROM (SELECT d.month_end, a.branch_code, count(*) n,
                 count(*) FILTER (WHERE t.channel_code IN ('MOBILE', 'INTERNET', 'POS')) dig,
                 count(*) FILTER (WHERE t.channel_code = 'COUNTER') cnt
          FROM dwh.fact_casa_txn t JOIN dwh.dim_casa_account a USING (account_no)
          JOIN dwh.dim_date d ON d.full_date = t.business_date
          WHERE t.business_date >= v_from AND t.channel_code <> 'SYSTEM' GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET atm_uptime_pct = s.u
    FROM (SELECT d.month_end, a.branch_code, avg(a.uptime_pct) u FROM dwh.fact_atm_daily a
          JOIN dwh.dim_date d ON d.full_date = a.report_date WHERE a.report_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET avg_wait_minutes = s.w
    FROM (SELECT d.month_end, o.branch_code,
                 sum(o.avg_wait_minutes * (o.counter_txn_count + o.service_request_count))
                 / NULLIF(sum(o.counter_txn_count + o.service_request_count), 0) w
          FROM dwh.fact_branch_ops o JOIN dwh.dim_date d ON d.full_date = o.business_date
          WHERE o.business_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    UPDATE mart.kpi_branch_month k SET complaints_received = s.n, complaints_sla_breached = s.br
    FROM (SELECT d.month_end, c.branch_code, count(*) n, count(*) FILTER (WHERE c.is_sla_breached) br
          FROM dwh.fact_complaint c JOIN dwh.dim_date d ON d.full_date = c.received_date
          WHERE c.received_date >= v_from GROUP BY 1, 2) s
    WHERE k.month_end = s.month_end AND k.branch_code = s.branch_code;

    CALL mart.sp_refresh_plan(v_from);

    -- ---------------------------------------------------------------- daily deposits (value date)
    DELETE FROM mart.deposit_daily WHERE balance_date >= v_from;
    v_bal_from := (v_from - 1);   -- previous month end snapshot = opening balance
    INSERT INTO mart.deposit_daily (balance_date, branch_code, product_code, balance)
    WITH opening AS (
        SELECT a.branch_code, a.product_code, sum(f.balance) AS bal
        FROM dwh.fact_casa_balance f JOIN dwh.dim_casa_account a USING (account_no)
        WHERE f.snapshot_date = v_bal_from GROUP BY 1, 2
    ), flows AS (
        SELECT t.txn_datetime::date AS d, a.branch_code, a.product_code, sum(t.signed_amount) AS net
        FROM dwh.fact_casa_txn t JOIN dwh.dim_casa_account a USING (account_no)
        WHERE t.txn_datetime >= v_from AND t.txn_datetime < v_to + 1 GROUP BY 1, 2, 3
    ), grid AS (
        SELECT d.full_date AS d, k.branch_code, k.product_code
        FROM dwh.dim_date d
        CROSS JOIN (SELECT branch_code, product_code FROM opening UNION SELECT branch_code, product_code FROM flows) k
        WHERE d.full_date BETWEEN v_from AND v_to
    )
    SELECT g.d, g.branch_code, g.product_code,
           COALESCE(o.bal, 0) + sum(COALESCE(f.net, 0)) OVER (PARTITION BY g.branch_code, g.product_code ORDER BY g.d)
    FROM grid g
    LEFT JOIN opening o USING (branch_code, product_code)
    LEFT JOIN flows f ON f.d = g.d AND f.branch_code = g.branch_code AND f.product_code = g.product_code;

    -- term deposits: +principal on open date, -principal on close date
    INSERT INTO mart.deposit_daily (balance_date, branch_code, product_code, balance)
    WITH ev AS (
        SELECT open_date AS d, branch_code, product_code, principal AS delta FROM dwh.dim_term_deposit
        UNION ALL
        SELECT close_date, branch_code, product_code, -principal FROM dwh.dim_term_deposit WHERE close_date IS NOT NULL
    ), opening AS (
        SELECT branch_code, product_code, sum(delta) AS bal FROM ev WHERE d < v_from GROUP BY 1, 2
    ), daily AS (
        SELECT d, branch_code, product_code, sum(delta) AS net FROM ev WHERE d BETWEEN v_from AND v_to GROUP BY 1, 2, 3
    ), grid AS (
        SELECT dd.full_date AS d, k.branch_code, k.product_code FROM dwh.dim_date dd
        CROSS JOIN (SELECT DISTINCT branch_code, product_code FROM dwh.dim_term_deposit) k
        WHERE dd.full_date BETWEEN v_from AND v_to
    )
    SELECT g.d, g.branch_code, g.product_code,
           COALESCE(o.bal, 0) + sum(COALESCE(x.net, 0)) OVER (PARTITION BY g.branch_code, g.product_code ORDER BY g.d)
    FROM grid g LEFT JOIN opening o USING (branch_code, product_code)
    LEFT JOIN daily x ON x.d = g.d AND x.branch_code = g.branch_code AND x.product_code = g.product_code;

    -- ---------------------------------------------------------------- loan migration
    DELETE FROM mart.loan_migration WHERE month_end >= v_from;
    INSERT INTO mart.loan_migration
    SELECT cur.snapshot_date, l.product_code,
           CASE WHEN prv.loan_id IS NULL THEN 'Mới giải ngân' ELSE 'Nhóm ' || prv.loan_group END,
           CASE cur.status WHEN 'WRITTEN_OFF' THEN 'Xử lý rủi ro' WHEN 'RECOVERED' THEN 'Thu hồi TSĐB'
                WHEN 'MATURED' THEN 'Tất toán' WHEN 'PREPAID' THEN 'Tất toán' WHEN 'CLOSED' THEN 'Tất toán'
                ELSE 'Nhóm ' || cur.loan_group END,
           count(*), COALESCE(sum(prv.outstanding_principal), 0), sum(cur.outstanding_principal)
    FROM dwh.fact_loan_balance cur
    JOIN dwh.dim_loan l USING (loan_id)
    LEFT JOIN dwh.fact_loan_balance prv ON prv.loan_id = cur.loan_id
         AND prv.snapshot_date = (date_trunc('month', cur.snapshot_date) - interval '1 day')::date
         AND prv.status IN ('ACTIVE', 'OVERDUE')
    WHERE cur.snapshot_date >= v_from AND cur.snapshot_date > (SELECT min(snapshot_date) FROM dwh.fact_loan_balance)
    GROUP BY 1, 2, 3, 4;

    -- ---------------------------------------------------------------- channels
    DELETE FROM mart.channel_month WHERE month_end >= v_from;
    INSERT INTO mart.channel_month
    SELECT d.month_end, a.branch_code, t.channel_code, t.txn_type, c.customer_type, count(*), sum(t.amount)
    FROM dwh.fact_casa_txn t
    JOIN dwh.dim_casa_account a USING (account_no)
    JOIN dwh.dim_customer c ON c.cif = a.cif AND c.is_current
    JOIN dwh.dim_date d ON d.full_date = t.business_date
    WHERE t.business_date >= v_from
    GROUP BY 1, 2, 3, 4, 5;

    -- ---------------------------------------------------------------- card spend
    DELETE FROM mart.card_spend_month WHERE month_end >= v_from;
    INSERT INTO mart.card_spend_month
    SELECT d.month_end, c.product_code, m.mcc_group,
           count(*) FILTER (WHERE t.auth_status = 'APPROVED'),
           COALESCE(sum(t.amount) FILTER (WHERE t.auth_status = 'APPROVED'), 0),
           count(*) FILTER (WHERE t.is_ecommerce AND t.auth_status = 'APPROVED'),
           count(*) FILTER (WHERE t.is_international AND t.auth_status = 'APPROVED'),
           count(*) FILTER (WHERE t.auth_status = 'DECLINED')
    FROM dwh.fact_card_txn t
    JOIN dwh.dim_card c USING (card_id)
    JOIN dwh.dim_mcc m USING (mcc)
    JOIN dwh.dim_date d ON d.full_date = t.business_date
    WHERE t.business_date >= v_from
    GROUP BY 1, 2, 3;

    -- ---------------------------------------------------------------- customers
    DELETE FROM mart.customer_month WHERE month_end >= v_from;
    INSERT INTO mart.customer_month
    SELECT m.month_end, c.home_branch_code, c.customer_type, c.segment,
           count(*) FILTER (WHERE c.status = 'ACTIVE'),
           count(*) FILTER (WHERE c.open_date BETWEEN date_trunc('month', m.month_end) AND m.month_end),
           count(*) FILTER (WHERE c.status = 'CLOSED' AND c.valid_from BETWEEN date_trunc('month', m.month_end) AND m.month_end),
           count(*) FILTER (WHERE c.status = 'ACTIVE' AND EXISTS (
               SELECT 1 FROM dwh.dim_loan l WHERE l.cif = c.cif AND l.product_code <> 'LN_CREDITCARD'
                 AND l.disbursement_date <= m.month_end AND (l.close_date IS NULL OR l.close_date > m.month_end))),
           count(*) FILTER (WHERE c.status = 'ACTIVE' AND EXISTS (
               SELECT 1 FROM dwh.dim_term_deposit t WHERE t.cif = c.cif
                 AND t.open_date <= m.month_end AND (t.close_date IS NULL OR t.close_date > m.month_end))),
           count(*) FILTER (WHERE c.status = 'ACTIVE' AND EXISTS (
               SELECT 1 FROM dwh.dim_card k WHERE k.cif = c.cif AND k.product_code LIKE 'CD_CREDIT%'
                 AND k.activation_date <= m.month_end AND (k.close_date IS NULL OR k.close_date > m.month_end)))
    FROM _months m
    JOIN dwh.dim_customer c ON c.valid_from <= m.month_end AND c.valid_to >= m.month_end
    GROUP BY 1, 2, 3, 4;
END $$;


-- Plan columns only (called after python/etl/load_plan.py)
CREATE OR REPLACE PROCEDURE mart.sp_refresh_plan(p_from date DEFAULT '1900-01-01')
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE mart.kpi_branch_month k
    SET plan_deposit = p.dep, plan_casa = p.casa, plan_loan = p.loan, plan_new_customers = p.kh, plan_credit_cards = p.cc
    FROM (SELECT plan_month, branch_code,
                 max(plan_value) FILTER (WHERE kpi_code = 'HUY_DONG') dep, max(plan_value) FILTER (WHERE kpi_code = 'CASA') casa,
                 max(plan_value) FILTER (WHERE kpi_code = 'DU_NO') loan, max(plan_value) FILTER (WHERE kpi_code = 'KH_MOI') kh,
                 max(plan_value) FILTER (WHERE kpi_code = 'THE_TD') cc
          FROM dwh.fact_plan WHERE plan_version = 'V1' GROUP BY 1, 2) p
    WHERE k.month_end = p.plan_month AND k.branch_code = p.branch_code AND k.month_end >= p_from;
END $$;
