# Bank Operations Reporting

Hệ thống báo cáo vận hành end-to-end cho một **ngân hàng TMCP tư nhân tầm trung, mạnh bán lẻ** tại Việt Nam, mô phỏng đúng luồng dữ liệu thực tế: *Core Banking → File trích xuất cuối ngày → Data Warehouse → Data Mart → Báo cáo*.

> **Lưu ý:** Toàn bộ dữ liệu là **giả lập**, được hiệu chỉnh theo số liệu công khai (báo cáo tài chính các ngân hàng niêm yết, thống kê ngành). "Ngân hàng TMCP Đông Lam" (mã `DLB`) là tên **hư cấu**, không đại diện cho bất kỳ ngân hàng nào.

## Công cụ

| Công cụ | Vai trò trong dự án |
|---|---|
| **Python** | Sinh dữ liệu core banking, ETL, kiểm tra chất lượng dữ liệu, phân tích nâng cao, tự động hóa báo cáo |
| **SQL Server** | Data Warehouse (staging → core → mart), stored procedure xử lý cuối ngày, đối chiếu số liệu |
| **Excel** | Kế hoạch chỉ tiêu, đối chiếu sổ cái, báo cáo định kỳ theo mẫu (Power Query) |
| **Power BI** | Mô hình dữ liệu, DAX, dashboard điều hành, phân quyền theo chi nhánh (RLS) |

## Cấu trúc thư mục

```
bank-operations-reporting/
├── config/          # Cấu hình mẫu (config.example.yaml)
├── data/
│   ├── raw/         # File trích xuất core banking (gitignored, sinh lại bằng script)
│   ├── staging/     # Dữ liệu trung gian (gitignored)
│   ├── reference/   # Danh mục: tỉnh/thành, sản phẩm, mã ngành...
│   └── sample/      # Mẫu dữ liệu nhỏ để xem nhanh
├── docs/            # Thiết kế, data dictionary, nghiệp vụ, hình ảnh
├── sql/
│   ├── 00_setup/    # Tạo database, schema
│   ├── 01_staging/  # Bảng staging (giống cấu trúc file core)
│   ├── 02_core/     # Dim/Fact của DWH (SCD Type 2)
│   ├── 03_mart/     # Data mart phục vụ báo cáo
│   ├── 04_procedures/ # Batch cuối ngày, tính toán, đối chiếu
│   ├── 05_reports/  # Truy vấn báo cáo
│   └── 99_tests/    # Kiểm thử số liệu
├── python/
│   ├── generator/   # Mô phỏng hệ thống core banking
│   ├── etl/         # Nạp file cuối ngày vào SQL
│   ├── data_quality/# Kiểm tra chất lượng dữ liệu
│   ├── analytics/   # Dự báo nợ xấu, chấm điểm tín dụng, churn
│   └── automation/  # Xuất và gửi báo cáo tự động
├── notebooks/       # Phân tích khám phá (Jupyter)
├── excel/           # Mẫu và báo cáo Excel
└── powerbi/         # Dự án Power BI (PBIP) và theme
```

## Bắt đầu

```bash
git clone https://github.com/<your-username>/bank-operations-reporting.git
cd bank-operations-reporting
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env           # sau đó chỉnh thông tin kết nối SQL Server
```

Yêu cầu: Python 3.11+, SQL Server 2019+ (Developer/Express) + SSMS, ODBC Driver 18, Excel 365, Power BI Desktop.

## Tài liệu

- [Bản thiết kế tổng thể](docs/01_project_blueprint.md)

## Lộ trình

- [x] Khởi tạo repo, thiết kế tổng thể
- [ ] Giai đoạn 1: Danh mục tham chiếu và bộ sinh dữ liệu core banking
- [ ] Giai đoạn 2: Data Warehouse và batch cuối ngày (SQL)
- [ ] Giai đoạn 3: ETL và kiểm tra chất lượng dữ liệu (Python)
- [ ] Giai đoạn 4: Excel: kế hoạch, đối chiếu, báo cáo mẫu
- [ ] Giai đoạn 5: Power BI dashboard
- [ ] Giai đoạn 6: Phân tích nâng cao và tự động hóa
