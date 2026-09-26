-- =====================================================================================
-- Fact loads. All loads are idempotent (re-running a batch gives the same result).
-- =====================================================================================

CREATE OR REPLACE PROCEDURE dwh.sp_load_casa_txn(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    INSERT INTO dwh.fact_casa_txn (txn_id, account_no, txn_datetime, business_date, date_key, txn_type, dr_cr, amount,
                                   signed_amount, channel_code, branch_code, atm_id, counterparty_bank, description,
                                   is_reversal, batch_id)
    SELECT DISTINCT ON (txn_id, dwh.f_date(business_date))
           txn_id, account_no, dwh.f_ts(txn_datetime), dwh.f_date(business_date),
           to_char(dwh.f_date(business_date), 'YYYYMMDD')::int, txn_type, dr_cr, amount::bigint,
           CASE WHEN dr_cr = 'C' THEN amount::bigint ELSE -amount::bigint END,
           channel_code, branch_code, NULLIF(atm_id, ''), NULLIF(counterparty_bank, ''), description,
           is_reversal = '1', p_batch
    FROM stg.txn
    ORDER BY txn_id, dwh.f_date(business_date), _row_no
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    CALL ctl.sp_log_step(p_batch, 'fact_casa_txn', n, t0);
END $$;


CREATE OR REPLACE PROCEDURE dwh.sp_load_snapshots(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    INSERT INTO dwh.fact_casa_balance AS f (snapshot_date, account_no, balance, accrued_interest, status, batch_id)
    SELECT dwh.f_date(snapshot_date), account_no, balance::bigint, accrued_interest::bigint, status, p_batch
    FROM stg.casa_balance
    ON CONFLICT (snapshot_date, account_no) DO UPDATE
    SET balance = EXCLUDED.balance, status = EXCLUDED.status, batch_id = p_batch;

    INSERT INTO dwh.fact_td_balance AS f (snapshot_date, td_id, principal, accrued_interest, status, batch_id)
    SELECT dwh.f_date(snapshot_date), td_id, principal::bigint, accrued_interest::bigint, status, p_batch
    FROM stg.td_balance
    ON CONFLICT (snapshot_date, td_id) DO UPDATE
    SET principal = EXCLUDED.principal, accrued_interest = EXCLUDED.accrued_interest, batch_id = p_batch;

    -- Loans: recompute the group from DPD, apply CIC group, compute provisions
    INSERT INTO dwh.fact_loan_balance AS f (snapshot_date, loan_id, outstanding_principal, overdue_principal, dpd,
                                            core_loan_group, cic_group, dpd_group, loan_group, accrued_interest,
                                            specific_provision, general_provision, status, batch_id)
    SELECT x.snapshot_date, x.loan_id, x.outstanding, x.overdue, x.dpd, x.core_group, x.cic_group, x.dpd_group,
           x.final_group, x.accrued,
           CASE WHEN x.status IN ('ACTIVE', 'OVERDUE') THEN
                round(g.specific_provision_rate *
                      greatest(0, x.outstanding - COALESCE(l.collateral_value, 0) * COALESCE(cf.deduction_rate, 0)))
                ELSE 0 END,
           CASE WHEN x.status IN ('ACTIVE', 'OVERDUE') AND x.final_group <= 4 THEN round(0.0075 * x.outstanding)
                ELSE 0 END,
           x.status, p_batch
    FROM (
        SELECT dwh.f_date(snapshot_date) AS snapshot_date, loan_id, outstanding_principal::bigint AS outstanding,
               overdue_principal::bigint AS overdue, dpd::int AS dpd, loan_group::smallint AS core_group,
               NULLIF(cic_group, '0')::smallint AS cic_group, dwh.f_dpd_group(dpd::int) AS dpd_group,
               greatest(dwh.f_dpd_group(dpd::int), COALESCE(NULLIF(cic_group, '0')::smallint, 1))::smallint AS final_group,
               accrued_interest::bigint AS accrued, status
        FROM stg.loan_balance
    ) x
    JOIN dwh.dim_loan_group g ON g.loan_group = x.final_group
    LEFT JOIN dwh.dim_loan l ON l.loan_id = x.loan_id
    LEFT JOIN dwh.ref_collateral_factor cf ON cf.collateral_type = l.collateral_type
    ON CONFLICT (snapshot_date, loan_id) DO UPDATE
    SET outstanding_principal = EXCLUDED.outstanding_principal, overdue_principal = EXCLUDED.overdue_principal,
        dpd = EXCLUDED.dpd, core_loan_group = EXCLUDED.core_loan_group, cic_group = EXCLUDED.cic_group,
        dpd_group = EXCLUDED.dpd_group, loan_group = EXCLUDED.loan_group,
        specific_provision = EXCLUDED.specific_provision, general_provision = EXCLUDED.general_provision,
        status = EXCLUDED.status, batch_id = p_batch;

    INSERT INTO dwh.fact_gl_balance AS f (snapshot_date, branch_code, gl_account, balance, batch_id)
    SELECT dwh.f_date(snapshot_date), branch_code, gl_account, balance::bigint, p_batch
    FROM stg.gl_balance
    ON CONFLICT (snapshot_date, branch_code, gl_account) DO UPDATE SET balance = EXCLUDED.balance, batch_id = p_batch;
    GET DIAGNOSTICS n = ROW_COUNT;
    CALL ctl.sp_log_step(p_batch, 'snapshots', n, t0);
END $$;


CREATE OR REPLACE PROCEDURE dwh.sp_load_cards_ops(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    INSERT INTO dwh.fact_card_txn (card_txn_id, card_id, txn_datetime, business_date, date_key, mcc, merchant_name,
                                   amount, is_ecommerce, is_international, auth_status, batch_id)
    SELECT card_txn_id, card_id, dwh.f_ts(txn_datetime), dwh.f_date(business_date),
           to_char(dwh.f_date(business_date), 'YYYYMMDD')::int, mcc, merchant_name, amount::bigint,
           is_ecommerce = '1', is_international = '1', auth_status, p_batch
    FROM stg.card_txn
    ON CONFLICT (card_txn_id) DO NOTHING;

    INSERT INTO dwh.dim_atm (atm_id, branch_code, first_seen)
    SELECT atm_id, min(branch_code), min(dwh.f_date(business_date)) FROM stg.atm_daily GROUP BY atm_id
    ON CONFLICT (atm_id) DO NOTHING;

    INSERT INTO dwh.fact_atm_daily AS f (report_date, atm_id, branch_code, onus_wd_count, onus_wd_amount, offus_wd_count,
                                         offus_wd_amount, uptime_minutes, uptime_pct, incident_count, cash_out_flag, batch_id)
    SELECT dwh.f_date(business_date), atm_id, branch_code, onus_wd_count::int, onus_wd_amount::bigint,
           offus_wd_count::int, offus_wd_amount::bigint, uptime_minutes::int, uptime_minutes::numeric / 1440,
           incident_count::int, cash_out_flag = '1', p_batch
    FROM stg.atm_daily
    ON CONFLICT (report_date, atm_id) DO NOTHING;

    INSERT INTO dwh.fact_branch_ops (business_date, branch_code, tellers, counter_txn_count, service_request_count,
                                     avg_wait_minutes, avg_service_minutes, pct_wait_under_15m, batch_id)
    SELECT dwh.f_date(business_date), branch_code, tellers::int, counter_txn_count::int, service_request_count::int,
           avg_wait_minutes::numeric, avg_service_minutes::numeric, pct_wait_under_15m::numeric, p_batch
    FROM stg.branch_ops
    ON CONFLICT (business_date, branch_code) DO NOTHING;

    -- Complaints: accumulating snapshot (insert on receipt, update on resolution)
    INSERT INTO dwh.fact_complaint AS f (complaint_id, cif, branch_code, received_datetime, received_date, channel,
                                         complaint_type, sla_days, sla_due_date, resolved_datetime, resolution_bdays,
                                         is_sla_breached, status, is_valid, batch_id)
    SELECT DISTINCT ON (s.complaint_id)
           s.complaint_id, s.cif, s.branch_code, dwh.f_ts(s.received_datetime), dwh.f_ts(s.received_datetime)::date,
           s.channel, s.complaint_type, s.sla_days::int,
           dwh.f_add_business_days(dwh.f_ts(s.received_datetime)::date, s.sla_days::int),
           dwh.f_ts(s.resolved_datetime), NULL, NULL, s.status, NULLIF(s.is_valid, ''), p_batch
    FROM stg.complaint s
    ORDER BY s.complaint_id, (s.status = 'CLOSED') DESC, s._row_no DESC
    ON CONFLICT (complaint_id) DO UPDATE
    SET resolved_datetime = COALESCE(EXCLUDED.resolved_datetime, f.resolved_datetime),
        status = CASE WHEN f.status = 'CLOSED' THEN f.status ELSE EXCLUDED.status END,
        is_valid = COALESCE(EXCLUDED.is_valid, f.is_valid), batch_id = p_batch;

    UPDATE dwh.fact_complaint c
    SET resolution_bdays = r.business_day_seq - d.business_day_seq,
        is_sla_breached = c.resolved_datetime::date > c.sla_due_date
    FROM dwh.dim_date d, dwh.dim_date r
    WHERE c.batch_id = p_batch AND c.resolved_datetime IS NOT NULL
      AND d.full_date = dwh.f_next_business_day(c.received_date) AND r.full_date = c.resolved_datetime::date;
    GET DIAGNOSTICS n = ROW_COUNT;
    CALL ctl.sp_log_step(p_batch, 'cards_ops_complaints', n, t0);
END $$;
