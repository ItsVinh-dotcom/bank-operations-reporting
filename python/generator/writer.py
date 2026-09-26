"""Write simulated frames as core-banking extract files (history monthly + EOD daily).

Folder structure produced:
    data/raw/history/YYYYMM/DLB_<ENTITY>_<YYYYMMDD>.csv   (initial migration: one batch per month)
    data/raw/eod/YYYYMMDD/DLB_<ENTITY>_<YYYYMMDD>.csv      (daily EOD batches)

Data-quality defects are injected on purpose (documented in docs/04_data_quality.md) so that the
data-quality framework has something real to catch.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from python.common.config import Config
from python.common.layouts import LAYOUTS, file_name
from python.generator import calendar_vn as cal
from python.generator.simulate import Frames

log = logging.getLogger(__name__)

ENTITY_OF = {
    "branch": "BRANCH", "customer": "CUSTOMER", "casa_account": "CASA_ACCOUNT", "casa_balance": "CASA_BALANCE",
    "txn": "TXN", "term_deposit": "TERM_DEPOSIT", "td_balance": "TD_BALANCE", "loan": "LOAN",
    "loan_balance": "LOAN_BALANCE", "card": "CARD", "card_txn": "CARD_TXN", "atm_daily": "ATM_DAILY",
    "branch_ops": "BRANCH_OPS", "complaint": "COMPLAINT", "gl_balance": "GL_BALANCE",
}
BAD_TRAILER = ("TXN", date(2026, 8, 19))   # core sends a truncated file, then a corrected _R1 file


def _fmt(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        s = out[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[c] = s.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
        elif s.dtype == object:
            sample = s.dropna()
            if len(sample) and isinstance(sample.iloc[0], date) and not isinstance(sample.iloc[0], pd.Timestamp):
                out[c] = s.map(lambda x: x.strftime("%Y%m%d") if isinstance(x, date) else "")
            elif len(sample) and isinstance(sample.iloc[0], pd.Timestamp):
                out[c] = s.map(lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else "")
            else:
                out[c] = s.fillna("").astype(str)
        elif pd.api.types.is_float_dtype(s):
            out[c] = s.map(lambda x: "" if pd.isna(x) else (f"{x:.2f}".rstrip("0").rstrip(".") if x % 1 else f"{int(x)}"))
    return out


def inject_defects(fr: Frames, seed: int) -> dict:
    rng = np.random.default_rng(seed + 7)
    report = {}
    c = fr.customer
    ind = c.index[(c.customer_type == "IND") & (c.record_action.isin(["INIT", "NEW"]))]
    k = rng.choice(ind, int(len(ind) * 0.004), replace=False)
    c.loc[k, "date_of_birth"] = None
    report["customer_missing_dob"] = len(k)
    k = rng.choice(ind, int(len(ind) * 0.003), replace=False)
    c.loc[k, "id_number"] = ""
    report["customer_missing_id"] = len(k)
    k = rng.choice(ind, int(len(ind) * 0.002), replace=False)
    c.loc[k, "phone"] = c.loc[k, "phone"].str[:-1]
    report["customer_bad_phone"] = len(k)
    dup = c.loc[rng.choice(ind, 12, replace=False)]
    fr.customer = pd.concat([c, dup], ignore_index=True)
    report["customer_duplicate_rows"] = 12

    t = fr.txn
    k = rng.choice(t.index, int(len(t) * 0.0002), replace=False)
    t.loc[k, "branch_code"] = "999"
    report["txn_invalid_branch"] = len(k)
    cand = t.index[(t.is_reversal == 0) & (t.txn_type == "TRF_OUT")]
    k = rng.choice(cand, int(len(t) * 0.0001), replace=False)
    t.loc[k, "amount"] = -t.loc[k, "amount"]
    report["txn_negative_amount"] = len(k)
    k = rng.choice(t.index, int(len(t) * 0.0005), replace=False)
    t.loc[k, "business_date"] = [cal.next_business_day(d + pd.Timedelta(days=1).to_pytimedelta()) for d in t.loc[k, "business_date"]]
    t.loc[k, "_bdate"] = t.loc[k, "business_date"]
    report["txn_late_posting"] = len(k)
    dup = t.loc[rng.choice(t.index, int(len(t) * 0.00005), replace=False)]
    fr.txn = pd.concat([t, dup], ignore_index=True)
    report["txn_duplicate_rows"] = len(dup)

    lo = fr.loan
    mort = lo.index[(lo.product_code == "LN_MORTGAGE") & (lo.close_date.isna())]
    k = rng.choice(mort, max(1, int(len(mort) * 0.003)), replace=False)
    lo.loc[k, "collateral_value"] = np.nan
    report["loan_missing_collateral"] = len(k)
    return report


def write_all(fr: Frames, cfg: Config, out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir or cfg.paths.raw)
    eod_start = cfg.sim.eod_start_date
    end = cfg.sim.end_date
    report = inject_defects(fr, cfg.sim.random_seed)
    stats: dict[str, int] = {}
    for attr, entity in ENTITY_OF.items():
        df: pd.DataFrame = getattr(fr, attr)
        df = df[df["_bdate"] <= end]
        cols = LAYOUTS[entity]
        bd = pd.to_datetime(df["_bdate"])
        is_eod = bd >= pd.Timestamp(eod_start)
        # history: bucket by month
        hist = df[~is_eod]
        for per, g in hist.groupby(bd[~is_eod].dt.to_period("M")):
            fdate = per.end_time.strftime("%Y%m%d")
            _write(out_dir / "history" / per.strftime("%Y%m"), cfg.bank_code, entity, fdate, g[cols])
        for d, g in df[is_eod].groupby(bd[is_eod].dt.date):
            _write(out_dir / "eod" / d.strftime("%Y%m%d"), cfg.bank_code, entity, d.strftime("%Y%m%d"), g[cols],
                   bad_trailer=(entity, d) == BAD_TRAILER)
        stats[entity] = len(df)
        log.info("%-13s %9d rows", entity, len(df))
    # every EOD folder gets all entities (empty files with trailer 0) so that the batch is complete
    for d in cal.business_days(eod_start, end):
        folder = out_dir / "eod" / d.strftime("%Y%m%d")
        for entity in LAYOUTS:
            f = folder / file_name(cfg.bank_code, entity, d.strftime("%Y%m%d"))
            if not f.exists():
                _write(folder, cfg.bank_code, entity, d.strftime("%Y%m%d"), pd.DataFrame(columns=LAYOUTS[entity]))
    meta = {"generated_rows": stats, "injected_defects": report, "config": {k: str(v) for k, v in asdict(cfg.sim).items()}}
    (out_dir / "_generation_report.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def _write(folder: Path, bank: str, entity: str, fdate: str, df: pd.DataFrame, bad_trailer: bool = False):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / file_name(bank, entity, fdate)
    body = _fmt(df)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        body.to_csv(fh, sep="|", index=False, lineterminator="\n")
        n = len(body) + (37 if bad_trailer else 0)
        fh.write(f"TRL|{n}|{fdate}\n")
    if bad_trailer:   # corrected resend
        with open(folder / file_name(bank, entity, fdate, revision=1), "w", encoding="utf-8", newline="") as fh:
            body.to_csv(fh, sep="|", index=False, lineterminator="\n")
            fh.write(f"TRL|{len(body)}|{fdate}\n")
