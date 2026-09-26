"""Run one or more SQL files against the DWH.

    python -m python.etl.run_sql sql/05_reports/02_powerbi_views.sql
"""
from __future__ import annotations

import sys
from pathlib import Path

from python.common.config import ROOT, load_config
from python.etl.db import connect


def main() -> None:
    files = sys.argv[1:]
    if not files:
        raise SystemExit(__doc__)
    with connect(load_config().pg_dsn) as conn:
        for f in files:
            p = Path(f) if Path(f).is_absolute() else ROOT / f
            conn.execute(p.read_text(encoding="utf-8"))
            print(f"OK  {p.relative_to(ROOT)}")
        conn.commit()


if __name__ == "__main__":
    main()
