"""Generate docs/03_data_dictionary.md from the live database catalog.

    python -m python.etl.export_data_dictionary
"""
from __future__ import annotations

from python.common.config import ROOT, load_config
from python.common.layouts import LAYOUTS
from python.etl.db import connect

DESCRIPTIONS = {
    "dwh.dim_date": "Lịch: ngày làm việc, ngày lễ, cuối tháng/quý, số thứ tự ngày làm việc (tính SLA)",
    "dwh.dim_province": "34 tỉnh/thành sau sáp nhập 01/07/2025",
    "dwh.map_province_old_new": "Chuyển đổi 63 tỉnh/thành cũ → 34 đơn vị mới",
    "dwh.dim_branch": "Chi nhánh/PGD, SCD Type 2 (đổi tỉnh/thành từ 01/07/2025)",
    "dwh.dim_customer": "Khách hàng, SCD Type 2 theo phân khúc, tỉnh/thành, chi nhánh quản lý, trạng thái",
    "dwh.dim_product": "Danh mục sản phẩm huy động, tín dụng, thẻ",
    "dwh.dim_channel": "Kênh giao dịch",
    "dwh.dim_loan_group": "5 nhóm nợ, ngưỡng số ngày quá hạn, tỷ lệ trích lập dự phòng cụ thể",
    "dwh.dim_mcc": "Mã ngành hàng chấp nhận thẻ (MCC)",
    "dwh.dim_gl_account": "Tài khoản sổ cái dùng để đối chiếu",
    "dwh.dim_casa_account": "Tài khoản thanh toán (trạng thái mới nhất)",
    "dwh.dim_term_deposit": "Hợp đồng tiền gửi có kỳ hạn; tái tục tạo hợp đồng mới (rollover_of)",
    "dwh.dim_loan": "Hợp đồng tín dụng (kể cả tài khoản thẻ tín dụng LN_CREDITCARD)",
    "dwh.dim_card": "Thẻ ghi nợ và thẻ tín dụng",
    "dwh.dim_atm": "Danh mục ATM",
    "dwh.fact_casa_txn": "Giao dịch tài khoản thanh toán; partition theo năm của business_date",
    "dwh.fact_casa_balance": "Số dư tài khoản thanh toán cuối tháng",
    "dwh.fact_td_balance": "Số dư tiền gửi có kỳ hạn cuối tháng",
    "dwh.fact_loan_balance": "Dư nợ cuối tháng, DPD, nhóm nợ core và nhóm nợ DWH tính lại, dự phòng",
    "dwh.fact_card_txn": "Giao dịch thẻ tín dụng (kể cả giao dịch bị từ chối)",
    "dwh.fact_atm_daily": "Hoạt động ATM theo ngày: rút tiền on-us/off-us, uptime, sự cố, hết tiền",
    "dwh.fact_branch_ops": "Vận hành quầy theo ngày làm việc: giao dịch, thời gian chờ",
    "dwh.fact_complaint": "Khiếu nại (accumulating snapshot): hạn SLA, ngày xử lý, vi phạm SLA",
    "dwh.fact_gl_balance": "Số dư sổ cái cuối tháng theo chi nhánh",
    "dwh.fact_plan": "Kế hoạch kinh doanh (nạp từ Excel)",
    "mart.kpi_branch_month": "KPI theo chi nhánh × tháng: số dư, nợ xấu, dự phòng, dòng tiền, khách hàng, thẻ, kênh, vận hành, kế hoạch",
    "mart.deposit_daily": "Số dư huy động theo ngày (value date) × chi nhánh × sản phẩm (nguồn báo cáo T-1)",
    "mart.loan_migration": "Ma trận chuyển nhóm nợ tháng này so với tháng trước",
    "mart.channel_month": "Giao dịch theo kênh × loại × chi nhánh × tháng",
    "mart.card_spend_month": "Chi tiêu thẻ tín dụng theo sản phẩm × nhóm MCC × tháng",
    "mart.customer_month": "Cơ sở khách hàng theo chi nhánh × phân khúc × tháng",
    "ctl.batch": "Nhật ký lô ETL", "ctl.file_log": "Nhật ký file (trailer, số dòng, trạng thái)",
    "ctl.step_log": "Thời gian từng bước xử lý lô",
    "dq.rule": "Danh mục quy tắc chất lượng dữ liệu", "dq.result": "Kết quả kiểm tra theo lô",
    "dq.issue": "Bản ghi lỗi chi tiết",
}


def main() -> None:
    out = ["# Từ điển dữ liệu", "", "*Tự sinh bởi `python -m python.etl.export_data_dictionary`.*", "",
           "## 1. File trích xuất core banking", "",
           "Định dạng: UTF-8, phân cách `|`, dòng tiêu đề, dòng cuối `TRL|<số bản ghi>|<ngày>`. "
           "Ngày dạng `YYYYMMDD`, thời điểm dạng `YYYY-MM-DD HH:MM:SS`, số tiền là số nguyên VND.", "",
           "| File | Cột |", "|---|---|"]
    for e, cols in LAYOUTS.items():
        out.append(f"| `DLB_{e}_YYYYMMDD.csv` | {', '.join(cols)} |")
    with connect(load_config().pg_dsn) as conn:
        rows = conn.execute("""
            SELECT c.table_schema, c.table_name, c.column_name, c.data_type
            FROM information_schema.columns c
            JOIN information_schema.tables t USING (table_schema, table_name)
            WHERE c.table_schema IN ('dwh', 'mart', 'ctl', 'dq') AND t.table_type = 'BASE TABLE'
              AND c.table_name NOT LIKE 'fact_casa_txn_%'
            ORDER BY c.table_schema, c.table_name, c.ordinal_position""").fetchall()
        counts = {}
        for s, t in {(r[0], r[1]) for r in rows}:
            counts[f"{s}.{t}"] = conn.execute(f"SELECT count(*) FROM {s}.{t}").fetchone()[0]
    sections = {"dwh": "## 2. Kho dữ liệu (schema `dwh`)", "mart": "## 3. Mart báo cáo (schema `mart`)",
                "ctl": "## 4. Điều khiển lô (schema `ctl`)", "dq": "## 5. Chất lượng dữ liệu (schema `dq`)"}
    cur_schema, cur_table = None, None
    for s, t, col, typ in rows:
        full = f"{s}.{t}"
        if s != cur_schema:
            out += ["", sections[s]]
            cur_schema = s
        if full != cur_table:
            out += ["", f"### `{full}`", "", f"{DESCRIPTIONS.get(full, '')}  ", f"Số dòng: {counts[full]:,}", "",
                    "| Cột | Kiểu |", "|---|---|"]
            cur_table = full
        out.append(f"| {col} | {typ} |")
    out += ["", "## 6. View báo cáo", "",
            "| View | Nội dung |", "|---|---|",
            "| `mart.v_kpi_bank_month` | KPI toàn hàng và các tỷ lệ: CASA, NPL, LDR, bao phủ nợ xấu, tỷ trọng kênh số |",
            "| `mart.v_daily_deposit_report` | Báo cáo huy động T-1: biến động so với ngày trước, đầu tháng, đầu năm |",
            "| `mart.v_td_maturity_ladder` | Thang đáo hạn tiền gửi có kỳ hạn |",
            "| `mart.v_branch` | Chi nhánh hiện hành kèm chi nhánh quản lý, tỉnh/thành, vùng |",
            "| `mart.v_customer_masked` | Khách hàng đã che thông tin cá nhân (tên, CCCD, SĐT) |",
            "| `mart.v_dq_summary` | Kết quả chất lượng dữ liệu theo lô |"]
    (ROOT / "docs" / "03_data_dictionary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("docs/03_data_dictionary.md written")


if __name__ == "__main__":
    main()
