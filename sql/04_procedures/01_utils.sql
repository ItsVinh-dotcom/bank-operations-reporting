-- =====================================================================================
-- Utility functions
-- =====================================================================================

-- 'YYYYMMDD' -> date (empty -> NULL)
CREATE OR REPLACE FUNCTION dwh.f_date(p text) RETURNS date
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p IS NULL OR btrim(p) = '' THEN NULL ELSE to_date(p, 'YYYYMMDD') END
$$;

-- 'YYYY-MM-DD HH24:MI:SS' -> timestamp (empty -> NULL)
CREATE OR REPLACE FUNCTION dwh.f_ts(p text) RETURNS timestamp
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p IS NULL OR btrim(p) = '' THEN NULL ELSE p::timestamp END
$$;

CREATE OR REPLACE FUNCTION dwh.f_num(p text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p IS NULL OR btrim(p) = '' THEN NULL ELSE p::numeric END
$$;

-- Loan group from days past due (Vietnamese 5-group classification, quantitative method)
CREATE OR REPLACE FUNCTION dwh.f_dpd_group(p_dpd int) RETURNS smallint
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_dpd <= 9 THEN 1 WHEN p_dpd <= 90 THEN 2 WHEN p_dpd <= 180 THEN 3
                WHEN p_dpd <= 360 THEN 4 ELSE 5 END::smallint
$$;

CREATE OR REPLACE FUNCTION dwh.f_next_business_day(p date) RETURNS date
LANGUAGE sql STABLE AS $$
    SELECT min(full_date) FROM dwh.dim_date WHERE full_date >= p AND is_business_day
$$;

-- Add N business days (N >= 0). Uses dim_date.business_day_seq.
CREATE OR REPLACE FUNCTION dwh.f_add_business_days(p date, n int) RETURNS date
LANGUAGE sql STABLE AS $$
    SELECT d2.full_date
    FROM dwh.dim_date d1
    JOIN dwh.dim_date d2 ON d2.business_day_seq = d1.business_day_seq + n AND d2.is_business_day
    WHERE d1.full_date = dwh.f_next_business_day(p)
$$;

-- Build the date dimension
CREATE OR REPLACE PROCEDURE dwh.sp_build_dim_date(p_from date, p_to date)
LANGUAGE plpgsql AS $$
BEGIN
    TRUNCATE dwh.dim_date;
    INSERT INTO dwh.dim_date
    SELECT to_char(d, 'YYYYMMDD')::int,
           d::date,
           extract(day FROM d)::smallint,
           extract(isodow FROM d)::smallint,
           (ARRAY['Thứ Hai','Thứ Ba','Thứ Tư','Thứ Năm','Thứ Sáu','Thứ Bảy','Chủ Nhật'])[extract(isodow FROM d)],
           extract(week FROM d)::smallint,
           extract(month FROM d)::smallint,
           'Tháng ' || extract(month FROM d)::int,
           extract(quarter FROM d)::smallint,
           extract(year FROM d)::smallint,
           to_char(d, 'YYYY-MM'),
           date_trunc('month', d)::date,
           (date_trunc('month', d) + interval '1 month - 1 day')::date,
           extract(isodow FROM d) >= 6,
           h.holiday_date IS NOT NULL,
           h.holiday_name,
           extract(isodow FROM d) < 6 AND h.holiday_date IS NULL,
           d::date = (date_trunc('month', d) + interval '1 month - 1 day')::date,
           d::date = (date_trunc('quarter', d) + interval '3 month - 1 day')::date,
           0
    FROM generate_series(p_from, p_to, interval '1 day') d
    LEFT JOIN dwh.ref_holiday h ON h.holiday_date = d::date;

    UPDATE dwh.dim_date t
    SET business_day_seq = s.seq
    FROM (SELECT full_date, sum(CASE WHEN is_business_day THEN 1 ELSE 0 END)
                 OVER (ORDER BY full_date) AS seq FROM dwh.dim_date) s
    WHERE s.full_date = t.full_date;
END $$;

-- step logger
CREATE OR REPLACE PROCEDURE ctl.sp_log_step(p_batch int, p_step text, p_rows bigint, p_start timestamptz)
LANGUAGE sql AS $$
    INSERT INTO ctl.step_log(batch_id, step, rows_affected, started_at) VALUES (p_batch, p_step, p_rows, p_start);
$$;
