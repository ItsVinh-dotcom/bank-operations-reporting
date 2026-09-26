"""Create (or re-create) the DLB data warehouse objects and load reference data.

    python -m python.etl.setup_db            # create objects (idempotent)
    python -m python.etl.setup_db --reset    # DROP all schemas first (full rebuild)
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from python.common.config import load_config
from python.etl.db import SQL_DIR, SQL_FILES, connect, run_sql_file

log = logging.getLogger(__name__)

REFERENCE = [  # (csv file, table, columns)
    ("provinces.csv", "dwh.dim_province", ["province_code", "province_name", "province_type", "region", "is_merged_2025"]),
    ("provinces_old_to_new.csv", "dwh.map_province_old_new", ["old_province_code", "old_province_name", "new_province_code"]),
    ("products.csv", "dwh.dim_product", ["product_code", "product_name", "product_group", "product_type", "customer_type",
                                         "term_months_min", "term_months_max"]),
    ("channels.csv", "dwh.dim_channel", ["channel_code", "channel_name", "channel_group"]),
    ("loan_groups.csv", "dwh.dim_loan_group", ["loan_group", "loan_group_name", "dpd_from", "dpd_to", "is_npl",
                                              "specific_provision_rate"]),
    ("mcc.csv", "dwh.dim_mcc", ["mcc", "mcc_name", "mcc_group"]),
    ("gl_accounts.csv", "dwh.dim_gl_account", ["gl_account", "gl_name", "gl_group", "sign"]),
    ("holidays.csv", "dwh.ref_holiday", ["holiday_date", "holiday_name"]),
]
COLLATERAL = [("SO_TIET_KIEM", 1.0), ("BAT_DONG_SAN", 0.5), ("O_TO", 0.3), ("BDS_HANG_TON_KHO", 0.4), ("BDS_MAY_MOC", 0.4)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="drop and recreate all schemas")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config()
    with connect(cfg.pg_dsn) as conn:
        if a.reset:
            log.warning("dropping schemas ctl, stg, dwh, mart, dq")
            conn.execute("DROP SCHEMA IF EXISTS mart, dq, dwh, stg, ctl CASCADE")
        for f in SQL_FILES:
            run_sql_file(conn, SQL_DIR / f)
        # reference data (truncate + reload)
        for fname, table, cols in reversed(REFERENCE):
            conn.execute(f"TRUNCATE {table} CASCADE")
        for fname, table, cols in REFERENCE:
            df = pd.read_csv(cfg.paths.reference / fname, dtype=str).fillna("")
            with conn.cursor() as cur:
                with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
                    for row in df[cols].itertuples(index=False):
                        cp.write_row([None if v == "" else v for v in row])
            log.info("loaded %-28s %4d rows", table, len(df))
        conn.execute("TRUNCATE dwh.ref_collateral_factor")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO dwh.ref_collateral_factor VALUES (%s, %s)", COLLATERAL)
        conn.execute("CALL dwh.sp_build_dim_date('2023-01-01', '2027-12-31')")
        conn.commit()
    log.info("database ready")


if __name__ == "__main__":
    main()
