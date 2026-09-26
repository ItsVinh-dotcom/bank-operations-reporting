"""Vietnamese banking calendar: holidays, business days, Tết windows."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from python.common.config import ROOT

# Lunar New Year day (mùng 1 Tết)
TET_DAYS = {2024: date(2024, 2, 10), 2025: date(2025, 1, 29), 2026: date(2026, 2, 17)}


@lru_cache
def holidays() -> set[date]:
    df = pd.read_csv(ROOT / "data" / "reference" / "holidays.csv", parse_dates=["holiday_date"])
    return set(df["holiday_date"].dt.date)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in holidays()


def next_business_day(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def business_days(start: date, end: date) -> list[date]:
    return [d.date() for d in pd.date_range(start, end) if is_business_day(d.date())]


def pre_tet_factor(d: date) -> float:
    """Demand multiplier around Tết: strong spike in the 12 days before, drop during the holiday."""
    tet = TET_DAYS.get(d.year) or TET_DAYS.get(d.year + 1)
    if tet is None:
        return 1.0
    delta = (tet - d).days
    if 1 <= delta <= 12:
        return 1.0 + 1.6 * (13 - delta) / 12
    if -4 <= delta <= 0:
        return 0.35
    return 1.0


def day_weights(month_start: date, kind: str) -> tuple[np.ndarray, list[date]]:
    """Probability weights for each calendar day of a month for a given activity kind.

    kind: 'digital' (any day), 'counter' (business days only), 'atm' (any day, Tết-sensitive), 'payroll'.
    """
    end = (pd.Timestamp(month_start) + pd.offsets.MonthEnd(0)).date()
    days = [d.date() for d in pd.date_range(month_start, end)]
    w = np.ones(len(days))
    for i, d in enumerate(days):
        bd = is_business_day(d)
        if kind == "counter":
            w[i] = 1.0 if bd else 0.0
        elif kind == "payroll":
            w[i] = 1.0 if (bd and 5 <= d.day <= 10) else 0.0
        else:
            w[i] = 1.0 if bd else 0.75
            if 5 <= d.day <= 10:
                w[i] *= 1.3
            if kind == "atm":
                w[i] *= pre_tet_factor(d)
            else:
                w[i] *= 1 + (pre_tet_factor(d) - 1) * 0.4
    if w.sum() == 0:  # e.g. a month with no payroll window business day (should not happen)
        w[:] = 1
    return w / w.sum(), days
