# Dữ liệu core banking (bản nén Parquet)

Thư mục này chứa **toàn bộ** 761 file trích xuất core banking của dự án (33 lô lịch sử + 21 lô EOD), nén từ **473 MB CSV xuống khoảng 50 MB** bằng định dạng Parquet (nén zstd).

| File | Nội dung |
|---|---|
| `<ENTITY>.parquet` | Dữ liệu của một loại file core, cột `_file` cho biết dòng thuộc file CSV nào |
| `TXN.part1..4.parquet` | Giao dịch (3,7 triệu dòng) chia 4 phần, mỗi phần khoảng 10 MB |
| `manifest.json` | Danh sách 761 file gốc, số dòng và dòng trailer của từng file (kể cả file lỗi trailer ngày 19/08/2026) |
| `_generation_report.json` | Tham số sinh dữ liệu và số lỗi dữ liệu được cài sẵn |

## Dùng thế nào

```bash
python -m python.tools.unpack_data     # dựng lại data/raw/*.csv (khoảng 15 giây), giống hệt từng byte
python -m python.etl.run_pipeline --mode all
```

Sau khi sinh lại dữ liệu bằng generator (ví dụ đổi tham số), đóng gói lại bằng:

```bash
python -m python.tools.pack_data
```

## Vì sao dùng Parquet

- **Nén theo cột:** các giá trị trong một cột giống nhau nhiều (mã chi nhánh, loại giao dịch, ngày...) nên nén rất tốt, khoảng 10 lần.
- **Mỗi file dưới 11 MB:** GitHub chặn file trên 100 MB và cảnh báo file trên 50 MB.
- **Đọc trực tiếp được** bằng pandas, DuckDB, Power BI (connector Parquet) mà không cần giải nén.
