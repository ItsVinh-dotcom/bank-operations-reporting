"""PostgreSQL helpers (psycopg 3)."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg

from python.common.config import ROOT, load_config

log = logging.getLogger(__name__)
SQL_DIR = ROOT / "sql"
# execution order of the DDL / procedure scripts
SQL_FILES = [
    "00_setup/01_schemas.sql",
    "01_staging/01_stg_tables.sql",
    "02_core/01_dimensions.sql",
    "02_core/02_facts.sql",
    "02_core/03_dq_tables.sql",
    "03_mart/01_mart_tables.sql",
    "04_procedures/01_utils.sql",
    "04_procedures/02_load_dimensions.sql",
    "04_procedures/03_load_facts.sql",
    "04_procedures/05_dq_checks.sql",
    "04_procedures/06_refresh_marts.sql",
    "04_procedures/04_process_batch.sql",
    "05_reports/01_report_views.sql",
]


@contextmanager
def connect(dsn: str | None = None, autocommit: bool = False):
    dsn = dsn or load_config().pg_dsn
    with psycopg.connect(dsn, autocommit=autocommit) as conn:
        yield conn


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    log.info("running %s", path.relative_to(ROOT))
    conn.execute(path.read_text(encoding="utf-8"))


def copy_file(conn: psycopg.Connection, table: str, columns: list[str], path: Path) -> int:
    """COPY a pipe-delimited extract (header + body + trailer) into a staging table, skipping the trailer."""
    cols = ", ".join(columns)
    n = 0
    with conn.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, DELIMITER '|', HEADER true, NULL '\\N')") as cp:
            with open(path, "r", encoding="utf-8") as fh:
                prev = None
                for line in fh:
                    if prev is not None:
                        cp.write(prev)
                        n += 1
                    prev = line
    return n - 1  # minus header
