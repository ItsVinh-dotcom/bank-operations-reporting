-- =====================================================================================
-- 03. TÍN DỤNG & RỦI RO
-- Nhóm nợ theo số ngày quá hạn (DPD): N1 ≤9 | N2 10-90 | N3 91-180 | N4 181-360 | N5 >360 ngày.
-- Nợ xấu (NPL) = nhóm 3-5. Dự phòng cụ thể 0/5/20/50/100% phần dư nợ sau khi trừ tài sản đảm bảo.
-- =====================================================================================

-- Q3.1  Dư nợ, nợ xấu, LDR, tỷ lệ bao phủ nợ xấu theo tháng
SELECT month_end, round(loan_balance / 1e9, 1) AS du_no_ty, round(npl_ratio * 100, 2) AS npl_pct,
       round(ldr * 100, 1) AS ldr_pct, round(llr_coverage * 100, 0) AS bao_phu_pct,
       round(writeoff_amount / 1e9, 2) AS xu_ly_rui_ro_ty
FROM mart.v_kpi_bank_month ORDER BY month_end;

-- Q3.2  Cơ cấu dư nợ và nợ xấu theo sản phẩm (31/08/2026)
SELECT l.product_code, count(*) AS so_khoan_vay,
       round(sum(f.outstanding_principal) / 1e9, 1) AS du_no_ty,
       round(100.0 * sum(f.outstanding_principal) / sum(sum(f.outstanding_principal)) OVER (), 1) AS ty_trong_pct,
       round(100.0 * sum(f.outstanding_principal) FILTER (WHERE f.loan_group >= 3) / sum(f.outstanding_principal), 2) AS npl_pct
FROM dwh.fact_loan_balance f JOIN dwh.dim_loan l USING (loan_id)
WHERE f.snapshot_date = '2026-08-31' AND f.status IN ('ACTIVE', 'OVERDUE')
GROUP BY 1 ORDER BY du_no_ty DESC;
-- Nhận xét: vay không có TSĐB (tiêu dùng, thẻ) có nợ xấu cao hơn vay mua nhà.

-- Q3.3  SỰ KIỆN: nợ xấu cụm Cần Thơ tăng mạnh năm 2025 (so với toàn hàng)
SELECT k.month_end,
       round(100.0 * sum(k.npl_balance) FILTER (WHERE b.managing_branch_code = '400')
             / NULLIF(sum(k.loan_balance) FILTER (WHERE b.managing_branch_code = '400'), 0), 2) AS npl_can_tho_pct,
       round(100.0 * sum(k.npl_balance) / sum(k.loan_balance), 2) AS npl_toan_hang_pct
FROM mart.kpi_branch_month k JOIN mart.v_branch b USING (branch_code)
WHERE k.month_end BETWEEN '2024-10-31' AND '2026-03-31'
GROUP BY k.month_end ORDER BY k.month_end;

-- Q3.4  Ma trận chuyển nhóm nợ tháng 06/2025 (hàng = nhóm đầu tháng, cột = nhóm cuối tháng), theo số khoản vay
SELECT from_state AS dau_thang,
       sum(loan_count) FILTER (WHERE to_state = 'Nhóm 1') AS "N1",
       sum(loan_count) FILTER (WHERE to_state = 'Nhóm 2') AS "N2",
       sum(loan_count) FILTER (WHERE to_state = 'Nhóm 3') AS "N3",
       sum(loan_count) FILTER (WHERE to_state = 'Nhóm 4') AS "N4",
       sum(loan_count) FILTER (WHERE to_state = 'Nhóm 5') AS "N5",
       sum(loan_count) FILTER (WHERE to_state = 'Tất toán') AS "Tất toán",
       sum(loan_count) FILTER (WHERE to_state IN ('Xử lý rủi ro', 'Thu hồi TSĐB')) AS "XLRR/Thu hồi"
FROM mart.loan_migration
WHERE month_end = '2025-06-30' AND product_code <> 'LN_CREDITCARD'
GROUP BY from_state ORDER BY from_state;

-- Q3.5  Tỷ lệ "roll rate" N1 -> N2 theo tháng: chỉ báo sớm của nợ xấu
SELECT month_end,
       round(100.0 * sum(amount_from) FILTER (WHERE from_state = 'Nhóm 1' AND to_state = 'Nhóm 2')
             / NULLIF(sum(amount_from) FILTER (WHERE from_state = 'Nhóm 1'), 0), 3) AS roll_n1_n2_pct
FROM mart.loan_migration GROUP BY month_end ORDER BY month_end;

-- Q3.6  Top 10 khoản vay quá hạn lớn nhất hiện tại (danh sách cho bộ phận thu hồi nợ)
SELECT f.loan_id, l.product_code, l.branch_code, c.display_name, f.dpd, f.loan_group,
       round(f.outstanding_principal / 1e6) AS du_no_trieu, round(l.collateral_value / 1e6) AS tsdb_trieu,
       round(f.specific_provision / 1e6) AS du_phong_trieu
FROM dwh.fact_loan_balance f
JOIN dwh.dim_loan l USING (loan_id)
JOIN mart.v_customer_masked c USING (cif)
WHERE f.snapshot_date = '2026-08-31' AND f.status = 'OVERDUE'
ORDER BY f.outstanding_principal DESC LIMIT 10;

-- Q3.7  Nhóm nợ theo CIC: khoản vay trả đúng hạn tại DLB nhưng bị nâng nhóm do nợ ở ngân hàng khác
SELECT snapshot_date, count(*) AS so_khoan, round(sum(outstanding_principal) / 1e9, 2) AS du_no_ty
FROM dwh.fact_loan_balance
WHERE cic_group IS NOT NULL AND dpd_group < loan_group
GROUP BY 1 ORDER BY 1 DESC LIMIT 6;

-- Q3.8  Giải ngân mới theo tháng: dồn vào cuối tháng/cuối quý ("chạy chỉ tiêu")
SELECT to_char(disbursement_date, 'YYYY-MM') AS thang,
       round(sum(approved_amount) / 1e9, 1) AS giai_ngan_ty,
       round(100.0 * sum(approved_amount) FILTER (WHERE extract(day FROM disbursement_date) >= 21)
             / sum(approved_amount), 0) AS pct_10_ngay_cuoi
FROM dwh.dim_loan
WHERE disbursement_date >= '2024-01-01' AND product_code <> 'LN_CREDITCARD'
GROUP BY 1 ORDER BY 1;
