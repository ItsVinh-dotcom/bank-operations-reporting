-- =====================================================================================
-- 00. LÀM QUEN VỚI KHO DỮ LIỆU
-- Mục tiêu: biết có những schema/bảng nào, bao nhiêu dữ liệu, ETL đã chạy ra sao.
-- Cách chạy: bôi đen từng câu (từ SELECT đến dấu ;) rồi bấm F5 (pgAdmin) hoặc Ctrl+Enter (DBeaver/VS Code).
-- =====================================================================================

-- Q0.1  Các tầng dữ liệu và số bảng mỗi tầng
--   stg  = nơi "hạ cánh" file thô từ core (xóa sạch mỗi lô)
--   dwh  = kho chuẩn hóa: dim_* (danh mục) và fact_* (sự kiện/số dư)
--   mart = bảng tổng hợp sẵn cho báo cáo (Power BI dùng tầng này)
--   dq   = kiểm soát chất lượng dữ liệu, ctl = nhật ký chạy lô
SELECT table_schema, count(*) AS so_bang
FROM information_schema.tables
WHERE table_schema IN ('stg', 'dwh', 'mart', 'dq', 'ctl')
GROUP BY table_schema
ORDER BY table_schema;

-- Q0.2  Số dòng của từng bảng trong dwh và mart (ước lượng nhanh từ thống kê của PostgreSQL)
SELECT schemaname AS schema, relname AS bang, n_live_tup AS so_dong_uoc_tinh
FROM pg_stat_user_tables
WHERE schemaname IN ('dwh', 'mart') AND relname NOT LIKE 'fact_casa_txn_%'
ORDER BY schemaname, n_live_tup DESC;

-- Q0.3  Nhật ký lô ETL: 33 lô lịch sử (tháng) + 21 lô EOD (ngày làm việc tháng 8/2026)
SELECT batch_type, count(*) AS so_lo, min(business_date) AS tu_ngay, max(business_date) AS den_ngay,
       count(*) FILTER (WHERE status = 'SUCCESS') AS thanh_cong
FROM ctl.batch
GROUP BY batch_type;

-- Q0.4  Mỗi lô nạp những file nào, bao nhiêu dòng (ví dụ lô EOD 19/08/2026 có file lỗi trailer)
SELECT b.business_date, f.entity, f.file_name, f.trailer_count, f.loaded_count, f.status, f.message
FROM ctl.file_log f JOIN ctl.batch b USING (batch_id)
WHERE b.business_date = '2026-08-19'
ORDER BY f.entity, f.revision;

-- Q0.5  Thời gian xử lý từng bước của 1 lô (xem bước nào nặng nhất)
SELECT s.step, s.rows_affected, round(extract(epoch FROM s.finished_at - s.started_at)::numeric, 2) AS giay
FROM ctl.step_log s JOIN ctl.batch b USING (batch_id)
WHERE b.business_date = '2025-12-31' AND b.batch_type = 'HISTORY'
ORDER BY s.started_at;
