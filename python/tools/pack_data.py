"""Pack the core-banking extracts (data/raw, ~450 MB CSV) into compressed Parquet (data/parquet, ~45 MB).

Why: the CSV extracts are the realistic "core banking" format, but too big for GitHub. Parquet is a
columnar, compressed format (zstd) that shrinks them ~10x. One Parquet file per entity keeps the number
of files small; `unpack_data` rebuilds the exact same CSV files (byte-for-byte), including trailers.

    python -m python.tools.pack_data            # data/raw  -> data/parquet
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from python.common.config import ROOT, load_config
from python.common.layouts import LAYOUTS

FILE_RE = re.compile(r"^[A-Z]+_(?P<entity>[A-Z_]+?)_\d{8}(?:_R\d+)?\.csv$")
DEFAULT_OUT = ROOT / "data" / "parquet"
MAX_ROWS = 1_000_000


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=None)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    raw = Path(a.raw) if a.raw else load_config().paths.raw
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for old_file in out.glob("*.parquet"):
        old_file.unlink()
    files = sorted(p for p in raw.rglob("*.csv"))
    manifest: dict[str, dict] = {}
    parts: dict[str, list[pd.DataFrame]] = {e: [] for e in LAYOUTS}
    for p in files:
        m = FILE_RE.match(p.name)
        if not m:
            continue
        rel = p.relative_to(raw).as_posix()
        # the trailer line is read separately so that malformed trailers are preserved exactly
        lines = p.read_text(encoding="utf-8").splitlines()
        trailer = lines[-1]
        body_rows = len(lines) - 2
        manifest[rel] = {"entity": m["entity"], "rows": body_rows, "trailer": trailer}
        if body_rows > 0:
            df = pd.read_csv(p, sep="|", dtype=str, keep_default_na=False, na_filter=False).iloc[:-1]
            df.insert(0, "_file", rel)
            parts[m["entity"]].append(df)
    total_in = sum(p.stat().st_size for p in files)
    total_out = 0
    for entity, dfs in parts.items():
        if not dfs:
            continue
        # large entities are split into parts of ~MAX_ROWS rows (whole files only) to keep each file small
        chunks, cur, cur_rows = [], [], 0
        for d in dfs:
            if cur and cur_rows + len(d) > MAX_ROWS:
                chunks.append(cur)
                cur, cur_rows = [], 0
            cur.append(d)
            cur_rows += len(d)
        chunks.append(cur)
        for i, chunk in enumerate(chunks, 1):
            df = pd.concat(chunk, ignore_index=True)
            df["_file"] = df["_file"].astype("category")
            name = f"{entity}.parquet" if len(chunks) == 1 else f"{entity}.part{i}.parquet"
            target = out / name
            df.to_parquet(target, compression="zstd", compression_level=9, index=False, row_group_size=200_000)
            total_out += target.stat().st_size
            print(f"{name:<22} {len(df):>9,} rows -> {target.stat().st_size / 1e6:6.1f} MB")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=0, ensure_ascii=False), encoding="utf-8")
    rep = raw / "_generation_report.json"
    if rep.exists():
        (out / "_generation_report.json").write_text(rep.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{len(manifest)} files: {total_in / 1e6:.0f} MB CSV -> {total_out / 1e6:.0f} MB Parquet")


if __name__ == "__main__":
    main()
