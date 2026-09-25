# Bản thiết kế tổng thể: Hệ thống báo cáo vận hành DLB

*Phiên bản 0.1 (bản nháp để duyệt), 25/09/2026*

## 1. Mục tiêu

Xây dựng một hệ thống báo cáo vận hành hoàn chỉnh cho một ngân hàng bán lẻ tầm trung. Hệ thống phải thể hiện được:

1. Hiểu nghiệp vụ ngân hàng Việt Nam: huy động, tín dụng, thẻ, kênh số, vận hành chi nhánh, rủi ro.
2. Kỹ năng dữ liệu end-to-end: mô phỏng nguồn, ETL, kho dữ liệu, kiểm soát chất lượng, báo cáo, phân tích.
3. Cách làm việc chuyên nghiệp: tài liệu hóa, kiểm thử, quản lý mã nguồn.

## 2. Ngân hàng hư cấu

| Thuộc tính | Giá trị |
|---|---|
| Tên | Ngân hàng TMCP Đông Lam (mã `DLB`), **hư cấu** |
| Loại hình | TMCP tư nhân tầm trung, định hướng bán lẻ và ngân hàng số |
| Mạng lưới mô phỏng | ~40 điểm giao dịch (12 chi nhánh + ~28 phòng giao dịch), tập trung Hà Nội, TP.HCM và các tỉnh/thành kinh tế lớn, theo danh mục **34 tỉnh/thành sau sáp nhập (hiệu lực 01/07/2025)** |
| Khách hàng | ~50.000 cá nhân + ~2.000 doanh nghiệp SME |
| Giai đoạn dữ liệu | 01/01/2024 – 31/08/2026 (theo ngày) |
| Quy mô | Mô phỏng thu nhỏ: giữ đúng **tỷ lệ, cơ cấu, xu hướng** của ngân hàng thật, không giữ quy mô tuyệt đối |

### Mục tiêu hiệu chỉnh

Các chỉ số dưới đây sẽ được **chốt theo báo cáo tài chính 2024–2025 của nhóm ngân hàng TMCP bán lẻ niêm yết**, có dẫn nguồn trong `docs/02_calibration.md` (sẽ viết ở giai đoạn 1). Khoảng giá trị hiện tại chỉ là tham chiếu sơ bộ.

| Chỉ số | Ý nghĩa | Hướng hiệu chỉnh |
|---|---|---|
| Tỷ lệ CASA | Tiền gửi không kỳ hạn / tổng tiền gửi | Nhóm cao của ngành (ngân hàng mạnh bán lẻ) |
| Cơ cấu dư nợ bán lẻ | Dư nợ cá nhân / tổng dư nợ | Chiếm đa số |
| Tỷ lệ nợ xấu (nhóm 3–5) | Nợ xấu / tổng dư nợ | Quanh mức trung bình ngành, có biến động theo quý |
| Tăng trưởng tín dụng | So với cuối năm trước | Bám theo tăng trưởng toàn ngành từng năm |
| LDR | Dư nợ / huy động | Trong giới hạn quy định |
| Lãi suất | Theo kỳ hạn, theo thời kỳ | Bám biểu lãi suất công bố của các ngân hàng cùng nhóm |

## 3. Kiến trúc

```
┌──────────────────┐   EOD batch   ┌───────────┐    ┌──────────────┐    ┌────────────┐    ┌──────────────┐
│ Core Banking     │ ────────────▶ │ data/raw  │ ─▶ │ stg (SQL)    │ ─▶ │ dwh (SQL)  │ ─▶ │ mart (SQL)   │
│ (Python mô phỏng)│  CSV theo ngày│ file T-1  │    │ nạp nguyên   │    │ Dim/Fact   │    │ bảng báo cáo │
└──────────────────┘               └───────────┘    └──────────────┘    │ SCD Type 2 │    └──────┬───────┘
                                        │                               └────────────┘           │
                                   Python ETL + Data Quality                         ┌───────────┴──────────┐
                                                                                     │ Power BI  │  Excel   │
                         Excel (kế hoạch, số nhập tay) ─────────────────────────────▶│ dashboard │ báo cáo  │
                                                                                     └──────────────────────┘
```

**Nguyên tắc mô phỏng giống thật**

- **Ngày nghiệp vụ (business date) khác ngày hệ thống:** có giao dịch hạch toán trễ, giao dịch cuối tuần và ngày lễ dồn sang ngày làm việc kế tiếp.
- **File trích xuất cuối ngày** mang tên theo chuẩn, ví dụ `DLB_LOAN_20260831.csv`, có dòng trailer ghi số bản ghi để đối chiếu.
- **Số dư dạng snapshot theo ngày;** báo cáo dùng số dư cuối kỳ và **số dư bình quân**.
- **Dữ liệu có lỗi có chủ đích** (~0,5–2%): thiếu thông tin định danh, trùng CIF, sai mã chi nhánh, giao dịch âm bất thường. Các lỗi này bị bộ kiểm tra chất lượng bắt và ghi log.
- **Đối chiếu với sổ cái (GL):** số tổng hợp từ chi tiết phải khớp số dư tài khoản GL. Phần chênh lệch phải giải trình được.

## 4. Dữ liệu nguồn (core banking mô phỏng)

| File | Nội dung | Tần suất |
|---|---|---|
| `CUSTOMER` | CIF, họ tên, ngày sinh, giới tính, CCCD (giả), tỉnh/thành, phân khúc, ngày mở | Delta theo ngày |
| `BRANCH` | Mã chi nhánh/PGD, cấp, vùng, tỉnh/thành, ngày hoạt động | Khi thay đổi |
| `PRODUCT` | Mã và tên sản phẩm, nhóm, loại tiền | Khi thay đổi |
| `CASA_ACCOUNT` | Tài khoản thanh toán, số dư cuối ngày | Snapshot ngày |
| `TERM_DEPOSIT` | Sổ tiết kiệm/tiền gửi có kỳ hạn: kỳ hạn, lãi suất, ngày đáo hạn, số dư | Snapshot ngày |
| `LOAN` | Khoản vay: hạn mức, giải ngân, dư nợ, lãi suất, số ngày quá hạn, **nhóm nợ** | Snapshot ngày |
| `TRANSACTION` | Giao dịch tài khoản: kênh (quầy/ATM/app/internet), loại, số tiền | Theo ngày |
| `CARD` / `CARD_TXN` | Thẻ ghi nợ/tín dụng, trạng thái kích hoạt; giao dịch thẻ theo MCC | Theo ngày |
| `GL_BALANCE` | Số dư tài khoản sổ cái theo chi nhánh | Snapshot ngày |
| `ATM_EVENT` | Sự kiện ATM: hoạt động, lỗi, hết tiền | Theo ngày |
| `BRANCH_QUEUE` | Lượt phục vụ tại quầy: thời gian chờ, thời gian phục vụ | Theo ngày |
| `COMPLAINT` | Khiếu nại: kênh, loại, thời điểm tiếp nhận/xử lý, SLA | Theo ngày |
| `PLAN` (Excel) | Kế hoạch chỉ tiêu theo chi nhánh, tháng | Theo năm, điều chỉnh theo quý |

## 5. Data Warehouse (SQL Server: `DLB_DWH`)

**Schema:** `stg` (staging), `dwh` (lõi), `mart` (báo cáo), `dq` (chất lượng dữ liệu), `ctl` (điều khiển batch).

**Dimension:** `DimDate`, `DimBranch` (SCD2), `DimCustomer` (SCD2), `DimProduct`, `DimChannel`, `DimLoanGroup` (nhóm nợ 1–5), `DimCurrency`, `DimMCC`, `DimGLAccount`.

**Fact:**

| Fact | Grain |
|---|---|
| `FactDepositDaily` | Tài khoản × ngày |
| `FactLoanDaily` | Khoản vay × ngày |
| `FactTransaction` | Giao dịch |
| `FactCardTxn` | Giao dịch thẻ |
| `FactGLDaily` | TK GL × chi nhánh × ngày |
| `FactBranchOps` | Chi nhánh × ngày (lượt giao dịch, thời gian chờ) |
| `FactATMDaily` | ATM × ngày (uptime, số lần lỗi) |
| `FactComplaint` | Khiếu nại |
| `FactPlan` | Chi nhánh × chỉ tiêu × tháng |

**Stored procedure chính:** `ctl.usp_RunEOD` (điều phối batch), `dwh.usp_LoadDim*` (SCD2), `dwh.usp_LoadFact*`, `dwh.usp_ClassifyLoanGroup` (phân nhóm nợ theo số ngày quá hạn), `mart.usp_BuildMonthly*`, `dq.usp_ReconcileGL`.

## 6. Danh mục báo cáo

| # | Báo cáo | Người dùng | Công cụ |
|---|---|---|---|
| 1 | Tổng quan điều hành: huy động, dư nợ, nợ xấu, thu nhập, so với kế hoạch và cùng kỳ | Ban điều hành | Power BI |
| 2 | Huy động vốn: theo kỳ hạn, sản phẩm, chi nhánh; CASA; đáo hạn sắp tới; rút trước hạn | Khối Nguồn vốn, Bán lẻ | Power BI |
| 3 | Tín dụng: dư nợ, giải ngân, thu nợ theo sản phẩm/ngành; ma trận chuyển nhóm nợ | Khối Tín dụng, Rủi ro | Power BI |
| 4 | Thẻ & Kênh số: phát hành, kích hoạt, chi tiêu theo MCC; tỷ trọng giao dịch theo kênh | Khối Thẻ, Ngân hàng số | Power BI |
| 5 | Vận hành chi nhánh: năng suất giao dịch viên, thời gian chờ, uptime ATM, SLA khiếu nại | Khối Vận hành | Power BI |
| 6 | Khách hàng: khách mới, khách rời bỏ, số sản phẩm/khách, phân khúc | Khối Bán lẻ | Power BI |
| 7 | Báo cáo ngày (T-1) huy động/dư nợ theo chi nhánh | Giám đốc chi nhánh | Excel (Power Query) |
| 8 | Đối chiếu số liệu chi tiết với GL | Kế toán, MIS | Excel + SQL |
| 9 | Kết quả thực hiện kế hoạch tháng/quý | Kế hoạch, Ban điều hành | Excel |
| 10 | Nhật ký chất lượng dữ liệu | MIS, Quản trị dữ liệu | Power BI / Excel |

**Phân quyền (RLS):** Hội sở xem toàn hàng; giám đốc vùng xem vùng mình; giám đốc chi nhánh xem chi nhánh và các PGD trực thuộc.

## 7. Python

| Module | Chức năng |
|---|---|
| `generator/` | Mô phỏng core banking theo ngày: vòng đời khách hàng, tài khoản, khoản vay; mùa vụ (Tết, cuối quý, cuối năm); phân phối lệch; sự kiện cài sẵn; lỗi dữ liệu có chủ đích |
| `etl/` | Kiểm tra trailer, nạp file vào `stg`, gọi `ctl.usp_RunEOD`, ghi log batch |
| `data_quality/` | Bộ quy tắc kiểm tra (đầy đủ, hợp lệ, duy nhất, nhất quán, đối chiếu), xuất báo cáo lỗi |
| `analytics/` | Dự báo nợ xấu, chấm điểm tín dụng, dự đoán khách rời bỏ, phân khúc RFM |
| `automation/` | Xuất báo cáo Excel T-1 theo từng chi nhánh, soạn email tóm tắt |

## 8. Excel

- `PLAN_2024-2026.xlsx`: giao chỉ tiêu theo chi nhánh/tháng, có phân bổ từ chỉ tiêu toàn hàng.
- `RECON_GL.xlsx`: đối chiếu chi tiết với GL, đánh dấu chênh lệch.
- `DAILY_BRANCH_REPORT.xlsx`: mẫu báo cáo ngày kết nối SQL bằng Power Query, có định dạng chuẩn.

## 9. Sự kiện cài sẵn (để dashboard có câu chuyện)

| Sự kiện | Thời điểm | Dấu hiệu trên dữ liệu |
|---|---|---|
| Tết Nguyên đán | Hàng năm | Rút tiền ATM tăng mạnh 2 tuần trước Tết, lương thưởng đổ vào CASA |
| Chạy chỉ tiêu | Cuối quý, cuối năm | Huy động và giải ngân dồn vào vài ngày cuối kỳ, đầu kỳ sau giảm lại |
| Chiến dịch thẻ tín dụng | Một quý năm 2025 | Phát hành tăng vọt, tỷ lệ kích hoạt thấp |
| Chi nhánh nợ xấu tăng | Một chi nhánh, 2025 | Một nhóm khoản vay tiêu dùng trượt nhóm dần qua nhiều tháng |
| Sáp nhập tỉnh/thành | 01/07/2025 | Chi nhánh đổi tỉnh/thành, xử lý bằng SCD Type 2 |
| Sự cố ATM | Một cụm ATM | Uptime giảm, khiếu nại tăng cùng thời điểm |
| Dịch chuyển kênh số | Suốt kỳ | Tỷ trọng giao dịch qua app tăng dần, giao dịch tại quầy giảm |

## 10. Lộ trình

| Giai đoạn | Nội dung | Kết quả |
|---|---|---|
| 0 | Khởi tạo repo, thiết kế tổng thể | Tài liệu này |
| 1 | Danh mục tham chiếu, hiệu chỉnh có nguồn, bộ sinh dữ liệu | `data/reference`, `docs/02_calibration.md`, `python/generator` |
| 2 | Data Warehouse và batch cuối ngày | `sql/*` |
| 3 | ETL và kiểm tra chất lượng | `python/etl`, `python/data_quality` |
| 4 | Excel | `excel/*` |
| 5 | Power BI | `powerbi/*` |
| 6 | Phân tích nâng cao và tự động hóa | `python/analytics`, `python/automation`, `notebooks/` |

## 11. Quy ước

- **Commit:** `feat: ...`, `fix: ...`, `docs: ...`, `sql: ...`
- **Đặt tên SQL:** `PascalCase` cho bảng, tiền tố `usp_` cho stored procedure, `vw_` cho view.
- **Dữ liệu lớn không đưa lên GitHub:** `data/raw` sinh lại bằng `python/generator` với `random_seed` cố định, nên ai clone về chạy cũng ra cùng một bộ dữ liệu.

## 12. Cần duyệt

1. Tên ngân hàng hư cấu "Đông Lam" (`DLB`): giữ hay đổi?
2. Quy mô (~40 điểm giao dịch, ~52.000 khách hàng, 2024–08/2026) có phù hợp máy của bạn không?
3. Có thêm hoặc bớt báo cáo nào trong mục 6?
