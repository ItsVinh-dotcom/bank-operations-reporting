# Bối cảnh nghiệp vụ

Tài liệu này dành cho người mới đọc dự án (hoặc chính người trình bày dự án): ngân hàng này là ai, ai dùng báo cáo, từng chỉ số nghĩa là gì, và dữ liệu đang "kể" những câu chuyện nào. Đọc xong, bạn có thể tự trình bày dashboard trong 5 phút và trả lời các câu hỏi nghiệp vụ thường gặp.

> Ngân hàng TMCP Đông Lam (DLB) là **hư cấu**. Số liệu là giả lập, hiệu chỉnh theo số liệu công khai của ngành (xem [02_calibration.md](02_calibration.md)). Số trong tài liệu này là số tại **31/08/2026** nếu không ghi khác.

---

## 1. Tóm tắt trong 30 giây

DLB là ngân hàng TMCP tư nhân tầm trung, mạnh bán lẻ, có 12 chi nhánh và 28 phòng giao dịch. Mỗi đêm, hệ thống core banking xuất file cuối ngày. Python nạp các file này vào kho dữ liệu PostgreSQL, kiểm tra chất lượng dữ liệu, rồi tổng hợp thành mart. Excel cung cấp kế hoạch kinh doanh. Power BI trình bày 6 trang báo cáo cho ban điều hành.

Tại 31/08/2026: tổng huy động **2.168,7 tỷ**, dư nợ **1.632,2 tỷ**, tỷ lệ CASA **33,0%**, nợ xấu **1,43%**, LDR **75,3%**.

Kết luận điều hành: huy động vượt kế hoạch (103%), tín dụng chưa đạt kế hoạch (96%), chất lượng tài sản đã cải thiện sau đợt nợ xấu tăng năm 2025 (đỉnh 2,42%).

---

## 2. Ai dùng báo cáo, dùng để làm gì

| Người dùng | Câu hỏi họ cần trả lời | Trang dashboard |
|---|---|---|
| Ban điều hành, HĐQT | Quy mô tăng thế nào? Có đạt kế hoạch không? Rủi ro có trong ngưỡng không? | 1. Tổng quan |
| Khối Nguồn vốn / Bán lẻ | Huy động đến từ đâu, chi phí vốn rẻ hay đắt (CASA), chi nhánh nào đạt kế hoạch | 2. Huy động |
| Khối Tín dụng, Quản lý rủi ro | Dư nợ tăng ở sản phẩm nào, nợ xấu tập trung ở đâu, khoản vay đang chuyển nhóm ra sao | 3. Tín dụng & Rủi ro |
| Khối Bán lẻ, Ngân hàng số, Thẻ | Khách hàng mới, chiến dịch thẻ có hiệu quả không, khách chuyển sang kênh số chưa | 4. Khách hàng, Thẻ & Kênh |
| Khối Vận hành, Dịch vụ khách hàng | ATM có ổn định không, khách chờ bao lâu, khiếu nại có xử lý đúng hạn không | 5. Vận hành |
| Phòng Quản lý dữ liệu / BI | Dữ liệu hôm nay có tin được không, lỗi nằm ở đâu | 6. Chất lượng dữ liệu |

**Nhịp báo cáo trong ngân hàng thật:**
- **Hằng ngày (T-1):** sáng nay xem số của hôm qua (sau khi chạy lô cuối ngày EOD).
- **Hằng tháng:** chốt số cuối tháng, so với kế hoạch.
- **Hằng quý / năm:** báo cáo HĐQT và NHNN.

---

## 3. Ngân hàng kiếm tiền như thế nào (để hiểu vì sao có các chỉ số này)

```
   Khách gửi tiền  ──(trả lãi thấp)──▶  NGÂN HÀNG  ──(thu lãi cao)──▶  Khách vay tiền
   = HUY ĐỘNG                                                        = TÍN DỤNG (DƯ NỢ)
                        Chênh lệch lãi (NIM) = lợi nhuận chính
```

Từ sơ đồ này suy ra các câu hỏi cốt lõi, mỗi câu tương ứng với một nhóm chỉ số:

1. **Có đủ vốn để cho vay không, vốn rẻ hay đắt?** → Tổng huy động, tỷ lệ CASA, LDR.
2. **Cho vay có tăng trưởng không?** → Dư nợ, tăng trưởng tín dụng, giải ngân mới.
3. **Tiền cho vay có thu về được không?** → Nợ nhóm 2, nợ xấu, dự phòng, bao phủ nợ xấu.
4. **Có thêm khách hàng, khách có dùng sản phẩm không?** → Khách hàng mới, thẻ, kênh số.
5. **Vận hành có trơn tru, khách có hài lòng không?** → Uptime ATM, thời gian chờ, khiếu nại, SLA.

**Vì sao CASA quan trọng:** tiền gửi không kỳ hạn (tài khoản thanh toán) ngân hàng chỉ phải trả lãi gần 0%. Tiền gửi có kỳ hạn 12 tháng phải trả khoảng 5–6%/năm. CASA càng cao thì chi phí vốn càng thấp và NIM càng tốt. Vì vậy các ngân hàng bán lẻ cạnh tranh mạnh về app, lương, thanh toán để giữ tiền trong tài khoản thanh toán.

---

## 4. Từ điển chỉ số

### 4.1 Hai loại số cần phân biệt

| Loại | Ví dụ | Cách đọc khi chọn nhiều tháng | Trong dashboard |
|---|---|---|---|
| **Số dư (snapshot, "cổ phiếu")** | Tổng huy động, dư nợ, nợ xấu, khách hàng hoạt động | Lấy **cuối kỳ**, không cộng dồn (cộng số dư 12 tháng là sai) | Ngày cuối cùng trong phạm vi lọc |
| **Phát sinh (flow, "dòng chảy")** | Khách hàng mới, giải ngân, số khiếu nại, số giao dịch | **Cộng dồn** các tháng trong kỳ | Ghi rõ "(YTD)" hoặc "(lũy kế)" |

Đây là lỗi phổ biến nhất của người mới làm báo cáo ngân hàng. Ví dụ: chọn cả năm 2025 thì "Dư nợ" phải là số 31/12/2025, còn "Giải ngân mới" là tổng 12 tháng.

### 4.2 Huy động

| Chỉ số | Cách tính | Ý nghĩa | Tham chiếu ngành | DLB 31/08/2026 |
|---|---|---|---|---|
| Tổng huy động | CASA + tiền gửi có kỳ hạn, số dư cuối kỳ | Quy mô nguồn vốn từ khách hàng | | 2.168,7 tỷ |
| CASA | Số dư tiền gửi không kỳ hạn | Vốn rẻ | | 715,4 tỷ |
| Tỷ lệ CASA | CASA / Tổng huy động | Chi phí vốn thấp hay cao | Bình quân 21,5%, nhóm dẫn đầu 34–38% | 33,0% (cùng kỳ 32,6%) |
| Tăng trưởng YTD | Số dư hiện tại / số dư 31/12 năm trước − 1 | Tăng bao nhiêu từ đầu năm | Ngành 2025: +14,1% | +6,5% (8 tháng) |
| Tăng trưởng YoY | So với cùng tháng năm trước | Loại bỏ yếu tố mùa vụ | | |
| % hoàn thành kế hoạch | Số dư thực tế / kế hoạch cùng thời điểm | Đạt chỉ tiêu chưa | | 103,2% |

### 4.3 Tín dụng và rủi ro

| Chỉ số | Cách tính | Ý nghĩa | Tham chiếu | DLB 31/08/2026 |
|---|---|---|---|---|
| Dư nợ | Tổng gốc còn phải thu của các khoản vay đang hoạt động | Quy mô cho vay | | 1.632,2 tỷ |
| Tăng trưởng tín dụng YTD | So với 31/12 năm trước | Tốc độ cho vay; NHNN giao "room" tín dụng hằng năm | Ngành 2025: +17,9% | +7,7% (8 tháng) |
| Nợ nhóm 2 | Dư nợ quá hạn 10–90 ngày | **Cảnh báo sớm**: hôm nay nhóm 2, vài tháng sau có thể thành nợ xấu | | 1,79% dư nợ |
| Nợ xấu (NPL) | Dư nợ nhóm 3 + 4 + 5 | Khoản vay khó thu hồi | Mục tiêu ngành < 3%; bình quân 1,86–1,94% | 1,43% |
| Dự phòng rủi ro | Dự phòng cụ thể (theo nhóm nợ) + dự phòng chung (0,75%) | Tiền đã trích từ lợi nhuận để bù lỗ nếu mất vốn | | 16,7 tỷ |
| Tỷ lệ bao phủ nợ xấu (LLR) | Dự phòng / Nợ xấu | Đệm chống rủi ro dày hay mỏng | Ngân hàng thận trọng > 100% | 71% |
| LDR | Dư nợ / Tổng huy động | Dùng vốn huy động để cho vay nhiều hay ít | Trần quy định 85% | 75,3% |
| % hoàn thành KH dư nợ | Dư nợ / kế hoạch | | | 95,8% |

**Phân loại nợ 5 nhóm** (theo quy định của NHNN về phân loại nợ; dự án mô phỏng đơn giản hóa):

| Nhóm | Tên | Số ngày quá hạn | Trích lập cụ thể | Nợ xấu? |
|---|---|---|---|---|
| 1 | Nợ đủ tiêu chuẩn | < 10 ngày | 0% | Không |
| 2 | Nợ cần chú ý | 10–90 ngày | 5% | Không |
| 3 | Nợ dưới tiêu chuẩn | 91–180 ngày | 20% | **Có** |
| 4 | Nợ nghi ngờ | 181–360 ngày | 50% | **Có** |
| 5 | Nợ có khả năng mất vốn | > 360 ngày | 100% | **Có** |

Hai quy tắc quan trọng đã được mô phỏng:
- **Đối chiếu CIC:** nếu Trung tâm Thông tin tín dụng (CIC) ghi nhận khách hàng ở nhóm nợ cao hơn tại ngân hàng khác, DLB phải phân loại theo nhóm cao hơn.
- **Tài sản bảo đảm (TSĐB):** dự phòng cụ thể tính trên phần dư nợ sau khi trừ giá trị TSĐB đã khấu trừ. Nhờ vậy, vay mua nhà có nợ xấu nhưng dự phòng vẫn thấp.

**Ma trận chuyển nhóm nợ** (trang 3) cho biết trong kỳ có bao nhiêu khoản vay chuyển từ nhóm A sang nhóm B. Đọc theo hàng: hàng "Nhóm 1" cho biết bao nhiêu khoản từ nhóm 1 vẫn ở nhóm 1, bao nhiêu khoản rơi xuống nhóm 2, bao nhiêu khoản tất toán. Đây là công cụ dự báo nợ xấu mà khối rủi ro dùng hằng tháng.

### 4.4 Khách hàng, thẻ, kênh số

| Chỉ số | Cách tính | Ý nghĩa |
|---|---|---|
| Khách hàng hoạt động | Khách có giao dịch hoặc số dư đáng kể trong tháng | Khách "thật", không tính tài khoản ngủ |
| Khách hàng mới (YTD) | Khách mở CIF mới từ đầu năm | Hiệu quả bán hàng; tại 31/08/2026: 1.051 KH, đạt 102% kế hoạch lũy kế |
| Thẻ tín dụng phát hành / kích hoạt | Theo tháng phát hành thẻ (cohort) | Thẻ phát hành mà không kích hoạt = tốn chi phí, không có doanh thu |
| Tỷ lệ kích hoạt thẻ | Thẻ đã kích hoạt / thẻ phát hành | Chất lượng bán thẻ |
| Tỷ trọng kênh số | Giao dịch qua app/internet banking / tổng giao dịch do khách thực hiện | Chuyển đổi số, giảm tải quầy |

### 4.5 Vận hành

| Chỉ số | Cách tính | Ý nghĩa |
|---|---|---|
| Uptime ATM | Tỷ lệ thời gian ATM hoạt động | Mục tiêu nội bộ ≥ 99% |
| Số sự cố ATM | Lỗi phần cứng, kẹt tiền, mất kết nối | |
| Thời gian chờ tại quầy | Bình quân gia quyền theo số lượt phục vụ | Trải nghiệm khách tại chi nhánh |
| Tỷ lệ vi phạm SLA | Khiếu nại xử lý quá thời hạn cam kết / khiếu nại đã đóng | Mục tiêu nội bộ ≤ 10% |

### 4.6 Chất lượng dữ liệu

| Chỉ số | Ý nghĩa |
|---|---|
| Số bản ghi kiểm tra / lỗi | 15 quy tắc chạy tự động sau mỗi lô EOD (xem [04_data_quality.md](04_data_quality.md)) |
| Chiều chất lượng | Completeness (đầy đủ), Validity (hợp lệ), Uniqueness (không trùng), Consistency (nhất quán), Timeliness (kịp thời), Reconciliation (khớp sổ cái) |
| Lô FAIL | Lô có ít nhất một quy tắc mức HIGH vượt ngưỡng; cần xử lý trước khi phát hành báo cáo |

---

## 5. Các khái niệm vận hành dữ liệu cần biết

| Khái niệm | Giải thích | Ở đâu trong dự án |
|---|---|---|
| **EOD / T-1** | Cuối ngày làm việc, core banking chốt sổ và xuất file. Sáng hôm sau, báo cáo phản ánh số của ngày hôm trước (T-1) | `data/raw/eod/YYYYMMDD/` |
| **Ngày nghiệp vụ ≠ ngày giao dịch** | Giao dịch thứ Bảy, Chủ nhật, ngày lễ được hạch toán vào ngày làm việc kế tiếp | Cột `business_date` vs `txn_datetime` |
| **Trailer** | Dòng cuối file ghi số bản ghi. Nếu không khớp với số dòng thực tế, file bị từ chối và nguồn phải gửi lại | File `DLB_TXN_20260819.csv` bị từ chối, dùng bản `_R1` |
| **Đối chiếu GL** | Tổng chi tiết từng tài khoản phải bằng số dư sổ cái. Chênh lệch phải giải trình | 4 khoản chênh lệch cài sẵn, bị quy tắc `GL_RECON` bắt |
| **SCD Type 2** | Khi thông tin thay đổi (ví dụ tỉnh sáp nhập), giữ cả bản cũ và bản mới kèm ngày hiệu lực, để báo cáo quá khứ không bị "viết lại" | `dwh.dim_branch`, `dwh.dim_customer` |
| **Sáp nhập tỉnh 01/07/2025** | 63 tỉnh/thành còn 34; chi nhánh và khách hàng đổi mã tỉnh | 13 chi nhánh/PGD và 2.333 khách hàng có phiên bản mới |
| **Kế hoạch** | Chỉ tiêu năm do Hội sở giao, phân bổ theo chi nhánh và tháng trong file Excel | `excel/templates/KE_HOACH_KINH_DOANH_2024_2026.xlsx` |

---

## 6. Những câu chuyện trong dữ liệu

Bảy sự kiện dưới đây được cài vào bộ mô phỏng. Chúng tạo "điểm bất thường" để người phân tích phát hiện và giải thích, giống công việc thật của một chuyên viên báo cáo.

### 6.1 Nợ xấu tăng ở cụm Cần Thơ (03–10/2025)
- **Chuyện gì xảy ra:** vay tiêu dùng tín chấp và vay hộ kinh doanh tại CN Cần Thơ và 3 PGD trực thuộc bị quá hạn hàng loạt.
- **Xem ở đâu:** trang 3, chọn Năm = 2025.
  - Biểu đồ "Tỷ lệ nợ xấu theo chi nhánh": CN Cần Thơ vượt xa các chi nhánh khác. Nợ xấu của cả cụm (CN + 3 PGD) tăng từ 2,2% (05/2025) lên 8,7% (09/2025) và đỉnh 11,0% (11/2025), trong khi toàn hàng quanh 2–2,4%.
  - Ma trận chuyển nhóm: dòng Nhóm 1 → 2 → 3 dày lên.
  - Trang 1: nợ xấu toàn hàng đỉnh 2,42% (06 và 08/2025), cuối 2025 còn 2,20%, đến 08/2026 giảm về 1,43% sau thu hồi và xử lý rủi ro.
- **Diễn giải:** sản phẩm không có TSĐB, khách thu nhập nhạy cảm với kinh tế địa phương. Nợ nhóm 2 toàn hàng lên đỉnh 3,2–3,3% vào 05–06/2025, **trước** khi nợ xấu lên đỉnh; đây chính là giá trị của chỉ số cảnh báo sớm.
- **Hành động đề xuất:** siết điều kiện cho vay tín chấp tại cụm, tăng thu hồi nợ, xem lại chính sách phê duyệt.

### 6.2 Chiến dịch thẻ tín dụng Q2/2025
- **Chuyện gì xảy ra:** chạy chỉ tiêu phát hành thẻ tháng 4–6/2025.
- **Xem ở đâu:** trang 4, biểu đồ "Thẻ tín dụng phát hành và tỷ lệ kích hoạt" (hiển thị 18 tháng để thấy đợt này). Cột phát hành tăng gấp khoảng 3 lần (156–189 thẻ/tháng so với 45–70), còn đường kích hoạt tụt xuống 33–45%.
- **Diễn giải:** bán thẻ để chạy chỉ tiêu, khách không có nhu cầu thật nên không kích hoạt. Ngân hàng tốn phí phát hành mà không có doanh thu.
- **Hành động đề xuất:** gắn KPI với số thẻ **kích hoạt và có chi tiêu**, không phải số thẻ phát hành.

### 6.3 Sự cố ATM cụm CN Sài Gòn (08/09–17/10/2025)
- **Xem ở đâu:** trang 5.
  - "Uptime ATM theo tháng": tháng 9–10/2025 giảm rõ. Lọc Chi nhánh = CN Sài Gòn để thấy uptime cụm này chỉ còn khoảng 91–94%.
  - "Khiếu nại theo loại": nhóm "ATM không nhận được tiền" nhiều nhất.
- **Diễn giải:** một lô máy ATM cũ hoặc nhà cung cấp bảo trì kém. Sự cố vận hành kéo theo khiếu nại tăng, và khiếu nại nhiều thì SLA xử lý cũng bị ảnh hưởng.

### 6.4 Lỗi ứng dụng sau nâng cấp (09–18/03/2026)
- **Xem ở đâu:** trang 5, "Khiếu nại theo tháng và loại". Tháng 3/2026 có cột "Lỗi ứng dụng" cao gần gấp 10 lần bình thường.
- **Diễn giải:** phát hành phiên bản app mới lỗi. Tỷ trọng kênh số càng cao thì sự cố app càng ảnh hưởng rộng.

### 6.5 Tết Nguyên đán
- **Xem ở đâu:**
  - Trang 5, "Lượt rút tiền ATM": tháng Tết tăng vọt (khoảng 12 ngày trước Tết).
  - Trang 2: CASA tăng tháng trước Tết do lương và thưởng tháng 13 đổ vào tài khoản.
- **Diễn giải:** mùa vụ lặp lại hằng năm. Vận hành phải tiếp quỹ ATM sớm; so sánh nên dùng YoY để không nhầm mùa vụ với tăng trưởng thật.

### 6.6 "Chạy số" cuối quý
- **Xem ở đâu:** trang 2, "Tỷ lệ CASA". Đường CASA nhích lên ở các tháng 3, 6, 9, 12 rồi giảm lại đầu quý sau.
- **Diễn giải:** chi nhánh vận động khách doanh nghiệp chuyển tiền vào tài khoản đúng ngày chốt quý để đạt chỉ tiêu, sau đó tiền rút ra. Số cuối quý đẹp nhưng không phản ánh số dư thật.
- **Hành động đề xuất:** đánh giá chi nhánh bằng **số dư bình quân** thay vì số dư cuối kỳ.

### 6.7 Lỗi dữ liệu được cài sẵn
- **Xem ở đâu:** trang 6.
  - File giao dịch 19/08/2026 bị từ chối do trailer ghi 3.651 dòng nhưng thực tế chỉ có 3.614, sau đó dùng file gửi lại `_R1`.
  - Mã chi nhánh không tồn tại, giao dịch trùng, số tiền âm bất thường, khách thiếu CCCD, v.v.
- **Diễn giải:** trong thực tế, dữ liệu nguồn luôn có lỗi. Giá trị của hệ thống báo cáo là **phát hiện và cô lập lỗi trước khi số liệu đến tay lãnh đạo**.

---

## 7. Kịch bản trình bày 5 phút

| Phút | Nội dung | Thao tác |
|---|---|---|
| 0:00–0:45 | Bài toán: ngân hàng bán lẻ cần báo cáo vận hành hằng ngày từ dữ liệu core banking. Kiến trúc: Core → EOD file → Python ETL → PostgreSQL (stg/dwh/mart/dq) → Power BI | Mở README, chỉ sơ đồ |
| 0:45–2:00 | Trang 1: đọc 6 thẻ KPI. Huy động vượt kế hoạch, tín dụng chưa đạt; nợ xấu 1,43% sau đỉnh 2,42% giữa năm 2025 | Chỉ biểu đồ nợ xấu |
| 2:00–3:00 | Tìm nguyên nhân nợ xấu: trang 3, chọn Năm = 2025 → CN Cần Thơ, vay tiêu dùng và hộ kinh doanh; ma trận chuyển nhóm | Dùng slicer |
| 3:00–3:45 | Trang 4: chiến dịch thẻ, phát hành nhiều nhưng kích hoạt thấp → đề xuất đổi KPI | |
| 3:45–4:30 | Trang 5: sự cố ATM Sài Gòn, lỗi app 3/2026 | |
| 4:30–5:00 | Trang 6: 15 quy tắc DQ, file lỗi trailer bị từ chối. Kết: hệ thống không chỉ vẽ biểu đồ mà kiểm soát được độ tin cậy của số liệu | |

---

## 8. Câu hỏi thường gặp khi phỏng vấn

**Vì sao không cộng dư nợ các tháng lại?**
Dư nợ là số dư tại một thời điểm. Measure lấy ngày cuối cùng trong phạm vi lọc (xem [07_powerbi_model.md](07_powerbi_model.md), mục 4.1). Chỉ các chỉ số phát sinh như giải ngân hay khách hàng mới mới cộng dồn.

**Nợ xấu giảm từ 2,42% xuống 1,43% là tốt hay xấu?**
Chưa chắc tốt. Cần xem nợ xấu giảm vì thu hồi được, vì xử lý rủi ro (dùng dự phòng xóa nợ, cột "Xử lý rủi ro" trong ma trận), hay vì dư nợ tăng nhanh làm mẫu số lớn lên. Ngoài ra, nợ nhóm 2 đang ở 1,79%, cao hơn nợ xấu, nên cần theo dõi.

**Tỷ lệ bao phủ 71% có đáng lo không?**
Thấp hơn mức thận trọng (100%). Tuy nhiên, phần lớn dư nợ có tài sản bảo đảm (vay mua nhà khoảng 38%), nên dự phòng cụ thể thấp là hợp lý về mặt quy định. Đây là điểm để thảo luận, không phải lỗi.

**Làm sao biết dữ liệu đúng?**
Có 4 lớp kiểm soát:
- Kiểm tra trailer từng file.
- 15 quy tắc DQ sau mỗi lô.
- Đối chiếu chi tiết với sổ cái (GL).
- Health check đối chiếu KPI giữa DWH và Power BI: số dòng và số liệu khớp tuyệt đối.

**Dữ liệu giả lập thì có ý nghĩa gì?**
Dữ liệu ngân hàng thật không thể công khai. Bộ giả lập giữ đúng tỷ lệ, cơ cấu và xu hướng theo số liệu công khai của ngành (có dẫn nguồn), đồng thời cài sẵn các tình huống thật để phân tích.

**Phần nào bạn tự làm?**
Trả lời trung thực theo quá trình của bạn. Gợi ý: tự viết thêm measure, tự thêm một trang hoặc một truy vấn phân tích mới, rồi ghi vào README.

---

## 9. Giới hạn và giả định

- Quy mô thu nhỏ khoảng vài trăm lần so với ngân hàng thật; các tỷ lệ được giữ đúng.
- Chưa mô phỏng: thu nhập lãi/phí (NIM, CIR, ROE), ngoại tệ, cho vay doanh nghiệp lớn, giao dịch liên ngân hàng.
- Các chỉ tiêu vận hành (thời gian chờ, SLA, uptime) là giả định hợp lý vì ngân hàng không công bố (xem [02_calibration.md](02_calibration.md), mục 4).
- Quy định về phân loại nợ và dự phòng được đơn giản hóa để minh họa; không dùng làm tài liệu tuân thủ.
