"""Run the ETL: load core-banking extracts batch by batch into PostgreSQL.

    python -m python.etl.run_pipeline --mode history      # initial migration (monthly batches)
    python -m python.etl.run_pipeline --mode eod          # daily EOD batches
    python -m python.etl.run_pipeline --mode all          # history + eod
    python -m python.etl.run_pipeline --mode eod --date 2026-08-19   # one specific day

Already successful batches are skipped, so the command can be re-run safely after a failure.
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

from python.common.config import load_config
from python.common.layouts import LAYOUTS
from python.etl.db import connect, copy_file

log = logging.getLogger("etl")
ANALYZE_TABLES = ["dwh.fact_casa_txn", "dwh.fact_casa_balance", "dwh.fact_td_balance", "dwh.fact_loan_balance",
                  "dwh.fact_card_txn", "dwh.dim_customer", "dwh.dim_loan", "dwh.dim_card", "dwh.dim_term_deposit",
                  "dwh.dim_casa_account", "dwh.fact_complaint"]
FILE_RE = re.compile(r"^(?P<bank>[A-Z]+)_(?P<entity>[A-Z_]+?)_(?P<date>\d{8})(?:_R(?P<rev>\d+))?\.csv$")


def read_trailer(path: Path) -> tuple[int, int]:
    """Return (trailer_count, actual_body_rows)."""
    with open(path, "rb") as fh:
        n_lines = sum(1 for _ in fh)
        fh.seek(max(0, fh.tell() - 200))
        last = fh.read().decode("utf-8", errors="ignore").strip().splitlines()[-1]
    parts = last.split("|")
    if parts[0] != "TRL":
        raise ValueError(f"{path.name}: missing trailer")
    return int(parts[1]), n_lines - 2


def pick_files(folder: Path) -> dict[str, list[tuple[int, Path]]]:
    files: dict[str, list[tuple[int, Path]]] = {}
    for f in folder.glob("*.csv"):
        m = FILE_RE.match(f.name)
        if m and m["entity"] in LAYOUTS:
            files.setdefault(m["entity"], []).append((int(m["rev"] or 0), f))
    return {k: sorted(v) for k, v in files.items()}


def business_date_of(folder: Path, batch_type: str) -> datetime.date:
    if batch_type == "EOD":
        return datetime.strptime(folder.name, "%Y%m%d").date()
    return (pd.Period(folder.name, "M").end_time).date()


def run_batch(conn, folder: Path, batch_type: str, refresh: bool = True) -> str:
    bdate = business_date_of(folder, batch_type)
    row = conn.execute("SELECT batch_id, status FROM ctl.batch WHERE business_date=%s AND batch_type=%s",
                       (bdate, batch_type)).fetchone()
    if row and row[1] == "SUCCESS":
        log.info("skip %s %s (already loaded)", batch_type, bdate)
        return "SKIPPED"
    if row:
        batch_id = row[0]
        conn.execute("DELETE FROM ctl.file_log WHERE batch_id=%s", (batch_id,))
        conn.execute("DELETE FROM ctl.step_log WHERE batch_id=%s", (batch_id,))
        conn.execute("UPDATE ctl.batch SET status='RUNNING', started_at=now(), message=NULL WHERE batch_id=%s", (batch_id,))
    else:
        batch_id = conn.execute("INSERT INTO ctl.batch(business_date, batch_type, folder) VALUES (%s,%s,%s) RETURNING batch_id",
                                (bdate, batch_type, str(folder))).fetchone()[0]
    conn.commit()
    t0 = time.time()
    try:
        for entity in LAYOUTS:
            conn.execute(f"TRUNCATE stg.{entity.lower()} RESTART IDENTITY")
        files = pick_files(folder)
        missing = [e for e in LAYOUTS if e not in files and batch_type == "EOD"]
        if missing:
            raise RuntimeError(f"missing files: {missing}")
        total = 0
        for entity, versions in files.items():
            loaded = False
            for rev, path in versions:
                trailer, actual = read_trailer(path)
                if trailer != actual:
                    msg = f"trailer={trailer} actual={actual}"
                    log.warning("REJECT %s (%s)", path.name, msg)
                    conn.execute("INSERT INTO ctl.file_log VALUES (%s,%s,%s,%s,%s,%s,'REJECTED',%s)",
                                 (batch_id, entity, path.name, rev, trailer, actual, msg))
                    continue
                n = copy_file(conn, f"stg.{entity.lower()}", LAYOUTS[entity], path)
                conn.execute("INSERT INTO ctl.file_log VALUES (%s,%s,%s,%s,%s,%s,'LOADED',NULL)",
                             (batch_id, entity, path.name, rev, trailer, n))
                total += n
                loaded = True
                break
            if not loaded:
                raise RuntimeError(f"no valid file for {entity}")
        conn.execute("CALL ctl.sp_process_batch(%s, false)", (batch_id,))
        conn.commit()
        if refresh:
            # refresh planner statistics after each load, otherwise the mart queries pick poor plans
            for t in ANALYZE_TABLES:
                conn.execute(f"ANALYZE {t}")
            # the previous month is refreshed too while its weekend transactions can still arrive (first days of a month)
            months_back = 2 if (batch_type == "HISTORY" or bdate.day <= 5) else 1
            start = (pd.Timestamp(bdate) - pd.offsets.MonthBegin(months_back)).date()
            conn.execute("CALL mart.sp_refresh(%s, %s)", (start, bdate))
            conn.commit()
        log.info("OK   %s %s  %8d rows  %5.1fs", batch_type, bdate, total, time.time() - t0)
        return "SUCCESS"
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        conn.execute("UPDATE ctl.batch SET status='FAILED', finished_at=now(), message=%s WHERE batch_id=%s",
                     (str(exc)[:1000], batch_id))
        conn.commit()
        log.error("FAIL %s %s: %s", batch_type, bdate, exc)
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["history", "eod", "all"], default="all")
    ap.add_argument("--date", help="load a single EOD date (YYYY-MM-DD)")
    ap.add_argument("--raw", help="raw data folder (default data/raw)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config()
    raw = Path(a.raw) if a.raw else cfg.paths.raw
    batches: list[tuple[Path, str]] = []
    if a.mode in ("history", "all") and not a.date:
        batches += [(p, "HISTORY") for p in sorted((raw / "history").iterdir()) if p.is_dir()]
    if a.mode in ("eod", "all"):
        eods = sorted((raw / "eod").iterdir()) if (raw / "eod").exists() else []
        if a.date:
            eods = [p for p in eods if p.name == a.date.replace("-", "")]
        batches += [(p, "EOD") for p in eods if p.is_dir()]
    if not batches:
        raise SystemExit(f"no batch folders found under {raw}")
    t0 = time.time()
    with connect(cfg.pg_dsn) as conn:
        for folder, btype in batches:
            run_batch(conn, folder, btype)
    log.info("pipeline finished in %.0fs (%d batches)", time.time() - t0, len(batches))


if __name__ == "__main__":
    main()
