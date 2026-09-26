-- =====================================================================================
-- 06. KẾ HOẠCH vs THỰC HIỆN & CHẤT LƯỢNG DỮ LIỆU
-- =====================================================================================

-- Q6.1  Thực hiện so với kế hoạch toàn hàng (kế hoạch nạp từ file Excel)
SELECT month_end,
       round(sum(deposit_balance) / 1e9) AS huy_dong_ty, round(sum(plan_deposit) / 1e9) AS kh_huy_dong_ty,
       round(100 * sum(deposit_balance) / sum(plan_deposit), 1) AS ht_huy_dong_pct,
       round(sum(loan_balance) / 1e9) AS du_no_ty, round(sum(plan_loan) / 1e9) AS kh_du_no_ty,
       round(100 * sum(loan_balance) / sum(plan_loan), 1) AS ht_du_no_pct
FROM mart.kpi_branch_month
WHERE plan_deposit IS NOT NULL
GROUP BY month_end ORDER BY month_end;

-- Q6.2  Xếp hạng chi nhánh theo % hoàn thành kế hoạch dư nợ tại 31/08/2026 (cây xếp hạng thi đua)
SELECT RANK() OVER (ORDER BY sum(k.loan_balance) / sum(k.plan_loan) DESC) AS hang,
       b.managing_branch_name AS chi_nhanh,
       round(100 * sum(k.loan_balance) / sum(k.plan_loan), 1) AS ht_du_no_pct,
       round(100 * sum(k.deposit_balance) / sum(k.plan_deposit), 1) AS ht_huy_dong_pct,
       round(100.0 * sum(k.npl_balance) / NULLIF(sum(k.loan_balance), 0), 2) AS npl_pct
FROM mart.kpi_branch_month k JOIN mart.v_branch b USING (branch_code)
WHERE k.month_end = '2026-08-31'
GROUP BY b.managing_branch_name ORDER BY hang;

-- Q6.3  Tổng hợp chất lượng dữ liệu: quy tắc nào phát hiện lỗi, bao nhiêu bản ghi
SELECT rule_code, severity, description, sum(failed_rows) AS so_loi,
       count(*) FILTER (WHERE status = 'FAIL') AS so_lo_fail
FROM mart.v_dq_summary
GROUP BY rule_code, severity, description ORDER BY so_loi DESC;

-- Q6.4  Chi tiết đối chiếu sổ cái (GL) lệch với số liệu chi tiết - 4 khoản mục cần giải trình
SELECT r.business_date AS ngay, split_part(i.record_key, '|', 1) AS chi_nhanh,
       split_part(i.record_key, '|', 2) AS tk_gl, i.detail
FROM dq.issue i JOIN dq.result r USING (batch_id, rule_code)
WHERE i.rule_code = 'GL_RECON' ORDER BY 1;

-- Q6.5  Mẫu bản ghi lỗi của từng quy tắc (3 dòng/quy tắc) - dùng ROW_NUMBER
SELECT rule_code, record_key, detail
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY rule_code ORDER BY record_key) AS rn FROM dq.issue) x
WHERE rn <= 3 ORDER BY rule_code, rn;

-- Q6.6  Lỗi nguồn lan xuống đối chiếu: giao dịch số tiền âm -> tài khoản lệch roll-forward
SELECT i.record_key AS txn_id, t.account_no, t.amount, t.dr_cr, t.business_date
FROM dq.issue i JOIN dwh.fact_casa_txn t ON t.txn_id = i.record_key
WHERE i.rule_code = 'TXN_NEG_AMOUNT' LIMIT 10;
