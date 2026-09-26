"""Health check of the loaded data warehouse -> prints a report and saves it to logs/health_check.txt.

    python -m python.etl.health_check
"""
from __future__ import annotations

from datetime import datetime

from python.common.config import ROOT, load_config
from python.etl.db import connect

CHECKS = [
    ("Lô ETL", "SELECT batch_type, count(*) AS so_lo, count(*) FILTER (WHERE status='SUCCESS') AS thanh_cong, "
               "min(business_date), max(business_date) FROM ctl.batch GROUP BY 1 ORDER BY 1", None),
    ("Lô lỗi (kỳ vọng 0 dòng)", "SELECT batch_id, business_date, status, left(message,100) FROM ctl.batch WHERE status<>'SUCCESS'", 0),
    ("File bị từ chối (kỳ vọng 1: DLB_TXN_20260819.csv)", "SELECT file_name, message FROM ctl.file_log WHERE status='REJECTED'", 1),
    ("Số dòng các bảng chính",
     "SELECT 'dim_customer' t, count(*) FROM dwh.dim_customer UNION ALL SELECT 'dim_branch', count(*) FROM dwh.dim_branch "
     "UNION ALL SELECT 'fact_casa_txn', count(*) FROM dwh.fact_casa_txn UNION ALL SELECT 'fact_loan_balance', count(*) FROM dwh.fact_loan_balance "
     "UNION ALL SELECT 'fact_card_txn', count(*) FROM dwh.fact_card_txn UNION ALL SELECT 'fact_complaint', count(*) FROM dwh.fact_complaint "
     "UNION ALL SELECT 'kpi_branch_month', count(*) FROM mart.kpi_branch_month UNION ALL SELECT 'fact_plan', count(*) FROM dwh.fact_plan", None),
    ("Mỗi CIF/chi nhánh đúng 1 phiên bản hiện hành (kỳ vọng 0)",
     "SELECT 'customer', cif FROM dwh.dim_customer GROUP BY cif HAVING count(*) FILTER (WHERE is_current)<>1 "
     "UNION ALL SELECT 'branch', branch_code FROM dwh.dim_branch GROUP BY branch_code HAVING count(*) FILTER (WHERE is_current)<>1", 0),
    ("Đối chiếu GL (kỳ vọng 4 khoản mục cố ý)",
     "SELECT r.business_date, i.record_key, i.detail FROM dq.issue i JOIN dq.result r USING (batch_id, rule_code) "
     "WHERE i.rule_code='GL_RECON' ORDER BY 1", 4),
    ("Kế hoạch đã nạp (kỳ vọng 7200)", "SELECT count(*) FROM dwh.fact_plan", None),
    ("KPI toàn hàng (một số tháng)",
     "SELECT month_end, round(deposit_balance/1e9) huy_dong_ty, round(loan_balance/1e9) du_no_ty, round(casa_ratio*100,1) casa_pct, "
     "round(npl_ratio*100,2) npl_pct, round(ldr*100,1) ldr_pct, round(100*deposit_balance/plan_deposit,1) ht_kh_hd_pct "
     "FROM mart.v_kpi_bank_month WHERE month_end IN ('2023-12-31','2024-12-31','2025-12-31','2026-08-31') ORDER BY 1", None),
]


def main() -> None:
    out, ok = [f"HEALTH CHECK dlb_dwh - {datetime.now():%Y-%m-%d %H:%M}", ""], True
    with connect(load_config().pg_dsn) as conn:
        for title, sql, expect in CHECKS:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            cols = [d.name for d in cur.description]
            status = ""
            if expect is not None:
                passed = len(rows) == expect
                ok &= passed
                status = "  [OK]" if passed else f"  [KIEM TRA LAI: {len(rows)} dong]"
            out.append(f"== {title}{status}")
            out.append(" | ".join(cols))
            out += [" | ".join("" if v is None else str(v) for v in r) for r in rows[:15]]
            out.append("")
    out.append("KET LUAN: " + ("TAT CA DEU DUNG" if ok else "CO MUC CAN KIEM TRA"))
    text = "\n".join(out)
    print(text)
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "health_check.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
