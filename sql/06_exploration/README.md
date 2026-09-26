# Bộ truy vấn khám phá dữ liệu

Chạy theo thứ tự để hiểu dự án trước khi làm dashboard. Mỗi câu truy vấn có chú thích: câu hỏi nghiệp vụ, cách đọc kết quả, và kỹ thuật SQL dùng.

| File | Nội dung | Kỹ thuật SQL |
|---|---|---|
| `00_lam_quen.sql` | Các tầng dữ liệu, số dòng, nhật ký lô ETL | information_schema, FILTER |
| `01_danh_muc.sql` | Mạng lưới, SCD2 chi nhánh/khách hàng, phân khúc, tháp tuổi | string_agg, window SUM() OVER |
| `02_huy_dong.sql` | CASA, chạy số cuối quý, kỳ hạn, lãi suất, thang đáo hạn, báo cáo T-1 | LAG, tỷ trọng |
| `03_tin_dung.sql` | Dư nợ, nợ xấu, sự kiện Cần Thơ, ma trận chuyển nhóm, roll rate, CIC | pivot bằng FILTER |
| `04_giao_dich_the.sql` | Dịch chuyển kênh, Tết, giờ giao dịch, thưởng tháng 13, chiến dịch thẻ | RANK, CTE |
| `05_van_hanh.sql` | Sự cố ATM, thời gian chờ, khiếu nại, lỗi app | percentile_cont |
| `06_ke_hoach_chat_luong.sql` | Thực hiện vs kế hoạch, xếp hạng chi nhánh, chất lượng dữ liệu | ROW_NUMBER |

Mẹo: các dòng có chữ **SỰ KIỆN** là những câu chuyện được cài sẵn, rất nên đưa lên dashboard.
