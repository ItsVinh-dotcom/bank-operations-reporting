-- =====================================================================================
-- Data-quality checks, executed at the end of every batch
-- =====================================================================================

CREATE OR REPLACE PROCEDURE dq.sp_record(p_batch int, p_bdate date, p_rule text, p_checked bigint, p_failed bigint,
                                         p_amount numeric DEFAULT NULL)
LANGUAGE plpgsql AS $$
DECLARE thr numeric; st text;
BEGIN
    SELECT threshold_pct INTO thr FROM dq.rule WHERE rule_code = p_rule;
    st := CASE WHEN p_failed = 0 THEN 'PASS'
               WHEN p_checked > 0 AND 100.0 * p_failed / p_checked <= thr THEN 'WARN'
               ELSE 'FAIL' END;
    INSERT INTO dq.result(batch_id, business_date, rule_code, checked_rows, failed_rows, failed_amount, status)
    VALUES (p_batch, p_bdate, p_rule, p_checked, p_failed, p_amount, st)
    ON CONFLICT (batch_id, rule_code) DO UPDATE
    SET checked_rows = EXCLUDED.checked_rows, failed_rows = EXCLUDED.failed_rows,
        failed_amount = EXCLUDED.failed_amount, status = EXCLUDED.status, checked_at = now();
END $$;


CREATE OR REPLACE PROCEDURE dq.sp_run_checks(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE
    v_bdate date; v_checked bigint; v_failed bigint; v_amt numeric; v_prev date; v_snap date;
    t0 timestamptz := clock_timestamp();
BEGIN
    SELECT business_date INTO v_bdate FROM ctl.batch WHERE batch_id = p_batch;
    DELETE FROM dq.issue WHERE batch_id = p_batch;

    -- ---------------- CUSTOMER
    SELECT count(*) INTO v_checked FROM stg.customer;
    INSERT INTO dq.issue SELECT p_batch, 'CUS_DUP_CIF', cif, count(*) || ' bản ghi'
    FROM stg.customer GROUP BY cif, effective_date HAVING count(*) > 1 ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_failed = ROW_COUNT;
    CALL dq.sp_record(p_batch, v_bdate, 'CUS_DUP_CIF', v_checked, v_failed);

    SELECT count(*) FILTER (WHERE record_action IN ('INIT', 'NEW') AND customer_type = 'IND') INTO v_checked FROM stg.customer;
    INSERT INTO dq.issue SELECT DISTINCT p_batch, 'CUS_MISS_DOB', cif, full_name FROM stg.customer
    WHERE record_action IN ('INIT', 'NEW') AND customer_type = 'IND' AND COALESCE(date_of_birth, '') = ''
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_failed = ROW_COUNT;
    CALL dq.sp_record(p_batch, v_bdate, 'CUS_MISS_DOB', v_checked, v_failed);

    INSERT INTO dq.issue SELECT DISTINCT p_batch, 'CUS_MISS_ID', cif, full_name FROM stg.customer
    WHERE record_action IN ('INIT', 'NEW') AND customer_type = 'IND' AND COALESCE(id_number, '') = ''
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_failed = ROW_COUNT;
    CALL dq.sp_record(p_batch, v_bdate, 'CUS_MISS_ID', v_checked, v_failed);

    INSERT INTO dq.issue SELECT DISTINCT p_batch, 'CUS_BAD_PHONE', cif, phone FROM stg.customer
    WHERE customer_type = 'IND' AND phone !~ '^0[0-9]{9}$' ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_failed = ROW_COUNT;
    CALL dq.sp_record(p_batch, v_bdate, 'CUS_BAD_PHONE', v_checked, v_failed);

    -- ---------------- TXN
    SELECT count(*) INTO v_checked FROM stg.txn;
    IF v_checked > 0 THEN
        INSERT INTO dq.issue SELECT p_batch, 'TXN_DUP_ID', txn_id, count(*) || ' bản ghi'
        FROM stg.txn GROUP BY txn_id HAVING count(*) > 1 ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'TXN_DUP_ID', v_checked, v_failed);

        INSERT INTO dq.issue SELECT p_batch, 'TXN_BAD_BRANCH', txn_id, 'branch_code=' || branch_code
        FROM stg.txn t WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_branch b WHERE b.branch_code = t.branch_code)
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'TXN_BAD_BRANCH', v_checked, v_failed);

        SELECT count(*), COALESCE(sum(-amount::bigint), 0) INTO v_failed, v_amt FROM stg.txn
        WHERE amount::bigint < 0 AND is_reversal = '0';
        INSERT INTO dq.issue SELECT p_batch, 'TXN_NEG_AMOUNT', txn_id, 'amount=' || amount FROM stg.txn
        WHERE amount::bigint < 0 AND is_reversal = '0' ON CONFLICT DO NOTHING;
        CALL dq.sp_record(p_batch, v_bdate, 'TXN_NEG_AMOUNT', v_checked, v_failed, v_amt);

        INSERT INTO dq.issue SELECT p_batch, 'TXN_LATE_POST', txn_id,
               'txn=' || left(txn_datetime, 10) || ' posted=' || business_date
        FROM stg.txn WHERE dwh.f_date(business_date) > dwh.f_next_business_day(dwh.f_ts(txn_datetime)::date)
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'TXN_LATE_POST', v_checked, v_failed);

        INSERT INTO dq.issue SELECT p_batch, 'TXN_ORPHAN_ACC', txn_id, account_no FROM stg.txn t
        WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_casa_account a WHERE a.account_no = t.account_no)
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'TXN_ORPHAN_ACC', v_checked, v_failed);
    END IF;

    -- ---------------- LOAN contracts
    SELECT count(*) FILTER (WHERE collateral_type <> '') INTO v_checked FROM stg.loan;
    IF v_checked > 0 THEN
        INSERT INTO dq.issue SELECT DISTINCT p_batch, 'LN_MISS_COLL', loan_id, product_code FROM stg.loan
        WHERE collateral_type <> '' AND COALESCE(collateral_value, '') = '' ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'LN_MISS_COLL', v_checked, v_failed);
    END IF;

    -- ---------------- LOAN group consistency
    SELECT count(*) INTO v_checked FROM stg.loan_balance WHERE status IN ('ACTIVE', 'OVERDUE');
    IF v_checked > 0 THEN
        INSERT INTO dq.issue SELECT p_batch, 'LN_GROUP_DIFF', f.loan_id,
               'core=' || f.core_loan_group || ' dwh=' || f.loan_group
        FROM dwh.fact_loan_balance f
        WHERE f.batch_id = p_batch AND f.status IN ('ACTIVE', 'OVERDUE') AND f.core_loan_group <> f.loan_group
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'LN_GROUP_DIFF', v_checked, v_failed);
    END IF;

    -- ---------------- TD maturity consistency
    SELECT count(*) INTO v_checked FROM stg.term_deposit;
    IF v_checked > 0 THEN
        INSERT INTO dq.issue SELECT DISTINCT p_batch, 'TD_MATURITY', td_id, open_date || '+' || term_months || 'm<>' || maturity_date
        FROM stg.term_deposit
        WHERE (dwh.f_date(open_date) + (term_months || ' month')::interval)::date <> dwh.f_date(maturity_date)
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        CALL dq.sp_record(p_batch, v_bdate, 'TD_MATURITY', v_checked, v_failed);
    END IF;

    -- ---------------- month-end reconciliations (only when the batch carries snapshots)
    -- CASA roll-forward is checked with a one-period lag: transactions made on the last (weekend) days of a
    -- month are posted on the first business day of the next month, i.e. they arrive with the next batch.
    SELECT max(dwh.f_date(snapshot_date)) INTO v_snap FROM stg.casa_balance;
    IF v_snap IS NOT NULL THEN
        SELECT max(snapshot_date) INTO v_snap FROM dwh.fact_casa_balance WHERE snapshot_date < v_snap;   -- period end to check
        SELECT max(snapshot_date) INTO v_prev FROM dwh.fact_casa_balance WHERE snapshot_date < v_snap;   -- period start
        IF v_prev IS NOT NULL THEN
            WITH cur AS (SELECT account_no, balance FROM dwh.fact_casa_balance WHERE snapshot_date = v_snap),
                 prv AS (SELECT account_no, balance FROM dwh.fact_casa_balance WHERE snapshot_date = v_prev),
                 flo AS (SELECT account_no, sum(signed_amount) AS net FROM dwh.fact_casa_txn
                         WHERE txn_datetime >= v_prev + 1 AND txn_datetime < v_snap + 1
                           AND business_date BETWEEN v_prev AND v_snap + 10
                         GROUP BY account_no),
                 chk AS (SELECT COALESCE(c.account_no, p.account_no) AS account_no,
                                COALESCE(c.balance, 0) - COALESCE(p.balance, 0) - COALESCE(f.net, 0) AS diff
                         FROM cur c FULL JOIN prv p USING (account_no) LEFT JOIN flo f
                              ON f.account_no = COALESCE(c.account_no, p.account_no))
            INSERT INTO dq.issue SELECT p_batch, 'CASA_ROLLFWD', account_no || '@' || v_snap, 'diff=' || diff
            FROM chk WHERE diff <> 0
            ON CONFLICT DO NOTHING;
            GET DIAGNOSTICS v_failed = ROW_COUNT;
            SELECT count(*) INTO v_checked FROM dwh.fact_casa_balance WHERE snapshot_date = v_snap;
            CALL dq.sp_record(p_batch, v_bdate, 'CASA_ROLLFWD', v_checked, v_failed);
        END IF;
    END IF;

    SELECT max(dwh.f_date(snapshot_date)) INTO v_snap FROM stg.gl_balance;
    IF v_snap IS NOT NULL THEN
        WITH detail AS (
            SELECT a.branch_code, '4211' AS gl_account, sum(b.balance) AS bal
            FROM dwh.fact_casa_balance b JOIN dwh.dim_casa_account a USING (account_no)
            WHERE b.snapshot_date = v_snap GROUP BY a.branch_code
            UNION ALL
            SELECT t.branch_code, CASE WHEN t.product_code = 'TD_SME' THEN '4212' ELSE '4232' END, sum(b.principal)
            FROM dwh.fact_td_balance b JOIN dwh.dim_term_deposit t USING (td_id)
            WHERE b.snapshot_date = v_snap GROUP BY 1, 2
            UNION ALL
            SELECT l.branch_code,
                   CASE WHEN COALESCE(l.term_months, 0) <= 12 THEN '211' WHEN l.term_months <= 60 THEN '212' ELSE '213' END
                   || f.loan_group, sum(f.outstanding_principal)
            FROM dwh.fact_loan_balance f JOIN dwh.dim_loan l USING (loan_id)
            WHERE f.snapshot_date = v_snap AND f.status IN ('ACTIVE', 'OVERDUE') GROUP BY 1, 2
        ), cmp AS (
            SELECT COALESCE(d.branch_code, g.branch_code) AS branch_code, COALESCE(d.gl_account, g.gl_account) AS gl_account,
                   COALESCE(g.balance, 0) - COALESCE(d.bal, 0) AS diff
            FROM detail d FULL JOIN (SELECT * FROM dwh.fact_gl_balance WHERE snapshot_date = v_snap) g
                 ON g.branch_code = d.branch_code AND g.gl_account = d.gl_account
        )
        INSERT INTO dq.issue SELECT p_batch, 'GL_RECON', branch_code || '|' || gl_account, 'GL - chi tiết = ' || diff
        FROM cmp WHERE diff <> 0 ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_failed = ROW_COUNT;
        SELECT count(*), COALESCE(sum(abs(split_part(detail, '= ', 2)::numeric)), 0) INTO v_checked, v_amt
        FROM dq.issue WHERE batch_id = p_batch AND rule_code = 'GL_RECON';
        SELECT count(*) INTO v_checked FROM dwh.fact_gl_balance WHERE snapshot_date = v_snap;
        CALL dq.sp_record(p_batch, v_bdate, 'GL_RECON', v_checked, v_failed, v_amt);
    END IF;

    -- ---------------- file trailer check (logged by the Python loader)
    SELECT count(*), count(*) FILTER (WHERE status = 'REJECTED') INTO v_checked, v_failed
    FROM ctl.file_log WHERE batch_id = p_batch;
    INSERT INTO dq.issue SELECT p_batch, 'FILE_TRAILER', file_name, message FROM ctl.file_log
    WHERE batch_id = p_batch AND status = 'REJECTED' ON CONFLICT DO NOTHING;
    CALL dq.sp_record(p_batch, v_bdate, 'FILE_TRAILER', v_checked, v_failed);

    CALL ctl.sp_log_step(p_batch, 'dq_checks', NULL, t0);
END $$;
