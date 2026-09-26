# Khung kiểm soát chất lượng dữ liệu

Mỗi lô ETL chạy `dq.sp_run_checks`. Kết quả tổng hợp ở `dq.result`, bản ghi lỗi chi tiết ở `dq.issue`, xem nhanh qua view `mart.v_dq_summary`.

## Quy tắc

| Mã | Đối tượng | Chiều chất lượng | Mức độ | Nội dung |
|---|---|---|---|---|
| CUS_DUP_CIF | CUSTOMER | Uniqueness | Trung bình | CIF xuất hiện nhiều lần trong cùng file |
| CUS_MISS_DOB | CUSTOMER | Completeness | Trung bình | KH cá nhân thiếu ngày sinh |
| CUS_MISS_ID | CUSTOMER | Completeness | Cao | KH cá nhân thiếu số CCCD |
| CUS_BAD_PHONE | CUSTOMER | Validity | Thấp | Số điện thoại không đủ 10 chữ số |
| TXN_DUP_ID | TXN | Uniqueness | Cao | Mã giao dịch bị trùng |
| TXN_BAD_BRANCH | TXN | Validity | Cao | Mã chi nhánh không có trong danh mục |
| TXN_NEG_AMOUNT | TXN | Validity | Cao | Số tiền âm nhưng không phải giao dịch hoàn trả |
| TXN_LATE_POST | TXN | Timeliness | Trung bình | Hạch toán trễ hơn 1 ngày làm việc |
| TXN_ORPHAN_ACC | TXN | Consistency | Cao | Giao dịch của tài khoản không có trong danh mục |
| LN_MISS_COLL | LOAN | Completeness | Cao | Khoản vay có TSĐB nhưng thiếu giá trị tài sản |
| LN_GROUP_DIFF | LOAN_BALANCE | Consistency | Cao | Nhóm nợ core khác nhóm nợ DWH tính lại |
| CASA_ROLLFWD | CASA_BALANCE | Reconciliation | Cao | Số dư đầu kỳ + phát sinh ≠ số dư cuối kỳ |
| GL_RECON | GL_BALANCE | Reconciliation | Cao | Chi tiết ≠ sổ cái theo chi nhánh × tài khoản GL |
| FILE_TRAILER | Tất cả | Completeness | Cao | Số bản ghi thực tế ≠ dòng trailer |
| TD_MATURITY | TERM_DEPOSIT | Consistency | Trung bình | Ngày đáo hạn ≠ ngày mở + kỳ hạn |

Trạng thái: **PASS** (không lỗi), **WARN** (tỷ lệ lỗi ≤ ngưỡng cho phép), **FAIL** (vượt ngưỡng).

## Lỗi được cài sẵn trong dữ liệu

Bộ sinh dữ liệu cố ý tạo lỗi (xem `python/generator/writer.py`, số lượng thực tế ghi trong `data/raw/_generation_report.json`) để khung DQ có việc để làm, giống dữ liệu thật:

| Lỗi cài sẵn | Tỷ lệ | Quy tắc bắt được |
|---|---|---|
| Thiếu ngày sinh | 0,4% KH cá nhân | CUS_MISS_DOB |
| Thiếu CCCD | 0,3% | CUS_MISS_ID |
| SĐT thiếu 1 số | 0,2% | CUS_BAD_PHONE |
| Bản ghi KH gửi trùng | 12 bản ghi | CUS_DUP_CIF |
| Mã chi nhánh "999" | 0,02% giao dịch | TXN_BAD_BRANCH |
| Số tiền âm | 0,01% giao dịch | TXN_NEG_AMOUNT, kéo theo CASA_ROLLFWD |
| Hạch toán trễ | 0,05% giao dịch | TXN_LATE_POST |
| Giao dịch gửi trùng | 0,005% | TXN_DUP_ID (ETL loại trùng khi nạp) |
| Thiếu giá trị TSĐB | 0,3% khoản vay mua nhà | LN_MISS_COLL |
| File giao dịch lỗi trailer | 19/08/2026 | FILE_TRAILER (dùng file `_R1`) |
| Chênh lệch sổ cái | 3 khoản mục (xem dưới) | GL_RECON |

**Khoản mục đối chiếu sổ cái (cố ý):**

1. 30/06/2025, CN Bình Dương (130), TK 4211: GL cao hơn chi tiết 1,85 tỷ (khoản treo hạch toán sau giờ khóa sổ).
2. 31/12/2025, CN Hà Nội (200), TK 2121/2122: 2,4 tỷ phân loại nhóm nợ trên GL chậm một kỳ.
3. 31/03/2026, CN Cần Thơ (400), TK 4232: chênh lệch làm tròn 1.250.000 đ.

Ngoài ra, các giao dịch có số tiền âm làm lệch roll-forward của tài khoản liên quan. Đây là ví dụ lỗi nguồn lan xuống báo cáo đối chiếu.

## Lưu ý kỹ thuật

- **CASA_ROLLFWD kiểm tra trễ một kỳ:** giao dịch thực hiện vào cuối tuần cuối tháng được hạch toán ngày làm việc đầu tháng sau, nên chỉ đủ dữ liệu khi lô tháng sau đã nạp.
- **LN_GROUP_DIFF:** DWH tính lại nhóm nợ = max(nhóm theo số ngày quá hạn, nhóm theo CIC). Nếu core phân loại khác thì bị gắn cờ.
