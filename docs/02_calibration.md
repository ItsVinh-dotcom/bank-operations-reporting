# Hiệu chỉnh số liệu và nguồn tham chiếu

Mục tiêu: dữ liệu giả lập phải có **tỷ lệ, cơ cấu và xu hướng** giống một ngân hàng TMCP bán lẻ tầm trung ở Việt Nam. Quy mô tuyệt đối được thu nhỏ khoảng vài trăm lần để chạy được trên máy cá nhân.

## 1. Số liệu tham chiếu công khai

| Chỉ số | Giá trị ngành | Nguồn |
|---|---|---|
| Tỷ lệ CASA | Bình quân nhóm 27 ngân hàng 21,5% (Q3/2025); nhóm dẫn đầu: Techcombank 38,4%, MB 36,8%, Vietcombank 34,0% | [VietnamBiz, 11/2025](https://vietnambiz.vn/top-10-ngan-hang-co-ty-le-casa-cao-nhat-9-thang-dau-nam-2025-techcombank-mb-vietcombank-dan-dau-2025112414389392.htm) |
| Tỷ lệ nợ xấu | 1,94% đầu 2025 → 1,86% cuối 2025 (nhóm ngân hàng niêm yết) | [Vietstock, 02/2026](https://vietstock.vn/2026/02/no-xau-ngan-hang-cuoi-nam-2025-giam-manh-757-1402300.htm) |
| Tăng trưởng tín dụng | 2024: +15,08%; 2025: +17,87% (đến 24/12/2025) | [Thị trường Tài chính Tiền tệ](https://thitruongtaichinhtiente.vn/ket-thuc-nam-2024-tin-dung-tang-15-08-65089.html), [VnEconomy](https://vneconomy.vn/ngan-hang-bom-gan-279-trieu-ty-dong-tin-dung-trong-nam-2025.htm) |
| Tăng trưởng huy động | 2025: +14,11% (thấp hơn tín dụng) | [VnEconomy](https://vneconomy.vn/ngan-hang-bom-gan-279-trieu-ty-dong-tin-dung-trong-nam-2025.htm) |
| Lãi suất huy động 12 tháng | NHTM tư nhân bình quân 5,82% (giữa 12/2025), tăng 0,7–1,0 điểm % so với đầu 2025; dự báo 2026 tăng thêm khoảng 0,5 điểm % | [VietnamBiz, 12/2025](https://vietnambiz.vn/lai-suat-huy-dong-se-tiep-tuc-tang-tao-mat-bang-moi-trong-nam-2026-202512311083495.htm) |
| Đơn vị hành chính | 34 tỉnh/thành từ 01/07/2025 (11 giữ nguyên, 23 hình thành mới) theo Nghị quyết 202/2025/QH15 | [Thư viện Pháp luật](https://thuvienphapluat.vn/phap-luat/ho-tro-phap-luat/34-tinh-thanh-sau-sap-nhap-gom-23-tinh-thanh-hinh-thanh-moi-va-giu-nguyen-11-tinh-thanh-tu-1-7-2025-241858.html) |
| Phân loại nợ | 5 nhóm theo số ngày quá hạn (≤9, 10–90, 91–180, 181–360, >360 ngày); tỷ lệ trích lập cụ thể 0/5/20/50/100%, dự phòng chung 0,75% | Quy định của NHNN về phân loại nợ và trích lập dự phòng (mô phỏng đơn giản hóa) |

## 2. Kết quả của bộ dữ liệu DLB

Số liệu lấy từ `mart.v_kpi_bank_month` sau khi chạy toàn bộ pipeline với `random_seed = 20260925`.

| Chỉ số | 31/12/2023 | 31/12/2024 | 31/12/2025 | 31/08/2026 | So với ngành |
|---|---|---|---|---|---|
| Tổng huy động (tỷ VND) | 1.527 | 1.759 | 2.037 | 2.169 | |
| Dư nợ cho vay (tỷ VND) | 1.164 | 1.305 | 1.516 | 1.632 | |
| Tỷ lệ CASA | 33,0% | 32,8% | 33,6% | 33,0% | Nhóm cao, sát nhóm dẫn đầu (34–38%), phù hợp ngân hàng mạnh bán lẻ |
| Tỷ lệ nợ xấu | 1,42% | 1,70% | 2,20% | 1,43% | Dao động quanh bình quân ngành 1,86–1,94% |
| LDR (dư nợ/huy động) | 76,2% | 74,2% | 74,4% | 75,3% | Dưới trần 85% |
| Bao phủ nợ xấu (dự phòng/nợ xấu) | 66% | 62% | 45% | 71% | |
| Tăng trưởng dư nợ trong năm | | +12,1% | +16,2% | +7,7% (8 tháng) | Thấp hơn ngành 1–3 điểm %: tín dụng không đạt kế hoạch |
| Tăng trưởng huy động trong năm | | +15,2% | +15,8% | +6,5% (8 tháng) | Cao hơn ngành 2025 (+14,11%) |
| Tỷ trọng giao dịch kênh số | | 75,8% | 78,5% | 79,6% | Tăng dần, giao dịch tại quầy giảm |

**Cơ cấu dư nợ 31/08/2026:** vay mua nhà 38,2%, SME vốn lưu động 25,9%, hộ kinh doanh 11,1%, SME trung dài hạn 9,5%, ô tô 7,6%, tiêu dùng tín chấp 4,8%, cầm cố sổ tiết kiệm 1,9%, thẻ tín dụng 1,1%. Dư nợ bán lẻ chiếm khoảng 65%.

**Nợ xấu theo sản phẩm 31/08/2026:** vay mua nhà 1,0%, SME 0,8–1,1%, ô tô 2,0%, hộ kinh doanh 3,2%, thẻ tín dụng 3,1%, tiêu dùng tín chấp 4,0%. Sản phẩm không có TSĐB có nợ xấu cao hơn, đúng quy luật thực tế.

**Thực hiện so với kế hoạch** (kế hoạch trong file Excel): huy động vượt 2–5%, dư nợ đạt 95–100%.

## 3. Sự kiện cài sẵn và dấu hiệu trên dữ liệu

| Sự kiện | Dấu hiệu kiểm chứng được |
|---|---|
| Nợ xấu cụm Cần Thơ (CN 400 và 3 PGD), vay tiêu dùng & hộ kinh doanh, 03–10/2025 | Nợ xấu cụm Cần Thơ lên 8,7% (30/09/2025) trong khi toàn hàng khoảng 2%; ma trận chuyển nhóm nợ cho thấy dòng Nhóm 1 → 2 → 3 |
| Chiến dịch thẻ tín dụng Q2/2025 | Phát hành 156–189 thẻ/tháng (bình thường 45–70), tỷ lệ kích hoạt chỉ khoảng 33–45% |
| Sự cố ATM cụm CN Sài Gòn, 08/09–17/10/2025 | Uptime trung bình giảm từ 99,2% xuống ~91–94%; khiếu nại "ATM không nhận được tiền" tăng |
| Lỗi app sau nâng cấp, 09–18/03/2026 | Khiếu nại "Lỗi ứng dụng" tháng 3/2026 tăng gần 10 lần |
| Tết Nguyên đán | Rút tiền ATM tăng mạnh 12 ngày trước Tết, thưởng tháng 13 đổ vào tài khoản lương, tỷ trọng kênh số giảm nhẹ tháng Tết |
| Chạy số cuối quý | Tiền gửi không kỳ hạn SME tăng ngày làm việc cuối quý và rút ra đầu quý sau (tỷ lệ CASA tăng tại các tháng 3, 6, 9, 12) |
| Sáp nhập tỉnh 01/07/2025 | 13 chi nhánh/PGD có phiên bản SCD2 mới (đổi mã hoặc tên tỉnh), 2.333 khách hàng được cập nhật mã tỉnh mới |

## 4. Giả định không có số liệu công khai

Các chỉ tiêu sau ngân hàng không công bố. Dự án dùng giả định hợp lý và ghi rõ là giả định:

- Thời gian chờ tại quầy, năng suất giao dịch viên, SLA xử lý khiếu nại.
- Uptime ATM (mức nền 99,2%), tỷ lệ hết tiền ATM.
- Hành vi thanh toán thẻ tín dụng (55% trả đủ, 35% trả một phần, 10% chỉ trả tối thiểu).
- Tỷ lệ khấu trừ TSĐB khi tính dự phòng: sổ tiết kiệm 100%, bất động sản 50%, ô tô 30%, hàng tồn kho/máy móc 40%.
- Biểu lãi suất theo thời kỳ (`data/reference/rates_*.csv`): bám mặt bằng lãi suất công bố, làm tròn.

## 5. Tái tạo và chỉnh hiệu chỉnh

Tham số nằm trong `python/generator/simulate.py`:

- Đường tăng trưởng: `g_year` (dư nợ), `g` (tiền gửi có kỳ hạn), thu nhập tăng 0,5%/tháng (CASA).
- Rủi ro: `P_MISS` (xác suất lỡ hạn theo sản phẩm), các xác suất chuyển tiếp, `EVENTS`.
- Quy mô: `--customers`, `--sme` hoặc `config/config.yaml`.

Cùng `random_seed` luôn cho ra cùng một bộ dữ liệu.
