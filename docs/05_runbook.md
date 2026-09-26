# Hướng dẫn chạy dự án (Windows)

Thời gian chạy toàn bộ lần đầu: khoảng 15–25 phút (tùy máy).

## 0. Cài đặt một lần

| Phần mềm | Ghi chú |
|---|---|
| Python 3.11+ | Đã có sẵn (Anaconda/Miniconda đều được) |
| PostgreSQL 16 hoặc 17 | Tải bộ cài từ postgresql.org (EDB installer). Ghi nhớ mật khẩu user `postgres`. Bộ cài có kèm pgAdmin |
| VS Code / Antigravity | Mở thư mục dự án |
| Excel 365, Power BI Desktop | Đã có |

Mở terminal trong VS Code tại thư mục dự án:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Mở file `.env`, điền `PG_PASSWORD` là mật khẩu `postgres` bạn đặt khi cài PostgreSQL.

## 1. Sinh dữ liệu core banking (~2 phút, ~450 MB)

```bash
python -m python.generator.run_generator --clean
```

Kết quả nằm trong `data/raw/history/` (33 lô tháng) và `data/raw/eod/` (21 lô ngày tháng 08/2026). Thư mục này **không** đưa lên GitHub. Cùng `random_seed` thì mọi máy sinh ra cùng một bộ dữ liệu.

Muốn chạy thử nhanh với dữ liệu nhỏ: `python -m python.generator.run_generator --customers 3000 --sme 120 --clean`.

## 2. Tạo database và các đối tượng

```bash
psql -U postgres -f sql/00_setup/00_create_database.sql
python -m python.etl.setup_db
```

`setup_db` chạy các script SQL theo thứ tự, nạp danh mục tham chiếu (`data/reference`) và dựng `dim_date`. Muốn làm lại từ đầu: `python -m python.etl.setup_db --reset`.

> Nếu lệnh `psql` không nhận, thêm `C:\Program Files\PostgreSQL\17\bin` vào PATH, hoặc mở pgAdmin → Query Tool và chạy `CREATE DATABASE dlb_dwh;`.

## 3. Chạy ETL

```bash
python -m python.etl.run_pipeline --mode history   # 33 lô lịch sử (migration)
python -m python.etl.run_pipeline --mode eod       # 21 lô EOD tháng 08/2026
```

- Lô đã chạy thành công sẽ được bỏ qua, nên có thể chạy lại an toàn sau khi lỗi.
- Ngày **19/08/2026** core gửi file giao dịch lỗi trailer. ETL từ chối file gốc, tự dùng file gửi lại `_R1` và ghi nhận sự cố vào `ctl.file_log` và `dq.result`. Đây là tình huống cố ý mô phỏng.
- Chạy một ngày cụ thể: `python -m python.etl.run_pipeline --mode eod --date 2026-08-19`.

## 4. Nạp kế hoạch kinh doanh từ Excel

```bash
python -m python.etl.load_plan
```

Workbook `excel/templates/KE_HOACH_KINH_DOANH_2024_2026.xlsx` có thể tạo lại bằng
`python -m python.generator.build_plan_excel` (sau đó mở bằng Excel và **Save** để Excel tính công thức trước khi nạp).

## 5. Kiểm tra nhanh

```sql
-- KPI toàn hàng
SELECT * FROM mart.v_kpi_bank_month ORDER BY month_end;
-- Chất lượng dữ liệu
SELECT rule_code, sum(failed_rows) FROM mart.v_dq_summary GROUP BY 1 ORDER BY 1;
-- Nhật ký lô
SELECT * FROM ctl.batch ORDER BY batch_id;
```

## 6. Kiểm thử

```bash
pytest
```

## Sự cố thường gặp

| Lỗi | Cách xử lý |
|---|---|
| `password authentication failed` | Kiểm tra `PG_PASSWORD` trong `.env` |
| `database "dlb_dwh" does not exist` | Chạy lại bước 2 |
| `plan_value has empty cells` | Mở file kế hoạch bằng Excel, bấm Save rồi nạp lại |
| Một lô FAILED | Xem `SELECT message FROM ctl.batch WHERE status='FAILED'`, sửa rồi chạy lại lệnh ETL |
