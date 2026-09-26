-- =====================================================================================
-- 02. HUY ĐỘNG VỐN (TIỀN GỬI)
-- CASA = tiền gửi không kỳ hạn (tài khoản thanh toán) -> vốn rẻ. TD = tiền gửi có kỳ hạn.
-- Tỷ lệ CASA = CASA / tổng tiền gửi: càng cao, chi phí vốn càng thấp.
-- =====================================================================================

-- Q2.1  Tổng huy động cuối tháng, tỷ lệ CASA, tăng trưởng so với cùng kỳ (window function LAG)
SELECT month_end,
       round(casa_balance / 1e9, 1)    AS casa_ty,
       round(td_balance / 1e9, 1)      AS td_ty,
       round(deposit_balance / 1e9, 1) AS tong_ty,
       round(casa_ratio * 100, 1)      AS casa_pct,
       round(100.0 * (deposit_balance / LAG(deposit_balance, 12) OVER (ORDER BY month_end) - 1), 1) AS tang_yoy_pct
FROM mart.v_kpi_bank_month
ORDER BY month_end;
-- Nhận xét: tỷ lệ CASA nhích lên vào tháng 3, 6, 9, 12 do doanh nghiệp "chạy số" cuối quý.

-- Q2.2  Bằng chứng "chạy số cuối quý": số dư CASA doanh nghiệp theo ngày quanh 30/06/2025
SELECT balance_date, round(sum(balance) / 1e9, 2) AS casa_dn_ty
FROM mart.deposit_daily
WHERE product_code = 'CASA_SME' AND balance_date BETWEEN '2025-06-24' AND '2025-07-04'
GROUP BY balance_date ORDER BY balance_date;

-- Q2.3  Cơ cấu tiền gửi có kỳ hạn theo kỳ hạn và lãi suất bình quân (31/08/2026)
SELECT t.term_months AS ky_han_thang, t.product_code, count(*) AS so_hd,
       round(sum(f.principal) / 1e9, 1) AS so_du_ty,
       round(sum(f.principal * t.interest_rate) / sum(f.principal), 2) AS ls_binh_quan
FROM dwh.fact_td_balance f JOIN dwh.dim_term_deposit t USING (td_id)
WHERE f.snapshot_date = '2026-08-31'
GROUP BY 1, 2 ORDER BY 1, 2;

-- Q2.4  Diễn biến lãi suất huy động 12 tháng theo tháng mở sổ (so với mặt bằng thị trường)
SELECT to_char(open_date, 'YYYY-MM') AS thang_mo, count(*) AS so_so_moi,
       round(avg(interest_rate) FILTER (WHERE product_code = 'TD_COUNTER'), 2) AS ls_tai_quay,
       round(avg(interest_rate) FILTER (WHERE product_code = 'TD_ONLINE'), 2) AS ls_online
FROM dwh.dim_term_deposit
WHERE term_months = 12 AND open_date >= '2024-01-01'
GROUP BY 1 ORDER BY 1;

-- Q2.5  Thang đáo hạn tiền gửi: bao nhiêu tiền sẽ đến hạn trong 7/30/90 ngày tới (góc nhìn thanh khoản)
SELECT bucket AS khoang_dao_han, sum(contracts) AS so_hd, round(sum(principal) / 1e9, 1) AS so_tien_ty
FROM mart.v_td_maturity_ladder GROUP BY bucket ORDER BY bucket;

-- Q2.6  Hành vi khi đáo hạn: tái tục, rút, rút trước hạn
SELECT COALESCE(close_reason, 'Đang hiệu lực') AS trang_thai, count(*) AS so_hd,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM dwh.dim_term_deposit GROUP BY 1 ORDER BY 2 DESC;

-- Q2.7  Báo cáo huy động ngày T-1 cho giám đốc chi nhánh (biến động so với hôm qua, đầu tháng, đầu năm)
SELECT managing_branch_name AS chi_nhanh, product_type,
       round(sum(bal_t) / 1e9, 2) AS so_du_ty, round(sum(chg_dod) / 1e6, 0) AS bd_ngay_trieu,
       round(sum(chg_mtd) / 1e9, 2) AS bd_thang_ty, round(sum(chg_ytd) / 1e9, 2) AS bd_nam_ty
FROM mart.v_daily_deposit_report
GROUP BY 1, 2 ORDER BY 1, 2;
