-- =====================================================================================
-- Dimension loads (SCD2 for branch & customer, Type 1 upserts for contracts)
-- =====================================================================================

CREATE OR REPLACE PROCEDURE dwh.sp_load_branch(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    DROP TABLE IF EXISTS _b_src;
    CREATE TEMP TABLE _b_src ON COMMIT DROP AS
    SELECT DISTINCT ON (s.branch_code)
           s.branch_code, s.branch_name, s.branch_level, NULLIF(s.parent_branch_code, '') AS parent_branch_code,
           COALESCE(NULLIF(s.parent_branch_code, ''), s.branch_code) AS managing_branch_code,
           s.province_code, p.province_name, p.region, s.district, dwh.f_date(s.open_date) AS open_date,
           s.status, dwh.f_date(s.effective_date) AS eff
    FROM stg.branch s
    LEFT JOIN dwh.map_province_old_new m ON m.old_province_code = s.province_code
    LEFT JOIN dwh.dim_province p ON p.province_code = COALESCE(m.new_province_code, s.province_code)
    ORDER BY s.branch_code, dwh.f_date(s.effective_date) DESC, s._row_no DESC;

    -- province name/region: before 01/07/2025 show the OLD province name
    UPDATE _b_src s SET province_name = m.old_province_name
    FROM dwh.map_province_old_new m
    WHERE m.old_province_code = s.province_code AND s.eff < DATE '2025-07-01';

    -- close changed versions
    UPDATE dwh.dim_branch d SET valid_to = s.eff - 1, is_current = false
    FROM _b_src s
    WHERE d.branch_code = s.branch_code AND d.is_current AND s.eff > d.valid_from
      AND (d.province_code, d.province_name, d.branch_name, d.status, COALESCE(d.parent_branch_code, ''))
          IS DISTINCT FROM (s.province_code, s.province_name, s.branch_name, s.status, COALESCE(s.parent_branch_code, ''));

    INSERT INTO dwh.dim_branch (branch_code, branch_name, branch_level, parent_branch_code, managing_branch_code,
                                province_code, province_name, region, district, open_date, status, valid_from)
    SELECT s.branch_code, s.branch_name, s.branch_level, s.parent_branch_code, s.managing_branch_code,
           s.province_code, s.province_name, s.region, s.district, s.open_date, s.status, s.eff
    FROM _b_src s
    WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_branch d WHERE d.branch_code = s.branch_code AND d.is_current);
    GET DIAGNOSTICS n = ROW_COUNT;
    CALL ctl.sp_log_step(p_batch, 'dim_branch', n, t0);
END $$;


CREATE OR REPLACE PROCEDURE dwh.sp_load_customer(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    -- de-duplicate the extract (the core occasionally sends the same record twice)
    DROP TABLE IF EXISTS _c_src;
    CREATE TEMP TABLE _c_src ON COMMIT DROP AS
    SELECT DISTINCT ON (cif, dwh.f_date(effective_date))
           cif, customer_type, NULLIF(full_name, '') AS full_name, NULLIF(gender, '') AS gender,
           dwh.f_date(date_of_birth) AS date_of_birth, NULLIF(id_number, '') AS id_number,
           NULLIF(tax_code, '') AS tax_code, NULLIF(phone, '') AS phone, province_code, home_branch_code,
           segment, NULLIF(occupation, '') AS occupation, NULLIF(industry, '') AS industry,
           dwh.f_date(open_date) AS open_date, dwh.f_date(close_date) AS close_date, status, record_action,
           CASE WHEN record_action = 'INIT' THEN dwh.f_date(open_date) ELSE dwh.f_date(effective_date) END AS eff
    FROM stg.customer
    ORDER BY cif, dwh.f_date(effective_date), _row_no DESC;
    CREATE INDEX ON _c_src(cif);

    -- process in effective-date order so that several changes in one batch are versioned correctly
    DROP TABLE IF EXISTS _c_ord;
    CREATE TEMP TABLE _c_ord ON COMMIT DROP AS
    SELECT *, row_number() OVER (PARTITION BY cif ORDER BY eff) AS rn FROM _c_src;

    FOR i IN 1..(SELECT COALESCE(max(rn), 0) FROM _c_ord) LOOP
        -- Type 1 attributes
        UPDATE dwh.dim_customer d
        SET full_name = COALESCE(s.full_name, d.full_name), gender = COALESCE(s.gender, d.gender),
            date_of_birth = COALESCE(s.date_of_birth, d.date_of_birth), id_number = COALESCE(s.id_number, d.id_number),
            tax_code = COALESCE(s.tax_code, d.tax_code), phone = COALESCE(s.phone, d.phone),
            occupation = s.occupation, industry = s.industry, close_date = s.close_date
        FROM _c_ord s
        WHERE s.rn = i AND d.cif = s.cif AND d.is_current;

        -- same-day change -> overwrite current version
        UPDATE dwh.dim_customer d
        SET segment = s.segment, province_code = s.province_code, home_branch_code = s.home_branch_code,
            status = s.status, batch_id = p_batch
        FROM _c_ord s
        WHERE s.rn = i AND d.cif = s.cif AND d.is_current AND s.eff <= d.valid_from;

        -- Type 2 attributes changed -> expire current version
        UPDATE dwh.dim_customer d
        SET valid_to = s.eff - 1, is_current = false
        FROM _c_ord s
        WHERE s.rn = i AND d.cif = s.cif AND d.is_current AND s.eff > d.valid_from
          AND (d.segment, d.province_code, d.home_branch_code, d.status)
              IS DISTINCT FROM (s.segment, s.province_code, s.home_branch_code, s.status);

        INSERT INTO dwh.dim_customer (cif, customer_type, full_name, gender, date_of_birth, id_number, tax_code,
                                      phone, province_code, home_branch_code, segment, occupation, industry,
                                      open_date, close_date, status, valid_from, batch_id)
        SELECT s.cif, s.customer_type, s.full_name, s.gender, s.date_of_birth, s.id_number, s.tax_code, s.phone,
               s.province_code, s.home_branch_code, s.segment, s.occupation, s.industry, s.open_date, s.close_date,
               s.status, s.eff, p_batch
        FROM _c_ord s
        WHERE s.rn = i
          AND NOT EXISTS (SELECT 1 FROM dwh.dim_customer d WHERE d.cif = s.cif AND d.is_current);
    END LOOP;
    SELECT count(*) INTO n FROM _c_src;
    CALL ctl.sp_log_step(p_batch, 'dim_customer', n, t0);
END $$;


CREATE OR REPLACE PROCEDURE dwh.sp_load_contracts(p_batch int)
LANGUAGE plpgsql AS $$
DECLARE t0 timestamptz := clock_timestamp(); n bigint;
BEGIN
    -- CASA accounts
    INSERT INTO dwh.dim_casa_account AS d (account_no, cif, product_code, branch_code, open_date, close_date, status, batch_id)
    SELECT DISTINCT ON (account_no) account_no, cif, product_code, branch_code, dwh.f_date(open_date),
           dwh.f_date(close_date), status, p_batch
    FROM stg.casa_account
    ORDER BY account_no, (close_date <> '') DESC, _row_no DESC
    ON CONFLICT (account_no) DO UPDATE
    SET close_date = COALESCE(EXCLUDED.close_date, d.close_date),
        status = CASE WHEN d.status = 'CLOSED' THEN d.status ELSE EXCLUDED.status END,
        batch_id = p_batch;

    -- Term deposits
    INSERT INTO dwh.dim_term_deposit AS d (td_id, cif, product_code, branch_code, open_date, maturity_date, term_months,
                                           interest_rate, principal, rollover_of, close_date, close_reason, batch_id)
    SELECT DISTINCT ON (td_id) td_id, cif, product_code, branch_code, dwh.f_date(open_date), dwh.f_date(maturity_date),
           term_months::smallint, interest_rate::numeric, principal::bigint, NULLIF(rollover_of, ''),
           dwh.f_date(close_date), NULLIF(close_reason, ''), p_batch
    FROM stg.term_deposit
    ORDER BY td_id, (close_date <> '') DESC, _row_no DESC
    ON CONFLICT (td_id) DO UPDATE
    SET close_date = COALESCE(EXCLUDED.close_date, d.close_date),
        close_reason = COALESCE(EXCLUDED.close_reason, d.close_reason), batch_id = p_batch;

    -- Loans
    INSERT INTO dwh.dim_loan AS d (loan_id, cif, product_code, branch_code, disbursement_date, maturity_date, term_months,
                                   term_bucket, approved_amount, interest_rate, repayment_method, collateral_type,
                                   collateral_value, close_date, close_reason, batch_id)
    SELECT DISTINCT ON (loan_id) loan_id, cif, product_code, branch_code, dwh.f_date(disbursement_date),
           dwh.f_date(maturity_date), NULLIF(term_months, '')::smallint,
           CASE WHEN NULLIF(term_months, '') IS NULL OR term_months::int <= 12 THEN 'Ngắn hạn'
                WHEN term_months::int <= 60 THEN 'Trung hạn' ELSE 'Dài hạn' END,
           approved_amount::bigint, dwh.f_num(interest_rate), repayment_method, NULLIF(collateral_type, ''),
           dwh.f_num(collateral_value)::bigint, dwh.f_date(close_date), NULLIF(close_reason, ''), p_batch
    FROM stg.loan
    ORDER BY loan_id, (close_date <> '') DESC, _row_no DESC
    ON CONFLICT (loan_id) DO UPDATE
    SET close_date = COALESCE(EXCLUDED.close_date, d.close_date),
        close_reason = COALESCE(EXCLUDED.close_reason, d.close_reason), batch_id = p_batch;

    -- Cards (ISSUED -> ACTIVE -> CLOSED)
    INSERT INTO dwh.dim_card AS d (card_id, masked_pan, cif, product_code, account_ref, branch_code, issue_date,
                                   activation_date, expiry_date, credit_limit, status, close_date, batch_id)
    SELECT DISTINCT ON (card_id) card_id, masked_pan, cif, product_code, NULLIF(account_ref, ''), branch_code,
           dwh.f_date(issue_date), dwh.f_date(activation_date), dwh.f_date(expiry_date), credit_limit::bigint,
           status, dwh.f_date(close_date), p_batch
    FROM stg.card
    ORDER BY card_id, CASE status WHEN 'CLOSED' THEN 3 WHEN 'ACTIVE' THEN 2 ELSE 1 END DESC, _row_no DESC
    ON CONFLICT (card_id) DO UPDATE
    SET activation_date = COALESCE(EXCLUDED.activation_date, d.activation_date),
        close_date = COALESCE(EXCLUDED.close_date, d.close_date),
        status = CASE WHEN d.status = 'CLOSED' THEN d.status
                      WHEN EXCLUDED.status = 'ISSUED' AND d.status = 'ACTIVE' THEN d.status
                      ELSE EXCLUDED.status END,
        batch_id = p_batch;
    GET DIAGNOSTICS n = ROW_COUNT;
    CALL ctl.sp_log_step(p_batch, 'contracts', n, t0);
END $$;
