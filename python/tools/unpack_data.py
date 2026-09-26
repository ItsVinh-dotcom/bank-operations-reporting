"""Rebuild the core-banking CSV extracts (data/raw) from the compressed Parquet copy (data/parquet).

    python -m python.tools.unpack_data          # data/parquet -> data/raw   (~30 seconds)

The output is byte-for-byte identical to what `python -m python.generator.run_generator` produces,
so after unpacking you can run the ETL directly (no need to re-generate).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from python.common.config import ROOT, load_config
from python.common.layouts import LAYOUTS

DEFAULT_SRC = ROOT / "data" / "parquet"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--raw", default=None)
    a = ap.parse_args()
    src = Path(a.src)
    raw = Path(a.raw) if a.raw else load_config().paths.raw
    manifest: dict[str, dict] = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    by_entity: dict[str, pd.DataFrame] = {}
    for entity in LAYOUTS:
        parts = [src / f"{entity}.parquet"] + sorted(src.glob(f"{entity}.part*.parquet"))
        parts = [f for f in parts if f.exists()]
        if parts:
            by_entity[entity] = pd.concat([pd.read_parquet(f) for f in parts], ignore_index=True)
    groups = {e: dict(tuple(df.groupby("_file", observed=True))) for e, df in by_entity.items()}
    n = 0
    for rel, meta in manifest.items():
        entity = meta["entity"]
        cols = LAYOUTS[entity]
        path = raw / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        df = groups.get(entity, {}).get(rel)
        body = df[cols] if df is not None else pd.DataFrame(columns=cols)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            body.to_csv(fh, sep="|", index=False, lineterminator="\n")
            fh.write(meta["trailer"] + "\n")
        n += 1
    rep = src / "_generation_report.json"
    if rep.exists():
        (raw / "_generation_report.json").write_text(rep.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"rebuilt {n} files in {raw}")


if __name__ == "__main__":
    main()
