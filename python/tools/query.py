"""Query tool to execute SQL queries on PostgreSQL DWH and display results in formatted tables.

Usage:
    python -m python.tools.query "SELECT * FROM rpt.dim_branch LIMIT 5;"
    python -m python.tools.query file.sql
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pandas as pd
from python.common.config import ROOT, load_config
from python.etl.db import connect

warnings.filterwarnings("ignore", category=UserWarning)

# Set UTF-8 output encoding for Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def run_query(sql: str) -> None:
    dsn = load_config().pg_dsn
    with connect(dsn) as conn:
        df = pd.read_sql(sql, conn)
        if df.empty:
            print("(0 rows returned)")
        else:
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", 1000)
            pd.set_option("display.max_rows", 100)
            print(df.to_string(index=False))
            print(f"\n({len(df)} rows)")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m python.tools.query \"SELECT * FROM schema.table LIMIT 10;\"")
        print("   or: python -m python.tools.query script.sql")
        return

    arg = sys.argv[1].strip()
    if os.path.exists(arg) or (ROOT / arg).exists():
        p = Path(arg) if os.path.exists(arg) else ROOT / arg
        sql = p.read_text(encoding="utf-8")
    else:
        sql = arg

    run_query(sql)


if __name__ == "__main__":
    main()
