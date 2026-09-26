-- =====================================================================================
-- 01. DANH MỤC: MẠNG LƯỚI, KHÁCH HÀNG, SẢN PHẨM
-- =====================================================================================

-- Q1.1  Mạng lưới hiện tại: chi nhánh (CN) quản lý các phòng giao dịch (PGD), theo vùng
SELECT region AS vung, managing_branch_code AS ma_cn, managing_branch_name AS chi_nhanh,
       count(*) AS so_diem_gd, string_agg(branch_name, ', ' ORDER BY branch_code) AS danh_sach
FROM mart.v_branch
GROUP BY region, managing_branch_code, managing_branch_name
ORDER BY region, ma_cn;

-- Q1.2  SCD Type 2: lịch sử chi nhánh trước/sau sáp nhập tỉnh 01/07/2025
--   Mỗi thay đổi tạo một phiên bản mới (valid_from/valid_to). Báo cáo tháng 6/2025 sẽ thấy tên tỉnh cũ,
--   báo cáo tháng 7/2025 trở đi thấy tên tỉnh mới -> đúng "sự thật tại thời điểm".
SELECT branch_code, branch_name, province_code, province_name, valid_from, valid_to, is_current
FROM dwh.dim_branch
WHERE branch_code IN (SELECT branch_code FROM dwh.dim_branch GROUP BY branch_code HAVING count(*) > 1)
ORDER BY branch_code, valid_from;

-- Q1.3  Khách hàng hiện hữu theo loại và phân khúc
SELECT customer_type AS loai_kh, segment AS phan_khuc, count(*) AS so_kh,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS ty_trong_pct
FROM dwh.dim_customer
WHERE is_current AND status = 'ACTIVE'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;

-- Q1.4  Tháp tuổi khách hàng cá nhân (đã che thông tin cá nhân qua view v_customer_masked)
SELECT CASE WHEN age < 25 THEN '1. <25' WHEN age < 35 THEN '2. 25-34' WHEN age < 45 THEN '3. 35-44'
            WHEN age < 55 THEN '4. 45-54' WHEN age < 65 THEN '5. 55-64' ELSE '6. 65+' END AS nhom_tuoi,
       count(*) FILTER (WHERE gender = 'M') AS nam, count(*) FILTER (WHERE gender = 'F') AS nu
FROM mart.v_customer_masked
WHERE customer_type = 'IND' AND status = 'ACTIVE' AND age IS NOT NULL
GROUP BY 1 ORDER BY 1;

-- Q1.5  Xem mẫu khách hàng đã che (tên, CCCD, SĐT) - cách chia sẻ dữ liệu an toàn cho người xem báo cáo
SELECT * FROM mart.v_customer_masked WHERE customer_type = 'IND' LIMIT 10;

-- Q1.6  Một khách hàng có nhiều phiên bản: đổi phân khúc và đổi mã tỉnh sau sáp nhập
SELECT cif, segment, province_code, home_branch_code, status, valid_from, valid_to
FROM dwh.dim_customer
WHERE cif IN (SELECT cif FROM dwh.dim_customer GROUP BY cif HAVING count(*) >= 3 LIMIT 3)
ORDER BY cif, valid_from;

-- Q1.7  Danh mục sản phẩm
SELECT product_group, product_type, product_code, product_name, customer_type
FROM dwh.dim_product ORDER BY product_group, product_code;
