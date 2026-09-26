-- =====================================================================================
-- 04. GIAO DỊCH, KÊNH SỐ & THẺ
-- =====================================================================================

-- Q4.1  Dịch chuyển kênh: tỷ trọng giao dịch theo kênh (không tính giao dịch hệ thống)
SELECT month_end,
       round(100.0 * sum(txn_count) FILTER (WHERE channel_code = 'MOBILE') / sum(txn_count), 1) AS mobile_pct,
       round(100.0 * sum(txn_count) FILTER (WHERE channel_code = 'INTERNET') / sum(txn_count), 1) AS internet_pct,
       round(100.0 * sum(txn_count) FILTER (WHERE channel_code = 'POS') / sum(txn_count), 1) AS pos_pct,
       round(100.0 * sum(txn_count) FILTER (WHERE channel_code = 'ATM') / sum(txn_count), 1) AS atm_pct,
       round(100.0 * sum(txn_count) FILTER (WHERE channel_code = 'COUNTER') / sum(txn_count), 1) AS quay_pct
FROM mart.channel_month
WHERE channel_code <> 'SYSTEM'
GROUP BY month_end ORDER BY month_end;

-- Q4.2  SỰ KIỆN TẾT: số lượt rút tiền ATM theo ngày quanh Tết Ất Tỵ (mùng 1 = 29/01/2025)
SELECT report_date, to_char(report_date, 'Dy') AS thu, sum(onus_wd_count + offus_wd_count) AS luot_rut,
       round(sum(onus_wd_amount + offus_wd_amount) / 1e9, 2) AS so_tien_ty
FROM dwh.fact_atm_daily
WHERE report_date BETWEEN '2025-01-10' AND '2025-02-05'
GROUP BY report_date ORDER BY report_date;

-- Q4.3  Giao dịch mobile theo giờ trong ngày (hai đỉnh: trưa và tối)
SELECT extract(hour FROM txn_datetime)::int AS gio, count(*) AS so_gd
FROM dwh.fact_casa_txn
WHERE channel_code = 'MOBILE' AND business_date BETWEEN '2026-07-01' AND '2026-07-31'
GROUP BY 1 ORDER BY 1;

-- Q4.4  Giao dịch cuối tuần được hạch toán vào ngày làm việc kế tiếp (business_date ≠ ngày giao dịch)
SELECT txn_datetime::date AS ngay_gd, to_char(txn_datetime, 'Dy') AS thu, business_date AS ngay_hach_toan, count(*) AS so_gd
FROM dwh.fact_casa_txn
WHERE txn_datetime >= '2026-08-07' AND txn_datetime < '2026-08-11'
GROUP BY 1, 2, 3 ORDER BY 1;

-- Q4.5  Thưởng tháng 13 trước Tết: tổng tiền lương chi qua tài khoản theo tháng
SELECT to_char(business_date, 'YYYY-MM') AS thang, count(*) AS so_lan_chi_luong, round(sum(amount) / 1e9, 1) AS tong_ty
FROM dwh.fact_casa_txn WHERE txn_type = 'PAYROLL'
GROUP BY 1 ORDER BY 1;

-- Q4.6  SỰ KIỆN: chiến dịch thẻ tín dụng Q2/2025 - phát hành tăng nhưng kích hoạt thấp
SELECT to_char(issue_date, 'YYYY-MM') AS thang_phat_hanh, count(*) AS so_the,
       count(activation_date) AS da_kich_hoat,
       round(100.0 * count(activation_date) / count(*), 0) AS ty_le_kich_hoat_pct
FROM dwh.dim_card
WHERE product_code LIKE 'CD_CREDIT%' AND issue_date BETWEEN '2024-10-01' AND '2025-12-31'
GROUP BY 1 ORDER BY 1;

-- Q4.7  Chi tiêu thẻ tín dụng theo nhóm ngành hàng (12 tháng gần nhất)
SELECT mcc_group, sum(txn_count) AS so_gd, round(sum(amount) / 1e9, 2) AS chi_tieu_ty,
       round(sum(amount) / NULLIF(sum(txn_count), 0) / 1e3) AS gia_tri_bq_nghin,
       round(100.0 * sum(ecom_count) / NULLIF(sum(txn_count), 0), 0) AS online_pct
FROM mart.card_spend_month
WHERE month_end > '2025-08-31'
GROUP BY 1 ORDER BY chi_tieu_ty DESC;

-- Q4.8  Top 5 khách hàng chi tiêu thẻ nhiều nhất năm 2025 (xếp hạng bằng RANK)
WITH s AS (
    SELECT c.cif, sum(t.amount) AS chi_tieu
    FROM dwh.fact_card_txn t JOIN dwh.dim_card c USING (card_id)
    WHERE t.auth_status = 'APPROVED' AND t.business_date BETWEEN '2025-01-01' AND '2025-12-31'
    GROUP BY c.cif)
SELECT RANK() OVER (ORDER BY chi_tieu DESC) AS hang, m.display_name, m.segment, round(s.chi_tieu / 1e6) AS chi_tieu_trieu
FROM s JOIN mart.v_customer_masked m USING (cif)
ORDER BY hang LIMIT 5;
