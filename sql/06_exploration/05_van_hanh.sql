-- =====================================================================================
-- 05. VẬN HÀNH: ATM, QUẦY GIAO DỊCH, KHIẾU NẠI
-- =====================================================================================

-- Q5.1  SỰ KIỆN: sự cố ATM cụm CN Sài Gòn (110/111/112) tháng 9-10/2025 so với phần còn lại
SELECT to_char(report_date, 'YYYY-MM') AS thang,
       round(100 * avg(uptime_pct) FILTER (WHERE branch_code IN ('110', '111', '112')), 2) AS uptime_cum_sai_gon,
       round(100 * avg(uptime_pct) FILTER (WHERE branch_code NOT IN ('110', '111', '112')), 2) AS uptime_con_lai,
       sum(incident_count) FILTER (WHERE branch_code IN ('110', '111', '112')) AS su_co_sai_gon
FROM dwh.fact_atm_daily
WHERE report_date BETWEEN '2025-07-01' AND '2025-12-31'
GROUP BY 1 ORDER BY 1;

-- Q5.2  ATM hết tiền: dồn vào dịp trước Tết
SELECT to_char(report_date, 'YYYY-MM') AS thang, sum(cash_out_flag::int) AS so_lan_het_tien
FROM dwh.fact_atm_daily GROUP BY 1 HAVING sum(cash_out_flag::int) > 20 ORDER BY 1;

-- Q5.3  Thời gian chờ tại quầy theo chi nhánh (năm 2025), trung vị và P90 bằng percentile_cont
SELECT b.managing_branch_name AS chi_nhanh,
       round(avg(o.avg_wait_minutes), 1) AS cho_tb_phut,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY o.avg_wait_minutes)::numeric, 1) AS trung_vi,
       round(percentile_cont(0.9) WITHIN GROUP (ORDER BY o.avg_wait_minutes)::numeric, 1) AS p90,
       round(100 * avg(o.pct_wait_under_15m), 1) AS pct_duoi_15p
FROM dwh.fact_branch_ops o JOIN mart.v_branch b USING (branch_code)
WHERE o.business_date BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY 1 ORDER BY cho_tb_phut DESC;

-- Q5.4  Thời gian chờ theo thứ trong tuần (thứ Hai và đầu tháng đông nhất)
SELECT d.day_of_week, d.day_name_vi, round(avg(o.avg_wait_minutes), 2) AS cho_tb_phut
FROM dwh.fact_branch_ops o JOIN dwh.dim_date d ON d.full_date = o.business_date
GROUP BY 1, 2 ORDER BY 1;

-- Q5.5  Khiếu nại theo loại: số lượng, SLA, tỷ lệ vi phạm SLA, thời gian xử lý bình quân
SELECT complaint_type AS loai, count(*) AS so_kn, max(sla_days) AS sla_ngay_lv,
       round(avg(resolution_bdays), 1) AS xu_ly_tb_ngay_lv,
       round(100.0 * count(*) FILTER (WHERE is_sla_breached) / NULLIF(count(resolved_datetime), 0), 1) AS vi_pham_sla_pct
FROM dwh.fact_complaint GROUP BY 1 ORDER BY so_kn DESC;

-- Q5.6  SỰ KIỆN: khiếu nại lỗi ứng dụng tăng vọt sau bản nâng cấp tháng 3/2026
SELECT received_date, count(*) FILTER (WHERE complaint_type = 'LOI_UNG_DUNG') AS loi_app, count(*) AS tong
FROM dwh.fact_complaint
WHERE received_date BETWEEN '2026-03-02' AND '2026-03-25'
GROUP BY 1 ORDER BY 1;

-- Q5.7  Khiếu nại đang mở tại ngày dữ liệu cuối cùng, sắp/đã quá hạn SLA
SELECT complaint_id, branch_code, complaint_type, received_date, sla_due_date,
       CASE WHEN sla_due_date < DATE '2026-08-31' THEN 'Quá hạn' ELSE 'Trong hạn' END AS tinh_trang
FROM dwh.fact_complaint WHERE status = 'OPEN'
ORDER BY sla_due_date LIMIT 20;
