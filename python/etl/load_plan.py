"""Load the business plan from Excel (sheet KeHoach_Thang) into dwh.fact_plan and refresh plan columns.

    python -m python.etl.load_plan [--file excel/templates/KE_HOACH_KINH_DOANH_2024_2026.xlsx] [--version V1]

The workbook must have been saved by Excel (or recalculated) so that formula results are cached.
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from python.common.config import ROOT, load_config
from python.etl.db import connect

log = logging.getLogger(__name__)
DEFAULT = ROOT / "excel" / "templates" / "KE_HOACH_KINH_DOANH_2024_2026.xlsx"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(DEFAULT))
    ap.add_argument("--version", default="V1")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    df = pd.read_excel(a.file, sheet_name="KeHoach_Thang", dtype={"branch_code": str})
    if df.plan_value.isna().any():
        raise SystemExit("plan_value has empty cells: open the workbook in Excel and save it (formulas not calculated)")
    df["plan_month"] = pd.to_datetime(df.plan_month).dt.date
    with connect(load_config().pg_dsn) as conn:
        conn.execute("DELETE FROM dwh.fact_plan WHERE plan_version = %s", (a.version,))
        with conn.cursor() as cur:
            with cur.copy("COPY dwh.fact_plan (plan_month, branch_code, kpi_code, plan_value, plan_version) FROM STDIN") as cp:
                for r in df.itertuples(index=False):
                    cp.write_row((r.plan_month, r.branch_code, r.kpi_code, float(r.plan_value), a.version))
        conn.execute("CALL mart.sp_refresh_plan()")
        conn.commit()
    log.info("loaded %d plan rows (version %s)", len(df), a.version)


if __name__ == "__main__":
    main()
