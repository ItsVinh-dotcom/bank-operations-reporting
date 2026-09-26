# Từ điển dữ liệu

*Tự sinh bởi `python -m python.etl.export_data_dictionary`.*

## 1. File trích xuất core banking

Định dạng: UTF-8, phân cách `|`, dòng tiêu đề, dòng cuối `TRL|<số bản ghi>|<ngày>`. Ngày dạng `YYYYMMDD`, thời điểm dạng `YYYY-MM-DD HH:MM:SS`, số tiền là số nguyên VND.

| File | Cột |
|---|---|
| `DLB_BRANCH_YYYYMMDD.csv` | branch_code, branch_name, branch_level, parent_branch_code, province_code, district, open_date, status, effective_date |
| `DLB_CUSTOMER_YYYYMMDD.csv` | cif, customer_type, full_name, gender, date_of_birth, id_number, tax_code, phone, province_code, home_branch_code, segment, occupation, industry, open_date, close_date, status, record_action, effective_date |
| `DLB_CASA_ACCOUNT_YYYYMMDD.csv` | account_no, cif, product_code, branch_code, open_date, close_date, status |
| `DLB_CASA_BALANCE_YYYYMMDD.csv` | snapshot_date, account_no, balance, accrued_interest, status |
| `DLB_TXN_YYYYMMDD.csv` | txn_id, account_no, txn_datetime, business_date, txn_type, dr_cr, amount, channel_code, branch_code, atm_id, counterparty_bank, description, is_reversal |
| `DLB_TERM_DEPOSIT_YYYYMMDD.csv` | td_id, cif, product_code, branch_code, open_date, maturity_date, term_months, interest_rate, principal, rollover_of, close_date, close_reason |
| `DLB_TD_BALANCE_YYYYMMDD.csv` | snapshot_date, td_id, principal, accrued_interest, status |
| `DLB_LOAN_YYYYMMDD.csv` | loan_id, cif, product_code, branch_code, disbursement_date, maturity_date, term_months, approved_amount, interest_rate, repayment_method, collateral_type, collateral_value, close_date, close_reason |
| `DLB_LOAN_BALANCE_YYYYMMDD.csv` | snapshot_date, loan_id, outstanding_principal, overdue_principal, dpd, loan_group, cic_group, accrued_interest, status |
| `DLB_CARD_YYYYMMDD.csv` | card_id, masked_pan, cif, product_code, account_ref, branch_code, issue_date, activation_date, expiry_date, credit_limit, status, close_date |
| `DLB_CARD_TXN_YYYYMMDD.csv` | card_txn_id, card_id, txn_datetime, business_date, mcc, merchant_name, amount, is_ecommerce, is_international, auth_status |
| `DLB_ATM_DAILY_YYYYMMDD.csv` | business_date, atm_id, branch_code, onus_wd_count, onus_wd_amount, offus_wd_count, offus_wd_amount, uptime_minutes, incident_count, cash_out_flag |
| `DLB_BRANCH_OPS_YYYYMMDD.csv` | business_date, branch_code, tellers, counter_txn_count, service_request_count, avg_wait_minutes, avg_service_minutes, pct_wait_under_15m |
| `DLB_COMPLAINT_YYYYMMDD.csv` | complaint_id, cif, branch_code, received_datetime, channel, complaint_type, sla_days, resolved_datetime, status, is_valid |
| `DLB_GL_BALANCE_YYYYMMDD.csv` | snapshot_date, branch_code, gl_account, balance |

## 4. Điều khiển lô (schema `ctl`)

### `ctl.batch`

Nhật ký lô ETL  
Số dòng: 53

| Cột | Kiểu |
|---|---|
| batch_id | integer |
| business_date | date |
| batch_type | text |
| folder | text |
| status | text |
| started_at | timestamp with time zone |
| finished_at | timestamp with time zone |
| message | text |

### `ctl.file_log`

Nhật ký file (trailer, số dòng, trạng thái)  
Số dòng: 761

| Cột | Kiểu |
|---|---|
| batch_id | integer |
| entity | text |
| file_name | text |
| revision | integer |
| trailer_count | integer |
| loaded_count | integer |
| status | text |
| message | text |
| logged_at | timestamp with time zone |

### `ctl.step_log`

Thời gian từng bước xử lý lô  
Số dòng: 371

| Cột | Kiểu |
|---|---|
| batch_id | integer |
| step | text |
| rows_affected | bigint |
| started_at | timestamp with time zone |
| finished_at | timestamp with time zone |

## 5. Chất lượng dữ liệu (schema `dq`)

### `dq.issue`

Bản ghi lỗi chi tiết  
Số dòng: 3,626

| Cột | Kiểu |
|---|---|
| batch_id | integer |
| rule_code | text |
| record_key | text |
| detail | text |

### `dq.result`

Kết quả kiểm tra theo lô  
Số dòng: 728

| Cột | Kiểu |
|---|---|
| batch_id | integer |
| business_date | date |
| rule_code | text |
| checked_rows | bigint |
| failed_rows | bigint |
| failed_amount | numeric |
| status | text |
| checked_at | timestamp with time zone |

### `dq.rule`

Danh mục quy tắc chất lượng dữ liệu  
Số dòng: 15

| Cột | Kiểu |
|---|---|
| rule_code | text |
| entity | text |
| dimension | text |
| severity | text |
| description | text |
| threshold_pct | numeric |

## 2. Kho dữ liệu (schema `dwh`)

### `dwh.dim_atm`

Danh mục ATM  
Số dòng: 61

| Cột | Kiểu |
|---|---|
| atm_id | text |
| branch_code | text |
| first_seen | date |

### `dwh.dim_branch`

Chi nhánh/PGD, SCD Type 2 (đổi tỉnh/thành từ 01/07/2025)  
Số dòng: 53

| Cột | Kiểu |
|---|---|
| branch_sk | integer |
| branch_code | text |
| branch_name | text |
| branch_level | text |
| parent_branch_code | text |
| managing_branch_code | text |
| province_code | text |
| province_name | text |
| region | text |
| district | text |
| open_date | date |
| status | text |
| valid_from | date |
| valid_to | date |
| is_current | boolean |

### `dwh.dim_card`

Thẻ ghi nợ và thẻ tín dụng  
Số dòng: 14,879

| Cột | Kiểu |
|---|---|
| card_id | text |
| masked_pan | text |
| cif | text |
| product_code | text |
| account_ref | text |
| branch_code | text |
| issue_date | date |
| activation_date | date |
| expiry_date | date |
| credit_limit | bigint |
| status | text |
| close_date | date |
| batch_id | integer |

### `dwh.dim_casa_account`

Tài khoản thanh toán (trạng thái mới nhất)  
Số dòng: 13,795

| Cột | Kiểu |
|---|---|
| account_no | text |
| cif | text |
| product_code | text |
| branch_code | text |
| open_date | date |
| close_date | date |
| status | text |
| batch_id | integer |

### `dwh.dim_channel`

Kênh giao dịch  
Số dòng: 6

| Cột | Kiểu |
|---|---|
| channel_code | text |
| channel_name | text |
| channel_group | text |

### `dwh.dim_customer`

Khách hàng, SCD Type 2 theo phân khúc, tỉnh/thành, chi nhánh quản lý, trạng thái  
Số dòng: 16,569

| Cột | Kiểu |
|---|---|
| customer_sk | integer |
| cif | text |
| customer_type | text |
| full_name | text |
| gender | text |
| date_of_birth | date |
| id_number | text |
| tax_code | text |
| phone | text |
| province_code | text |
| home_branch_code | text |
| segment | text |
| occupation | text |
| industry | text |
| open_date | date |
| close_date | date |
| status | text |
| valid_from | date |
| valid_to | date |
| is_current | boolean |
| batch_id | integer |

### `dwh.dim_date`

Lịch: ngày làm việc, ngày lễ, cuối tháng/quý, số thứ tự ngày làm việc (tính SLA)  
Số dòng: 1,826

| Cột | Kiểu |
|---|---|
| date_key | integer |
| full_date | date |
| day_of_month | smallint |
| day_of_week | smallint |
| day_name_vi | text |
| week_of_year | smallint |
| month_no | smallint |
| month_name_vi | text |
| quarter_no | smallint |
| year_no | smallint |
| year_month | text |
| month_start | date |
| month_end | date |
| is_weekend | boolean |
| is_holiday | boolean |
| holiday_name | text |
| is_business_day | boolean |
| is_month_end | boolean |
| is_quarter_end | boolean |
| business_day_seq | integer |

### `dwh.dim_gl_account`

Tài khoản sổ cái dùng để đối chiếu  
Số dòng: 18

| Cột | Kiểu |
|---|---|
| gl_account | text |
| gl_name | text |
| gl_group | text |
| sign | character |

### `dwh.dim_loan`

Hợp đồng tín dụng (kể cả tài khoản thẻ tín dụng LN_CREDITCARD)  
Số dòng: 8,972

| Cột | Kiểu |
|---|---|
| loan_id | text |
| cif | text |
| product_code | text |
| branch_code | text |
| disbursement_date | date |
| maturity_date | date |
| term_months | smallint |
| term_bucket | text |
| approved_amount | bigint |
| interest_rate | numeric |
| repayment_method | text |
| collateral_type | text |
| collateral_value | bigint |
| close_date | date |
| close_reason | text |
| batch_id | integer |

### `dwh.dim_loan_group`

5 nhóm nợ, ngưỡng số ngày quá hạn, tỷ lệ trích lập dự phòng cụ thể  
Số dòng: 5

| Cột | Kiểu |
|---|---|
| loan_group | smallint |
| loan_group_name | text |
| dpd_from | integer |
| dpd_to | integer |
| is_npl | boolean |
| specific_provision_rate | numeric |

### `dwh.dim_mcc`

Mã ngành hàng chấp nhận thẻ (MCC)  
Số dòng: 17

| Cột | Kiểu |
|---|---|
| mcc | text |
| mcc_name | text |
| mcc_group | text |

### `dwh.dim_product`

Danh mục sản phẩm huy động, tín dụng, thẻ  
Số dòng: 19

| Cột | Kiểu |
|---|---|
| product_code | text |
| product_name | text |
| product_group | text |
| product_type | text |
| customer_type | text |
| term_months_min | integer |
| term_months_max | integer |

### `dwh.dim_province`

34 tỉnh/thành sau sáp nhập 01/07/2025  
Số dòng: 34

| Cột | Kiểu |
|---|---|
| province_code | text |
| province_name | text |
| province_type | text |
| region | text |
| is_merged_2025 | boolean |

### `dwh.dim_term_deposit`

Hợp đồng tiền gửi có kỳ hạn; tái tục tạo hợp đồng mới (rollover_of)  
Số dòng: 11,239

| Cột | Kiểu |
|---|---|
| td_id | text |
| cif | text |
| product_code | text |
| branch_code | text |
| open_date | date |
| maturity_date | date |
| term_months | smallint |
| interest_rate | numeric |
| principal | bigint |
| rollover_of | text |
| close_date | date |
| close_reason | text |
| batch_id | integer |

### `dwh.fact_atm_daily`

Hoạt động ATM theo ngày: rút tiền on-us/off-us, uptime, sự cố, hết tiền  
Số dòng: 59,414

| Cột | Kiểu |
|---|---|
| report_date | date |
| atm_id | text |
| branch_code | text |
| onus_wd_count | integer |
| onus_wd_amount | bigint |
| offus_wd_count | integer |
| offus_wd_amount | bigint |
| uptime_minutes | integer |
| uptime_pct | numeric |
| incident_count | integer |
| cash_out_flag | boolean |
| batch_id | integer |

### `dwh.fact_branch_ops`

Vận hành quầy theo ngày làm việc: giao dịch, thời gian chờ  
Số dòng: 26,520

| Cột | Kiểu |
|---|---|
| business_date | date |
| branch_code | text |
| tellers | integer |
| counter_txn_count | integer |
| service_request_count | integer |
| avg_wait_minutes | numeric |
| avg_service_minutes | numeric |
| pct_wait_under_15m | numeric |
| batch_id | integer |

### `dwh.fact_card_txn`

Giao dịch thẻ tín dụng (kể cả giao dịch bị từ chối)  
Số dòng: 243,107

| Cột | Kiểu |
|---|---|
| card_txn_id | text |
| card_id | text |
| txn_datetime | timestamp without time zone |
| business_date | date |
| date_key | integer |
| mcc | text |
| merchant_name | text |
| amount | bigint |
| is_ecommerce | boolean |
| is_international | boolean |
| auth_status | text |
| batch_id | integer |

### `dwh.fact_casa_balance`

Số dư tài khoản thanh toán cuối tháng  
Số dòng: 357,903

| Cột | Kiểu |
|---|---|
| snapshot_date | date |
| account_no | text |
| balance | bigint |
| accrued_interest | bigint |
| status | text |
| batch_id | integer |

### `dwh.fact_casa_txn`

Giao dịch tài khoản thanh toán; partition theo năm của business_date  
Số dòng: 3,709,469

| Cột | Kiểu |
|---|---|
| txn_id | text |
| account_no | text |
| txn_datetime | timestamp without time zone |
| business_date | date |
| date_key | integer |
| txn_type | text |
| dr_cr | character |
| amount | bigint |
| signed_amount | bigint |
| channel_code | text |
| branch_code | text |
| atm_id | text |
| counterparty_bank | text |
| description | text |
| is_reversal | boolean |
| batch_id | integer |

### `dwh.fact_complaint`

Khiếu nại (accumulating snapshot): hạn SLA, ngày xử lý, vi phạm SLA  
Số dòng: 3,145

| Cột | Kiểu |
|---|---|
| complaint_id | text |
| cif | text |
| branch_code | text |
| received_datetime | timestamp without time zone |
| received_date | date |
| channel | text |
| complaint_type | text |
| sla_days | integer |
| sla_due_date | date |
| resolved_datetime | timestamp without time zone |
| resolution_bdays | integer |
| is_sla_breached | boolean |
| status | text |
| is_valid | text |
| batch_id | integer |

### `dwh.fact_gl_balance`

Số dư sổ cái cuối tháng theo chi nhánh  
Số dòng: 11,820

| Cột | Kiểu |
|---|---|
| snapshot_date | date |
| branch_code | text |
| gl_account | text |
| balance | bigint |
| batch_id | integer |

### `dwh.fact_loan_balance`

Dư nợ cuối tháng, DPD, nhóm nợ core và nhóm nợ DWH tính lại, dự phòng  
Số dòng: 132,857

| Cột | Kiểu |
|---|---|
| snapshot_date | date |
| loan_id | text |
| outstanding_principal | bigint |
| overdue_principal | bigint |
| dpd | integer |
| core_loan_group | smallint |
| cic_group | smallint |
| dpd_group | smallint |
| loan_group | smallint |
| accrued_interest | bigint |
| specific_provision | bigint |
| general_provision | bigint |
| status | text |
| batch_id | integer |

### `dwh.fact_plan`

Kế hoạch kinh doanh (nạp từ Excel)  
Số dòng: 7,200

| Cột | Kiểu |
|---|---|
| plan_month | date |
| branch_code | text |
| kpi_code | text |
| plan_value | numeric |
| plan_version | text |
| loaded_at | timestamp with time zone |

### `dwh.fact_td_balance`

Số dư tiền gửi có kỳ hạn cuối tháng  
Số dòng: 73,867

| Cột | Kiểu |
|---|---|
| snapshot_date | date |
| td_id | text |
| principal | bigint |
| accrued_interest | bigint |
| status | text |
| batch_id | integer |

### `dwh.map_province_old_new`

Chuyển đổi 63 tỉnh/thành cũ → 34 đơn vị mới  
Số dòng: 63

| Cột | Kiểu |
|---|---|
| old_province_code | text |
| old_province_name | text |
| new_province_code | text |

### `dwh.ref_collateral_factor`

  
Số dòng: 5

| Cột | Kiểu |
|---|---|
| collateral_type | text |
| deduction_rate | numeric |

### `dwh.ref_holiday`

  
Số dòng: 35

| Cột | Kiểu |
|---|---|
| holiday_date | date |
| holiday_name | text |

## 3. Mart báo cáo (schema `mart`)

### `mart.card_spend_month`

Chi tiêu thẻ tín dụng theo sản phẩm × nhóm MCC × tháng  
Số dòng: 766

| Cột | Kiểu |
|---|---|
| month_end | date |
| product_code | text |
| mcc_group | text |
| txn_count | integer |
| amount | numeric |
| ecom_count | integer |
| intl_count | integer |
| declined_count | integer |

### `mart.channel_month`

Giao dịch theo kênh × loại × chi nhánh × tháng  
Số dòng: 33,307

| Cột | Kiểu |
|---|---|
| month_end | date |
| branch_code | text |
| channel_code | text |
| txn_type | text |
| customer_type | text |
| txn_count | integer |
| amount | numeric |

### `mart.customer_month`

Cơ sở khách hàng theo chi nhánh × phân khúc × tháng  
Số dòng: 5,072

| Cột | Kiểu |
|---|---|
| month_end | date |
| branch_code | text |
| customer_type | text |
| segment | text |
| active_customers | integer |
| new_customers | integer |
| closed_customers | integer |
| with_loan | integer |
| with_td | integer |
| with_credit_card | integer |

### `mart.deposit_daily`

Số dư huy động theo ngày (value date) × chi nhánh × sản phẩm (nguồn báo cáo T-1)  
Số dòng: 239,579

| Cột | Kiểu |
|---|---|
| balance_date | date |
| branch_code | text |
| product_code | text |
| balance | numeric |

### `mart.kpi_branch_month`

KPI theo chi nhánh × tháng: số dư, nợ xấu, dự phòng, dòng tiền, khách hàng, thẻ, kênh, vận hành, kế hoạch  
Số dòng: 1,320

| Cột | Kiểu |
|---|---|
| month_end | date |
| branch_code | text |
| casa_balance | numeric |
| td_balance | numeric |
| deposit_balance | numeric |
| loan_balance | numeric |
| loan_retail_balance | numeric |
| loan_sme_balance | numeric |
| group2_balance | numeric |
| npl_balance | numeric |
| specific_provision | numeric |
| general_provision | numeric |
| writeoff_amount | numeric |
| disbursement_amount | numeric |
| disbursement_count | integer |
| new_customers | integer |
| closed_customers | integer |
| active_customers | integer |
| credit_cards_issued | integer |
| credit_cards_activated | integer |
| active_credit_cards | integer |
| card_spend_amount | numeric |
| casa_txn_count | integer |
| digital_txn_count | integer |
| counter_txn_count | integer |
| atm_uptime_pct | numeric |
| avg_wait_minutes | numeric |
| complaints_received | integer |
| complaints_sla_breached | integer |
| plan_deposit | numeric |
| plan_casa | numeric |
| plan_loan | numeric |
| plan_new_customers | numeric |
| plan_credit_cards | numeric |
| refreshed_at | timestamp with time zone |

### `mart.loan_migration`

Ma trận chuyển nhóm nợ tháng này so với tháng trước  
Số dòng: 2,346

| Cột | Kiểu |
|---|---|
| month_end | date |
| product_code | text |
| from_state | text |
| to_state | text |
| loan_count | integer |
| amount_from | numeric |
| amount_to | numeric |

## 6. View báo cáo

| View | Nội dung |
|---|---|
| `mart.v_kpi_bank_month` | KPI toàn hàng và các tỷ lệ: CASA, NPL, LDR, bao phủ nợ xấu, tỷ trọng kênh số |
| `mart.v_daily_deposit_report` | Báo cáo huy động T-1: biến động so với ngày trước, đầu tháng, đầu năm |
| `mart.v_td_maturity_ladder` | Thang đáo hạn tiền gửi có kỳ hạn |
| `mart.v_branch` | Chi nhánh hiện hành kèm chi nhánh quản lý, tỉnh/thành, vùng |
| `mart.v_customer_masked` | Khách hàng đã che thông tin cá nhân (tên, CCCD, SĐT) |
| `mart.v_dq_summary` | Kết quả chất lượng dữ liệu theo lô |
