"""Core-banking simulator for the fictional retail bank DLB.

Produces pandas DataFrames matching python.common.layouts.LAYOUTS. Each frame carries a helper column
`_bdate` (the business date whose EOD extract the record belongs to); the writer uses it to route
records into monthly history files or daily EOD files.

Design principles (see docs/02_calibration.md):
* Balances are *derived from flows* so every roll-forward reconciles
  (opening balance + credits - debits = closing balance).
* Portfolio totals follow calibrated growth paths (controllers) with seasonality and noise.
* Behaviour is heterogeneous and skewed (log-normal amounts, Pareto-like concentration).
* A handful of storyline events are embedded (see EVENTS).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from python.common.config import Config
from python.generator import calendar_vn as cal
from python.generator.names_vn import person_names, sme_names

log = logging.getLogger(__name__)

MONTH_END = pd.offsets.MonthEnd(0)
VN_BANKS = ["VCB", "BIDV", "CTG", "AGRIBANK", "TCB", "MB", "ACB", "VPB", "STB", "HDB", "TPB", "VIB",
            "SHB", "MSB", "OCB", "SEAB", "LPB", "EIB"]
PHONE_PREFIX = ["090", "091", "093", "094", "096", "097", "098", "086", "088", "089", "032", "033", "034",
                "035", "036", "037", "038", "039", "070", "076", "077", "078", "079", "081", "083", "084", "085"]

EVENTS = {
    # NPL storyline: consumer & household loans in the Cần Thơ cluster deteriorate in 2025
    "npl_branches": {"400", "401", "402", "403"},
    "npl_products": {"LN_CONSUMER", "LN_HOUSEHOLD"},
    "npl_window": (pd.Period("2025-03", "M"), pd.Period("2025-10", "M")),
    # Credit-card acquisition campaign: issuance x3, low activation
    "card_campaign": (pd.Period("2025-04", "M"), pd.Period("2025-06", "M")),
    # ATM incident cluster (CN Sài Gòn and its PGDs)
    "atm_branches": {"110", "111", "112"},
    "atm_window": (date(2025, 9, 8), date(2025, 10, 17)),
    # Mobile app release issue -> complaint spike
    "app_window": (date(2026, 3, 9), date(2026, 3, 18)),
}


@dataclass
class Frames:
    branch: pd.DataFrame
    customer: pd.DataFrame
    casa_account: pd.DataFrame
    casa_balance: pd.DataFrame
    txn: pd.DataFrame
    term_deposit: pd.DataFrame
    td_balance: pd.DataFrame
    loan: pd.DataFrame
    loan_balance: pd.DataFrame
    card: pd.DataFrame
    card_txn: pd.DataFrame
    atm_daily: pd.DataFrame
    branch_ops: pd.DataFrame
    complaint: pd.DataFrame
    gl_balance: pd.DataFrame


def _d(x) -> date:
    return pd.Timestamp(x).date()


def route_date(d: date) -> date:
    """EOD business date on which a master-data change is extracted.

    Normally the next business day; but a change made on the last (weekend/holiday) days of a month is still
    captured by that month's closing extract, so that month-end snapshots and master data stay consistent.
    """
    nb = cal.next_business_day(d)
    if (nb.year, nb.month) != (d.year, d.month):
        return (pd.Timestamp(d) + MONTH_END).date()
    return nb


class Simulator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.sim.random_seed)
        ref = cfg.paths.reference
        self.branches = pd.read_csv(ref / "branches.csv", dtype=str)
        self.branches["size_weight"] = self.branches["size_weight"].astype(float)
        self.branches["n_atm"] = self.branches["n_atm"].astype(int)
        self.branches["open_date"] = pd.to_datetime(self.branches["open_date"]).dt.date
        self.prov_map = pd.read_csv(ref / "provinces_old_to_new.csv", dtype=str)
        self.old2new = dict(zip(self.prov_map.old_province_code, self.prov_map.new_province_code))
        self.dep_rates = pd.read_csv(ref / "rates_deposit.csv")
        self.lend_rates = pd.read_csv(ref / "rates_lending.csv")
        self.mcc = pd.read_csv(ref / "mcc.csv", dtype={"mcc": str})
        self.months = pd.period_range(pd.Period(cfg.sim.start_date, "M"), pd.Period(cfg.sim.end_date, "M"), freq="M")
        self.init_date = cfg.sim.start_date - timedelta(days=1)            # 2023-12-31 migration snapshot
        self.province_switch = date(2025, 7, 1)
        self.branch_idx = {c: i for i, c in enumerate(self.branches.branch_code)}

    # ------------------------------------------------------------------ helpers
    def lognormal(self, median, sigma, n):
        return self.rng.lognormal(np.log(median), sigma, n)

    def dep_rate(self, month: pd.Period, term: np.ndarray | int) -> np.ndarray:
        tbl = self.dep_rates.copy()
        tbl["p"] = pd.PeriodIndex(tbl.effective_month, freq="M")
        row = tbl[tbl.p <= month].iloc[-1] if (tbl.p <= month).any() else tbl.iloc[0]
        term = np.atleast_1d(term)
        cols = {1: "rate_1m", 3: "rate_3m", 6: "rate_6m", 12: "rate_12m", 24: "rate_24m", 36: "rate_36m"}
        return np.array([row[cols[min(cols, key=lambda k: abs(k - t))]] for t in term], dtype=float)

    def lend_rate(self, month: pd.Period, product: str) -> float:
        tbl = self.lend_rates.copy()
        tbl["p"] = pd.PeriodIndex(tbl.effective_month, freq="M")
        row = tbl[tbl.p <= month].iloc[-1] if (tbl.p <= month).any() else tbl.iloc[0]
        return float(row[product])

    def random_dates(self, start: date, end: date, n: int, kind: str = "digital") -> np.ndarray:
        """Random dates between start and end (inclusive) following day-type weights."""
        days = pd.date_range(start, end)
        if len(days) == 0:
            return np.array([start] * n)
        w = np.array([1.0 if (kind != "counter" or cal.is_business_day(d.date())) else 0.0 for d in days])
        if w.sum() == 0:
            w[:] = 1
        idx = self.rng.choice(len(days), size=n, p=w / w.sum())
        return np.array([d.date() for d in days[idx]])

    # ================================================================== BRANCHES
    def build_branches(self) -> pd.DataFrame:
        b = self.branches
        init = pd.DataFrame({
            "branch_code": b.branch_code, "branch_name": b.branch_name, "branch_level": b.branch_level,
            "parent_branch_code": b.parent_branch_code.fillna(""), "province_code": b.old_province_code,
            "district": b.district, "open_date": b.open_date, "status": "ACTIVE",
            "effective_date": b.open_date, "_bdate": self.init_date,
        })
        # branches whose province code OR province name changes with the 01/07/2025 merger
        new_names = pd.read_csv(self.cfg.paths.reference / "provinces.csv", dtype=str).set_index("province_code").province_name
        old_names = self.prov_map.set_index("old_province_code").old_province_name
        new_code = b.old_province_code.map(self.old2new)
        changed = b[(new_code != b.old_province_code) |
                    (b.old_province_code.map(old_names).values != new_code.map(new_names).values)]
        upd = init.loc[changed.index].copy()
        upd["province_code"] = changed.old_province_code.map(self.old2new)
        upd["effective_date"] = self.province_switch
        upd["_bdate"] = self.province_switch
        # all branches: district naming also changed after 2-tier local government reform -> keep simple
        return pd.concat([init, upd], ignore_index=True)

    # ================================================================== CUSTOMERS
    def build_customers(self) -> pd.DataFrame:
        rng, cfg = self.rng, self.cfg
        b = self.branches
        w = b.size_weight.values / b.size_weight.sum()

        def assign_branch(n):
            return rng.choice(len(b), size=n, p=w)

        # ---------------- individuals
        n = cfg.sim.n_individuals
        n_pre = int(n * 0.68)
        n_new = n - n_pre
        # monthly acquisition weights: trend + seasonality + campaign
        mw = []
        for i, p in enumerate(self.months):
            s = 1 + 0.012 * i
            s *= {1: 0.85, 2: 0.6, 12: 1.1}.get(p.month, 1.0)
            if EVENTS["card_campaign"][0] <= p <= EVENTS["card_campaign"][1]:
                s *= 1.35
            mw.append(s * rng.lognormal(0, 0.08))
        mw = np.array(mw) / sum(mw)
        new_counts = rng.multinomial(n_new, mw)

        bi = assign_branch(n)
        open_dates = np.empty(n, dtype=object)
        # pre-existing: open between max(branch open, 2012-01-01) and 2023-12-31, skewed to recent years
        for k in range(n_pre):
            lo = max(b.open_date.iat[bi[k]], date(2012, 1, 1))
            span = (self.init_date - lo).days
            open_dates[k] = lo + timedelta(days=int(span * rng.beta(2.2, 1.0)))
        k = n_pre
        for mi, c in enumerate(new_counts):
            p = self.months[mi]
            ds = self.random_dates(p.start_time.date(), p.end_time.date(), c, kind="digital")
            open_dates[k:k + c] = ds
            k += c

        gender = rng.choice(["M", "F"], n, p=[0.49, 0.51])
        age = np.clip(np.where(rng.random(n) < 0.12, rng.normal(62, 6, n), rng.normal(33, 9, n)), 18, 82)
        new_mask = np.arange(n) >= n_pre
        age[new_mask] = np.clip(age[new_mask] - rng.uniform(0, 6, new_mask.sum()), 18, 82)
        dob = np.array([date(2024, 1, 1) - timedelta(days=int(a * 365.25 + rng.integers(0, 365))) for a in age])
        branch_prov = b.old_province_code.values[bi]
        all_old = self.prov_map.old_province_code.values
        birth_prov = np.where(rng.random(n) < 0.7, branch_prov, rng.choice(all_old, n))
        prov = np.where(rng.random(n) < 0.88, branch_prov, rng.choice(all_old, n))
        hn_hcm = np.isin(prov, ["01", "79"])
        income = self.lognormal(11e6, 0.65, n) * np.where(hn_hcm, 1.25, 1.0)
        segment = np.where(income > 60e6, "PRIORITY", np.where(income > 25e6, "AFFLUENT", "MASS"))
        segment = np.where((segment == "MASS") & (rng.random(n) < 0.015), "AFFLUENT", segment)
        occ = rng.choice(["Nhân viên văn phòng", "Kinh doanh tự do", "Công nhân", "Công chức/viên chức",
                          "Chủ doanh nghiệp/hộ kinh doanh", "Khác"], n, p=[.38, .2, .15, .12, .08, .07])
        age_now = age
        occ = np.where(age_now < 22.5, "Sinh viên", np.where(age_now > 60, "Hưu trí", occ))
        income = np.where(occ == "Sinh viên", income * 0.3, np.where(occ == "Hưu trí", income * 0.6, income))
        payroll = np.isin(occ, ["Nhân viên văn phòng", "Công nhân", "Công chức/viên chức"]) & (rng.random(n) < 0.62)

        # churn (closed relationship); customers with a close date never receive loans/TD
        close = np.full(n, None, dtype=object)
        for k in range(n):
            start_m = pd.Period(max(open_dates[k], cfg.sim.start_date), "M")
            haz = 0.0045 if k < n_pre else 0.003
            for p in self.months[self.months >= start_m]:
                if rng.random() < haz:
                    c_date = self.random_dates(p.start_time.date(), p.end_time.date(), 1, "counter")[0]
                    if (c_date - open_dates[k]).days > 60:
                        close[k] = c_date
                    break

        # CCCD: province of birth (3 digits) + century/gender digit + yy + 6 random digits
        cent = np.where(np.array([d.year for d in dob]) >= 2000, 2, 0) + (gender == "F").astype(int)
        yy = np.array([f"{d.year % 100:02d}" for d in dob])
        idn = np.array([f"0{bp}{c}{y}{rng.integers(0, 10**6):06d}" for bp, c, y in zip(birth_prov, cent, yy)])
        phone = np.array([f"{rng.choice(PHONE_PREFIX)}{rng.integers(0, 10**7):07d}" for _ in range(n)])

        ind = pd.DataFrame({
            "customer_type": "IND", "full_name": person_names(rng, gender), "gender": gender,
            "date_of_birth": dob, "id_number": idn, "tax_code": "", "phone": phone, "province_code": prov,
            "home_branch_code": b.branch_code.values[bi], "segment": segment, "occupation": occ,
            "industry": "", "open_date": open_dates, "close_date": close,
            "_income": income, "_payroll": payroll,
        })

        # ---------------- SMEs
        ns = cfg.sim.n_sme
        ns_pre = int(ns * 0.75)
        bi_s = assign_branch(ns)
        s_open = np.empty(ns, dtype=object)
        for k in range(ns):
            if k < ns_pre:
                lo = max(b.open_date.iat[bi_s[k]], date(2013, 1, 1))
                s_open[k] = lo + timedelta(days=int((self.init_date - lo).days * rng.beta(2, 1.2)))
            else:
                s_open[k] = self.random_dates(self.cfg.sim.start_date, date(2026, 7, 31), 1, "counter")[0]
        industry = rng.choice(["Thương mại bán buôn, bán lẻ", "Công nghiệp chế biến, chế tạo", "Xây dựng",
                               "Vận tải kho bãi", "Dịch vụ lưu trú và ăn uống", "Nông, lâm nghiệp và thủy sản",
                               "Thông tin và truyền thông", "Hoạt động chuyên môn, khoa học công nghệ"],
                              ns, p=[.34, .2, .13, .09, .08, .07, .05, .04])
        sme = pd.DataFrame({
            "customer_type": "SME", "full_name": sme_names(rng, ns), "gender": "", "date_of_birth": None,
            "id_number": "", "tax_code": [f"0{rng.integers(10**8, 10**9)}" for _ in range(ns)],
            "phone": [f"028{rng.integers(10**7, 10**8)}" if b.old_province_code.iat[i] in ("79", "74", "77")
                      else f"024{rng.integers(10**7, 10**8)}" for i in bi_s],
            "province_code": b.old_province_code.values[bi_s], "home_branch_code": b.branch_code.values[bi_s],
            "segment": "SME", "occupation": "", "industry": industry, "open_date": s_open, "close_date": None,
            "_income": self.lognormal(900e6, 0.8, ns), "_payroll": False,
        })
        cust = pd.concat([ind, sme], ignore_index=True)
        cust = cust.sort_values("open_date", kind="stable").reset_index(drop=True)
        cust.insert(0, "cif", [f"{10_000_000 + i * 3 + int(rng.integers(0, 3))}" for i in range(len(cust))])
        self.cust = cust
        return self._customer_file(cust)

    def _customer_file(self, cust: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        base_cols = ["cif", "customer_type", "full_name", "gender", "date_of_birth", "id_number", "tax_code",
                     "phone", "province_code", "home_branch_code", "segment", "occupation", "industry",
                     "open_date", "close_date"]
        rows = []
        pre = cust[cust.open_date <= self.init_date].copy()
        pre["status"], pre["record_action"], pre["effective_date"], pre["_bdate"] = "ACTIVE", "INIT", pre.open_date, self.init_date
        pre["close_date"] = None
        rows.append(pre)
        new = cust[cust.open_date > self.init_date].copy()
        new["status"], new["record_action"], new["effective_date"] = "ACTIVE", "NEW", new.open_date
        new["close_date"] = None
        new["_bdate"] = [route_date(d) for d in new.open_date]
        rows.append(new)

        # segment upgrades (SCD2 driver)
        ind = cust[(cust.customer_type == "IND") & (cust.segment != "PRIORITY") & cust.close_date.isna()]
        up = ind.sample(frac=0.05, random_state=int(rng.integers(1e9))).copy()
        up_dates = []
        for od in up.open_date:
            lo = max(od + timedelta(days=90), date(2024, 3, 1))
            up_dates.append(self.random_dates(lo, date(2026, 8, 20), 1, "counter")[0] if lo < date(2026, 8, 20) else None)
        up["effective_date"] = up_dates
        up = up[up.effective_date.notna()]
        up["segment"] = np.where(up.segment == "MASS", "AFFLUENT", "PRIORITY")
        up["status"], up["record_action"], up["close_date"] = "ACTIVE", "UPD", None
        up["_bdate"] = [route_date(d) for d in up.effective_date]
        # keep the upgrade in the master data so that later province conversion carries it
        self.cust.loc[up.index, "_upgrade_date"] = up.effective_date
        self.cust.loc[up.index, "_segment_after"] = up.segment
        rows.append(up)

        # province conversion on 2025-07-01 for active customers whose province code changes
        active = cust[(cust.open_date < self.province_switch) &
                      (cust.close_date.isna() | (cust.close_date >= self.province_switch))].copy()
        newcode = active.province_code.map(self.old2new)
        conv = active[newcode != active.province_code].copy()
        conv["province_code"] = newcode[newcode != active.province_code]
        seg_after = self.cust.loc[conv.index, "_segment_after"] if "_segment_after" in self.cust else None
        if seg_after is not None:
            upd_before = self.cust.loc[conv.index, "_upgrade_date"]
            mask = upd_before.notna() & (upd_before < self.province_switch)
            conv.loc[mask[mask].index, "segment"] = seg_after[mask]
        conv["status"], conv["record_action"], conv["effective_date"], conv["close_date"] = "ACTIVE", "UPD", self.province_switch, None
        conv["_bdate"] = self.province_switch
        rows.append(conv)

        # closures
        cl = cust[cust.close_date.notna()].copy()
        cl["status"], cl["record_action"], cl["effective_date"] = "CLOSED", "CLS", cl.close_date
        cl["province_code"] = np.where(cl.close_date >= self.province_switch,
                                       cl.province_code.map(self.old2new), cl.province_code)
        cl["_bdate"] = [route_date(d) for d in cl.close_date]
        rows.append(cl)
        out = pd.concat(rows, ignore_index=True)
        return out[base_cols + ["status", "record_action", "effective_date", "_bdate"]]

    # ================================================================== CASA
    def build_casa(self):
        rng, cust = self.rng, self.cust
        ind = cust.customer_type.values == "IND"
        n = len(cust)
        acc = pd.DataFrame({
            "cif": cust.cif, "cust_idx": np.arange(n), "branch_code": cust.home_branch_code,
            "open_date": cust.open_date, "close_date": cust.close_date,
            "product_code": np.where(ind, np.where(cust._payroll, "CASA_PAY", "CASA_IND"), "CASA_SME"),
            "is_main": True,
        })
        second = np.where(ind, rng.random(n) < 0.12, rng.random(n) < 0.3)
        sec = acc[second].copy()
        sec["is_main"] = False
        sec["product_code"] = np.where(sec.product_code == "CASA_SME", "CASA_SME", "CASA_IND")
        sec["open_date"] = [od + timedelta(days=int(rng.integers(30, 900))) for od in sec.open_date]
        sec = sec[sec.open_date <= self.cfg.sim.end_date]
        sec = sec[sec.close_date.isna() | (sec.open_date < sec.close_date)]
        # some secondary accounts close on their own
        own_close = (rng.random(len(sec)) < 0.15) & sec.close_date.isna().values
        cands = [o + timedelta(days=int(rng.integers(90, 700))) for o in sec.open_date[own_close]]
        sec.loc[own_close, "close_date"] = [c if c < date(2026, 8, 28) else None for c in cands]
        acc = pd.concat([acc, sec], ignore_index=True).sort_values("open_date", kind="stable").reset_index(drop=True)
        # accounts already closed before the migration date are not migrated
        closed_before = acc.close_date.map(lambda d: isinstance(d, date) and d <= self.init_date)
        acc = acc[~closed_before].reset_index(drop=True)
        # accounts opened before 2024 at branches that open later are impossible: fine by construction
        seq = np.arange(len(acc))
        acc["account_no"] = [f"{bc}{100000000 + s * 7 + int(rng.integers(0, 7)):09d}" for bc, s in zip(acc.branch_code, seq)]
        a_n = len(acc)
        is_sme = acc.product_code.values == "CASA_SME"
        seg = cust.segment.values[acc.cust_idx]
        inc = cust._income.values[acc.cust_idx] * np.where(acc.is_main, 1.0, 0.3)
        payroll = (acc.product_code.values == "CASA_PAY") & acc.is_main.values
        dormant = (~is_sme) & (rng.random(a_n) < 0.12)
        kmed = np.select([is_sme, seg == "PRIORITY", seg == "AFFLUENT"], [0.9, 2.6, 1.7], 1.05)
        k = kmed * rng.lognormal(0, 0.45, a_n)
        base_in = np.where(payroll, inc, inc * rng.uniform(0.35, 1.0, a_n))
        base_in = np.where(dormant, inc * 0.02, base_in)
        acc["_is_sme"], acc["_payroll"], acc["_dormant"] = is_sme, payroll, dormant
        acc["_k"], acc["_base_in"] = k, base_in
        # window dressing SMEs: 30% of SME main accounts
        acc["_wd"] = is_sme & acc.is_main.values & (rng.random(a_n) < 0.3)
        # old customers are heavier counter users
        age = np.array([(date(2024, 1, 1) - d).days / 365.25 if isinstance(d, date) else 40
                        for d in cust.date_of_birth.values[acc.cust_idx]])
        acc["_counter_pref"] = np.clip((age - 35) / 60, 0, 0.5)
        self.acc = acc

        balances, txns = self._simulate_casa_flows(acc)
        acc_file = acc[["account_no", "cif", "product_code", "branch_code", "open_date", "close_date"]].copy()
        acc_file["status"] = np.where(acc.close_date.notna(), "CLOSED", "ACTIVE")
        # account master delta: NEW rows on open, CLS rows on close
        opened = acc_file.copy()
        opened["status"], opened["close_date"] = "ACTIVE", None
        opened["_bdate"] = [self.init_date if d <= self.init_date else route_date(d) for d in opened.open_date]
        closed = acc_file[acc_file.close_date.notna()].copy()
        closed["_bdate"] = [route_date(d) for d in closed.close_date]
        return pd.concat([opened, closed], ignore_index=True), balances, txns

    def _simulate_casa_flows(self, acc: pd.DataFrame):
        rng = self.rng
        a_n = len(acc)
        open_d = pd.to_datetime(acc.open_date).values
        close_d = pd.to_datetime(acc.close_date).values
        # opening balance at migration date
        B = np.zeros(a_n)
        pre = open_d <= np.datetime64(self.init_date)
        B[pre] = np.round(acc._k.values[pre] * acc._base_in.values[pre] * rng.lognormal(0, 0.3, pre.sum()), -3)
        wd_pending = np.zeros(a_n)
        bal_rows = [pd.DataFrame({"snapshot_date": self.init_date, "account_no": acc.account_no.values[pre],
                                  "balance": B[pre].astype(np.int64), "accrued_interest": 0,
                                  "status": np.where(acc._dormant.values[pre], "DORMANT", "ACTIVE"),
                                  "_bdate": self.init_date})]
        txn_parts = []
        seq_by_day: dict[date, int] = {}
        for mi, p in enumerate(self.months):
            ms, me = p.start_time.date(), p.end_time.date()
            ms64, me64 = np.datetime64(ms), np.datetime64(me)
            active = (open_d <= me64) & (np.isnat(close_d) | (close_d >= ms64))
            idx = np.where(active)[0]
            opening = (open_d[idx] >= ms64)
            closing = (~np.isnat(close_d[idx])) & (close_d[idx] <= me64)
            growth = 1.005 ** mi
            base = acc._base_in.values[idx] * growth
            season = np.ones(len(idx))
            is_sme = acc._is_sme.values[idx]
            season[is_sme] *= {2: 0.8, 10: 1.08, 11: 1.12, 12: 1.2}.get(p.month, 1.0)
            I = base * season * rng.lognormal(0, 0.22, len(idx))
            # 13th-month salary paid in the month before/containing Tết
            tet = cal.TET_DAYS.get(p.year)
            bonus_month = pd.Period(tet - timedelta(days=12), "M") if tet else None
            payroll = acc._payroll.values[idx]
            payroll_amt = np.where(payroll, base * rng.uniform(0.95, 1.05, len(idx)), 0.0)
            if bonus_month is not None and p == bonus_month:
                payroll_amt = payroll_amt * np.where(rng.random(len(idx)) < 0.8, 2.0, 1.0)
            I = np.where(payroll, np.maximum(I, payroll_amt * 1.05), I)
            I[opening] += acc._base_in.values[idx][opening] * rng.uniform(0.2, 1.0, opening.sum())
            I = np.round(I, -3)
            payroll_amt = np.round(np.minimum(payroll_amt, I), -3)
            # window dressing at quarter end (in) and reversal next month (out)
            wd_in = np.zeros(len(idx))
            if p.month in (3, 6, 9, 12):
                wmask = acc._wd.values[idx] & ~closing
                wd_in[wmask] = np.round(base[wmask] * rng.uniform(0.1, 0.35, wmask.sum()), -6)
            wd_out = wd_pending[idx].copy()
            wd_pending[idx] = wd_in
            Bp = B[idx]
            target = acc._k.values[idx] * base
            O = I + 0.35 * (Bp - target) + rng.normal(0, 0.05, len(idx)) * I
            minbal = np.where(is_sme, 1e6, 5e4)
            O = np.clip(O, 0.2 * I, np.maximum(Bp + I - minbal, 0))
            interest = np.floor(Bp * 0.002 / 12)
            fee = np.where(is_sme, 55_000, np.where(rng.random(len(idx)) < 0.8, 11_000, 0))
            fee = np.where(opening, 0, fee)
            O = np.round(O, -3)
            # closing accounts: sweep everything out
            O = np.where(closing, Bp + I + interest - fee + wd_in - wd_out, O)
            B_new = Bp + I + interest - O - fee + wd_in - wd_out
            # guard (rounding) – never negative
            neg = B_new < 0
            O[neg] += B_new[neg]
            B_new[neg] = 0
            B[idx] = B_new
            txn_parts.append(self._casa_events(p, idx, acc, I, payroll_amt, O, interest, fee, wd_in, wd_out,
                                               opening, closing))
            status = np.where(closing, "CLOSED", np.where(acc._dormant.values[idx], "DORMANT", "ACTIVE"))
            bal_rows.append(pd.DataFrame({"snapshot_date": me, "account_no": acc.account_no.values[idx],
                                          "balance": B_new.astype(np.int64), "accrued_interest": 0,
                                          "status": status, "_bdate": me}))
        txn = pd.concat(txn_parts, ignore_index=True)
        txn = self._finalise_txn(txn)
        return pd.concat(bal_rows, ignore_index=True), txn

    def _casa_events(self, p, idx, acc, I, payroll_amt, O, interest, fee, wd_in, wd_out, opening, closing):
        rng = self.rng
        n = len(idx)
        is_sme = acc._is_sme.values[idx]
        dormant = acc._dormant.values[idx]
        mi = self.months.get_loc(p)
        # ------------ credits
        other_in = I - payroll_amt
        lam_in = np.where(is_sme, 10, np.where(dormant, 0.2, 1.1))
        n_in = rng.poisson(lam_in)
        n_in = np.where((other_in > 0) & (n_in == 0), 1, n_in)
        n_in = np.where(other_in <= 0, 0, n_in)
        # ------------ debits
        tet_boost = 1.35 if p.month in (1, 2) else 1.0
        lam = {
            "TRF_OUT": np.where(is_sme, 14, np.where(dormant, 0.2, 2.8)),
            "BILL_PAY": np.where(is_sme, 2, np.where(dormant, 0.05, 1.1)),
            "ATM_WD": np.where(is_sme, 0, np.where(dormant, 0.05, 1.2 * tet_boost)),
            "POS_PURCHASE": np.where(is_sme, 0, np.where(dormant, 0.05, 1.8)),
        }
        share = {"TRF_OUT": 1.0, "BILL_PAY": 0.12, "ATM_WD": 0.35, "POS_PURCHASE": 0.12}
        counts = {k: rng.poisson(v) for k, v in lam.items()}
        counts["TRF_OUT"] = np.where((O > 0) & (sum(counts.values()) == 0), 1, counts["TRF_OUT"])
        counts = {k: np.where(O > 0, v, 0) for k, v in counts.items()}
        parts = []

        def expand(cnt, ttype, drcr, total):
            rep = np.repeat(np.arange(n), cnt)
            if len(rep) == 0:
                return None
            return pd.DataFrame({"row": rep, "txn_type": ttype, "dr_cr": drcr, "_w": rng.gamma(1.2, 1.0, len(rep)),
                                 "_total": total[rep]})
        # credits: payroll + other
        pr = np.where(payroll_amt > 0)[0]
        if len(pr):
            parts.append(pd.DataFrame({"row": pr, "txn_type": "PAYROLL", "dr_cr": "C", "_w": 1.0,
                                       "_amt": payroll_amt[pr]}))
        ci = expand(n_in, "TRF_IN", "C", other_in)
        if ci is not None:
            ci["_amt"] = ci._total * ci._w / np.bincount(ci.row, weights=ci._w, minlength=n)[ci.row]
            parts.append(ci.drop(columns="_total"))
        # debits: split O by type weights
        wtot = np.zeros(n)
        dparts = []
        for k, c in counts.items():
            e = expand(c, k, "D", O)
            if e is not None:
                e["_w"] = e._w * share[k]
                dparts.append(e)
        if dparts:
            d = pd.concat(dparts, ignore_index=True)
            wtot = np.bincount(d.row, weights=d._w, minlength=n)
            d["_amt"] = d._total * d._w / wtot[d.row]
            parts.append(d.drop(columns="_total"))
        for amt, ttype, drcr in ((interest, "INTEREST", "C"), (fee, "FEE", "D"), (wd_in, "TRF_IN", "C"),
                                 (wd_out, "TRF_OUT", "D")):
            r = np.where(amt > 0)[0]
            if len(r):
                ev = pd.DataFrame({"row": r, "txn_type": ttype, "dr_cr": drcr, "_w": 1.0, "_amt": amt[r]})
                if ttype == "FEE":
                    ev["_fee"] = True
                if amt is wd_in:
                    ev["_wd"] = "in"
                if amt is wd_out:
                    ev["_wd"] = "out"
                parts.append(ev)
        ev = pd.concat(parts, ignore_index=True)
        ev["_fee"] = ev.get("_fee", False)
        ev["_wd"] = ev.get("_wd", None)
        ev["_fee"] = ev["_fee"].fillna(False).astype(bool)
        # rounding: ATM multiples of 100k, others 1k; interest exact
        rnd = np.where(ev.txn_type == "ATM_WD", -5, np.where(ev.txn_type == "INTEREST", 0, -3))
        ev["amount"] = [round(a, r) for a, r in zip(ev._amt.values, rnd)]
        bad_atm = (ev.txn_type == "ATM_WD") & (ev.amount < 100_000)
        ev.loc[bad_atm, "txn_type"] = "TRF_OUT"
        ev.loc[bad_atm, "amount"] = ev.loc[bad_atm, "_amt"].round(-3)
        # fix residuals so that per-account credits == I+interest+wd_in and debits == O+fee+wd_out
        for drcr, target in (("C", I + interest + wd_in), ("D", O + fee + wd_out)):
            sub = ev[ev.dr_cr == drcr]
            if sub.empty:
                continue
            got = np.bincount(sub.row, weights=sub.amount, minlength=n)
            diff = np.round(target - got)
            big = sub.groupby("row")["amount"].idxmax()
            ev.loc[big.values, "amount"] += diff[big.index.values]
        ev = ev[ev.amount != 0].copy()
        # ------------ dates, channels
        month_start = p.start_time.date()
        w_dig, days = cal.day_weights(month_start, "digital")
        w_cnt, _ = cal.day_weights(month_start, "counter")
        w_atm, _ = cal.day_weights(month_start, "atm")
        w_pay, _ = cal.day_weights(month_start, "payroll")
        mobile_share = 0.70 + 0.16 * mi / max(len(self.months) - 1, 1)
        internet_share = 0.09 - 0.04 * mi / max(len(self.months) - 1, 1)
        acc_rows = idx[ev.row.values]
        counter_pref = acc._counter_pref.values[acc_rows]
        sme_rows = acc._is_sme.values[acc_rows]
        u = rng.random(len(ev))
        p_counter = np.where(sme_rows, 0.14 - 0.05 * mi / 31, np.clip(1 - mobile_share - internet_share + counter_pref, 0, 0.8))
        p_internet = np.where(sme_rows, 0.6, internet_share)
        ch = np.where(u < p_counter, "COUNTER", np.where(u < p_counter + p_internet, "INTERNET", "MOBILE"))
        t = ev.txn_type.values
        ch = np.where(t == "ATM_WD", "ATM", np.where(t == "POS_PURCHASE", "POS",
                      np.where(np.isin(t, ["PAYROLL", "INTEREST", "FEE"]), "SYSTEM", ch)))
        ch = np.where((t == "BILL_PAY") & (ch == "COUNTER"), "MOBILE", ch)
        ev["channel_code"] = ch
        # counter transfers become cash deposits / withdrawals half of the time
        cash = (ch == "COUNTER") & (rng.random(len(ev)) < 0.5)
        ev.loc[cash & (t == "TRF_IN"), "txn_type"] = "CASH_DEP"
        ev.loc[cash & (t == "TRF_OUT"), "txn_type"] = "CASH_WD"
        day_idx = np.empty(len(ev), dtype=int)
        for kind, wts in (("digital", w_dig), ("counter", w_cnt), ("atm", w_atm), ("payroll", w_pay)):
            if kind == "counter":
                m = ch == "COUNTER"
            elif kind == "atm":
                m = ch == "ATM"
            elif kind == "payroll":
                m = t == "PAYROLL"
            else:
                m = ~((ch == "COUNTER") | (ch == "ATM") | (t == "PAYROLL"))
            day_idx[m] = rng.choice(len(days), size=m.sum(), p=wts)
        last = len(days) - 1
        # month-end system postings, window dressing on last/first business day
        day_idx[np.isin(t, ["INTEREST", "FEE"])] = last
        bdays = [i for i, d in enumerate(days) if cal.is_business_day(d)]
        wd = ev._wd.values
        day_idx[wd == "in"] = bdays[-1]
        day_idx[wd == "out"] = bdays[0]
        # opening accounts: nothing before open date; closing accounts: nothing after close date
        od = np.array([(d - month_start).days for d in pd.to_datetime(acc.open_date.values[acc_rows]).date])
        cd_raw = acc.close_date.values[acc_rows]
        cd = np.array([(d - month_start).days if isinstance(d, date) else last for d in cd_raw])
        day_idx = np.clip(day_idx, np.clip(od, 0, last), np.clip(cd, 0, last))
        # time of day
        sec = np.where(ch == "COUNTER", rng.integers(8 * 3600, 16 * 3600 + 1800, len(ev)),
                       np.where(ch == "SYSTEM", rng.integers(0, 3 * 3600, len(ev)),
                                self._digital_seconds(len(ev))))
        base_ts = np.datetime64(month_start) + day_idx.astype("timedelta64[D]")
        ev["txn_datetime"] = base_ts + sec.astype("timedelta64[s]")
        ev["account_no"] = acc.account_no.values[acc_rows]
        ev["branch_code"] = acc.branch_code.values[acc_rows]
        ev["_cust_branch"] = ev["branch_code"]
        return ev[["account_no", "txn_datetime", "txn_type", "dr_cr", "amount", "channel_code", "branch_code"]]

    def _digital_seconds(self, n: int) -> np.ndarray:
        """Time-of-day for digital channels: bimodal (lunch & evening peaks), few at night."""
        rng = self.rng
        comp = rng.random(n)
        sec = np.where(comp < 0.45, rng.normal(11.5 * 3600, 2.2 * 3600, n),
                       np.where(comp < 0.92, rng.normal(19.5 * 3600, 2.5 * 3600, n), rng.uniform(0, 86399, n)))
        bad = (sec < 0) | (sec > 86399)
        sec[bad] = rng.uniform(6 * 3600, 23 * 3600, bad.sum())
        return sec.astype(int)

    def _finalise_txn(self, txn: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        txn = txn.sort_values("txn_datetime", kind="stable").reset_index(drop=True)
        tdate = txn.txn_datetime.dt.date
        uniq = pd.Series(pd.unique(tdate))
        nbd = {d: cal.next_business_day(d) for d in uniq}
        txn["business_date"] = tdate.map(nbd)
        # reversals: 0.1% of outgoing transfers are reversed and re-sent (net zero effect)
        cand = txn.index[(txn.txn_type == "TRF_OUT") & (txn.channel_code != "COUNTER")]
        rev_idx = rng.choice(cand, size=int(len(cand) * 0.001), replace=False)
        rev = txn.loc[rev_idx].copy()
        rev["dr_cr"], rev["is_reversal"] = "C", 1
        rev["txn_datetime"] = rev.txn_datetime + pd.to_timedelta(rng.integers(60, 1800, len(rev)), unit="s")
        resend = txn.loc[rev_idx].copy()
        resend["is_reversal"] = 0
        resend["txn_datetime"] = rev.txn_datetime + pd.to_timedelta(rng.integers(60, 600, len(rev)), unit="s")
        txn["is_reversal"] = 0
        txn = pd.concat([txn, rev, resend], ignore_index=True)
        # keep reversals inside the same business date / month
        txn["business_date"] = txn.txn_datetime.dt.date.map(lambda d: nbd.get(d) or cal.next_business_day(d))
        txn = txn.sort_values(["txn_datetime", "account_no"], kind="stable").reset_index(drop=True)
        # ATM id (80% own branch ATM)
        atms = self.atm_list()
        by_branch = atms.groupby("branch_code")["atm_id"].apply(list).to_dict()
        is_atm = (txn.txn_type == "ATM_WD").values
        own = rng.random(is_atm.sum()) < 0.8
        brs = txn.branch_code.values[is_atm]
        all_ids = atms.atm_id.values
        txn["atm_id"] = ""
        txn.loc[is_atm, "atm_id"] = [rng.choice(by_branch[b]) if o and b in by_branch else rng.choice(all_ids)
                                     for b, o in zip(brs, own)]
        # counterparty bank & description
        tt = txn.txn_type.values
        is_trf = np.isin(tt, ["TRF_IN", "TRF_OUT"])
        txn["counterparty_bank"] = np.where(is_trf, np.where(rng.random(len(txn)) < 0.22, "DLB",
                                            rng.choice(VN_BANKS, len(txn))), "")
        mm = txn.txn_datetime.dt.strftime("%m/%Y")
        desc_map = {"PAYROLL": "Luong thang ", "TRF_IN": "Nhan chuyen tien", "TRF_OUT": "Chuyen tien den",
                    "BILL_PAY": "Thanh toan hoa don", "ATM_WD": "Rut tien ATM", "POS_PURCHASE": "Thanh toan the POS",
                    "INTEREST": "Tra lai tien gui KKH thang ", "FEE": "Phi dich vu thang ", "CASH_DEP": "Nop tien mat",
                    "CASH_WD": "Rut tien mat tai quay"}
        desc = pd.Series(tt).map(desc_map).values
        suffix = np.isin(tt, ["PAYROLL", "INTEREST", "FEE"])
        txn["description"] = np.where(suffix, desc + mm.values, desc)
        txn.loc[txn.is_reversal == 1, "description"] = "Hoan tra giao dich loi"
        bill_kinds = np.array(["dien", "nuoc", "internet", "di dong tra sau", "hoc phi", "bao hiem"])
        bill = tt == "BILL_PAY"
        txn.loc[bill, "description"] = "Thanh toan hoa don " + rng.choice(bill_kinds, bill.sum())
        # transaction reference: FT + yy + day-of-year + running number per business date
        bd = pd.to_datetime(txn.business_date)
        txn["_seq"] = txn.groupby("business_date").cumcount() + 1
        txn["txn_id"] = "FT" + bd.dt.strftime("%y%j") + txn._seq.map(lambda x: f"{x:06d}")
        txn["amount"] = txn.amount.astype(np.int64)
        txn["_bdate"] = txn.business_date
        cols = ["txn_id", "account_no", "txn_datetime", "business_date", "txn_type", "dr_cr", "amount",
                "channel_code", "branch_code", "atm_id", "counterparty_bank", "description", "is_reversal", "_bdate"]
        return txn[cols]

    def atm_list(self) -> pd.DataFrame:
        if hasattr(self, "_atms"):
            return self._atms
        rows = []
        for _, b in self.branches.iterrows():
            for i in range(b.n_atm):
                rows.append({"atm_id": f"ATM{b.branch_code}{i + 1:02d}", "branch_code": b.branch_code,
                             "size": b.size_weight})
        self._atms = pd.DataFrame(rows)
        return self._atms

    # ================================================================== TERM DEPOSITS
    TD_TERMS_IND = ([1, 3, 6, 12, 24, 36], [.07, .12, .24, .40, .10, .07])
    TD_TERMS_SME = ([1, 3, 6, 12], [.35, .35, .2, .1])

    def _eligible(self, when: date, ctype: str) -> np.ndarray:
        c = self.cust
        return np.where((c.customer_type.values == ctype) & (c.open_date.values <= when) & c.close_date.isna().values)[0]

    def _new_tds(self, n: int, ctype: str, month: pd.Period, open_dates: np.ndarray, progress: float) -> pd.DataFrame:
        rng, c = self.rng, self.cust
        pool = self._eligible(open_dates.max() if len(open_dates) else month.end_time.date(), ctype)
        seg = c.segment.values[pool]
        w = np.select([seg == "PRIORITY", seg == "AFFLUENT", seg == "SME"], [10, 4, 1], 1).astype(float)
        who = rng.choice(pool, size=n, p=w / w.sum())
        if ctype == "IND":
            sg = c.segment.values[who]
            med = np.select([sg == "PRIORITY", sg == "AFFLUENT"], [1.8e9, 4.5e8], 1.2e8)
            amt = med * rng.lognormal(0, 0.7, n)
            r = rng.random(n)
            amt = np.where(r < 0.6, np.round(amt, -7), np.where(r < 0.9, np.round(amt, -6), np.round(amt, -5)))
            amt = np.maximum(amt, 1e6)
            terms = rng.choice(self.TD_TERMS_IND[0], n, p=self.TD_TERMS_IND[1])
            online = rng.random(n) < (0.32 + 0.28 * progress)
            prod = np.where(online, "TD_ONLINE", "TD_COUNTER")
            bonus = np.where(online, 0.15, 0) + np.select([sg == "PRIORITY", sg == "AFFLUENT"], [0.25, 0.1], 0)
        else:
            amt = np.maximum(np.round(2.5e9 * rng.lognormal(0, 0.8, n), -8), 1e8)
            terms = rng.choice(self.TD_TERMS_SME[0], n, p=self.TD_TERMS_SME[1])
            prod = np.full(n, "TD_SME")
            bonus = np.full(n, -0.3)
        rate = np.round(self.dep_rate(month, terms) + bonus + rng.normal(0, 0.03, n), 2)
        mat = [ (pd.Timestamp(o) + pd.DateOffset(months=int(t))).date() for o, t in zip(open_dates, terms)]
        return pd.DataFrame({"cust_idx": who, "cif": c.cif.values[who], "product_code": prod,
                             "branch_code": c.home_branch_code.values[who], "open_date": open_dates,
                             "maturity_date": mat, "term_months": terms, "interest_rate": rate,
                             "principal": amt.astype(np.int64), "rollover_of": "", "close_date": None,
                             "close_reason": ""})

    def build_term_deposits(self, casa0: float):
        rng = self.rng
        td0 = casa0 * (1 / 0.33 - 1)
        parts = []
        for ctype, share in (("IND", 0.8), ("SME", 0.2)):
            target, got = td0 * share, 0.0
            while got < target:
                n = 400
                df = self._new_tds(n, ctype, pd.Period("2023-12", "M"), np.array([self.init_date] * n), 0.0)
                # back-date: contracts were opened some time before the migration date
                back = [int(rng.integers(0, t * 30 + 1)) for t in df.term_months]
                df["open_date"] = [self.init_date - timedelta(days=b) for b in back]
                df["maturity_date"] = [(pd.Timestamp(o) + pd.DateOffset(months=int(t))).date()
                                       for o, t in zip(df.open_date, df.term_months)]
                df = df[df.maturity_date > self.init_date]
                df["interest_rate"] = df.interest_rate + 0.3
                cum = df.principal.cumsum() + got
                df = df[cum.shift(fill_value=got) < target]
                parts.append(df)
                got += df.principal.sum()
        tds = pd.concat(parts, ignore_index=True)
        snaps = [self._td_snapshot(tds, self.init_date)]
        # growth path
        g = {2024: 0.0100, 2025: 0.0112, 2026: 0.0095}
        target = tds.principal.sum()
        for mi, p in enumerate(self.months):
            ms, me = p.start_time.date(), p.end_time.date()
            progress = mi / (len(self.months) - 1)
            tet = cal.TET_DAYS.get(p.year)
            gm = g[p.year] + rng.normal(0, 0.003)
            if tet and pd.Period(tet, "M") == p:
                gm -= 0.02
            if tet and pd.Period(tet, "M") + 1 == p:
                gm += 0.018
            target *= 1 + gm
            open_mask = tds.close_date.isna().values
            # early withdrawals
            haz = 0.0035 * (3 if (tet and p in (pd.Period(tet, "M"), pd.Period(tet, "M") - 1)) else 1)
            ew = open_mask & (rng.random(len(tds)) < haz) & (tds.maturity_date.values > me)
            if ew.any():
                tds.loc[ew, "close_date"] = self.random_dates(ms, me, ew.sum(), "counter")
                tds.loc[ew, "close_reason"] = "EARLY"
            # maturities
            mat_mask = tds.close_date.isna().values & (tds.maturity_date.values >= ms) & (tds.maturity_date.values <= me)
            mat_idx = np.where(mat_mask)[0]
            roll = rng.random(len(mat_idx)) < 0.65
            tds.loc[mat_idx, "close_date"] = tds.maturity_date.values[mat_idx]
            tds.loc[mat_idx, "close_reason"] = np.where(roll, "ROLLOVER", "MATURED")
            if roll.any():
                old = tds.iloc[mat_idx[roll]]
                interest = old.principal * old.interest_rate / 100 * old.term_months / 12
                new = old.copy()
                new["open_date"] = old.maturity_date.values
                new["maturity_date"] = [(pd.Timestamp(o) + pd.DateOffset(months=int(t))).date()
                                        for o, t in zip(new.open_date, new.term_months)]
                new["interest_rate"] = np.round(self.dep_rate(p, new.term_months.values) +
                                                np.where(new.product_code == "TD_SME", -0.3,
                                                         np.where(new.product_code == "TD_ONLINE", 0.15, 0)), 2)
                new["principal"] = np.round(old.principal + interest, -3).astype(np.int64)
                new["rollover_of"] = old.index.map(lambda i: f"__{i}")
                new["close_date"], new["close_reason"] = None, ""
                tds = pd.concat([tds, new], ignore_index=True)
            alive = tds.close_date.isna() | (pd.to_datetime(tds.close_date) > pd.Timestamp(me))
            alive &= pd.to_datetime(tds.open_date) <= pd.Timestamp(me)
            current = tds.loc[alive, "principal"].sum()
            need = max(target - current, 0.012 * current)
            new_parts, got = [], 0.0
            while got < need:
                ctype = "IND" if rng.random() < 0.82 else "SME"
                n = 60
                od = self.random_dates(ms, me, n, "digital" if ctype == "IND" else "counter")
                df = self._new_tds(n, ctype, p, od, progress)
                cum = df.principal.cumsum() + got
                df = df[cum.shift(fill_value=got) < need]
                new_parts.append(df)
                got += df.principal.sum()
            tds = pd.concat([tds] + new_parts, ignore_index=True)
            snaps.append(self._td_snapshot(tds, me))
        # ids
        tds = tds.reset_index(drop=True)
        tds["td_id"] = ["TD" + pd.Timestamp(o).strftime("%y%m") + f"{i:07d}" for i, o in enumerate(tds.open_date)]
        id_map = dict(zip(tds.index, tds.td_id))
        tds["rollover_of"] = tds.rollover_of.map(lambda x: id_map[int(x[2:])] if x.startswith("__") else "")
        snap = pd.concat(snaps, ignore_index=True)
        snap["td_id"] = snap["_row"].map(id_map)
        snap = snap.drop(columns="_row")
        cols = ["td_id", "cif", "product_code", "branch_code", "open_date", "maturity_date", "term_months",
                "interest_rate", "principal", "rollover_of", "close_date", "close_reason"]
        opened = tds[cols].copy()
        opened["close_date"], opened["close_reason"] = None, ""
        opened["_bdate"] = [self.init_date if o <= self.init_date else route_date(o) for o in tds.open_date]
        closed = tds[tds.close_date.notna()][cols].copy()
        closed["_bdate"] = [route_date(d) for d in closed.close_date]
        self.tds = tds
        return pd.concat([opened, closed], ignore_index=True), snap

    def _td_snapshot(self, tds: pd.DataFrame, d: date) -> pd.DataFrame:
        od = pd.to_datetime(tds.open_date)
        alive = (od <= pd.Timestamp(d)) & (tds.close_date.isna() | (pd.to_datetime(tds.close_date) > pd.Timestamp(d)))
        s = tds[alive]
        days = (pd.Timestamp(d) - pd.to_datetime(s.open_date)).dt.days
        return pd.DataFrame({"snapshot_date": d, "_row": s.index, "principal": s.principal.values,
                             "accrued_interest": np.round(s.principal * s.interest_rate / 100 * days / 365).astype(np.int64).values,
                             "status": "ACTIVE", "_bdate": d})

    # ================================================================== LOANS
    LOAN_PARAMS = {
        # product: (median, sigma, terms, probs, method, collateral_type, coll_lo, coll_hi, rounding, share)
        "LN_MORTGAGE": (1.3e9, .55, [120, 180, 240, 300], [.2, .35, .3, .15], "EQUAL_PRINCIPAL", "BAT_DONG_SAN", 1.4, 2.2, -7, .37),
        "LN_HOUSEHOLD": (6e8, .7, [12, 24, 36, 60], [.3, .3, .25, .15], "EQUAL_PRINCIPAL", "BAT_DONG_SAN", 1.3, 2.0, -7, .12),
        "LN_AUTO": (5.5e8, .4, [36, 48, 60, 72, 84], [.1, .2, .35, .2, .15], "EQUAL_PRINCIPAL", "O_TO", 1.2, 1.4, -7, .08),
        "LN_CONSUMER": (8e7, .6, [12, 24, 36, 48, 60], [.15, .25, .3, .15, .15], "EQUAL_PRINCIPAL", "", 0, 0, -6, .05),
        "LN_TDSECURED": (2.5e8, .8, [3, 6, 12], [.3, .4, .3], "BULLET", "SO_TIET_KIEM", 1.05, 1.2, -6, .02),
        "LN_SME_WC": (1.6e9, .75, [3, 6, 9, 12], [.15, .35, .2, .3], "BULLET", "BDS_HANG_TON_KHO", 1.0, 1.5, -8, .26),
        "LN_SME_TERM": (2.6e9, .75, [36, 48, 60, 84], [.25, .3, .3, .15], "EQUAL_PRINCIPAL", "BDS_MAY_MOC", 1.1, 1.6, -8, .10),
    }
    P_MISS = {"LN_MORTGAGE": .0048, "LN_HOUSEHOLD": .0115, "LN_AUTO": .0085, "LN_CONSUMER": .022,
              "LN_TDSECURED": .0006, "LN_SME_WC": .0092, "LN_SME_TERM": .008}

    def _new_loans(self, n: int, month: pd.Period, dates: np.ndarray, product: str | None = None) -> pd.DataFrame:
        rng, c = self.rng, self.cust
        prods = list(self.LOAN_PARAMS)
        share = np.array([self.LOAN_PARAMS[p][9] for p in prods])
        # sample products by amount share -> convert to count share via median amounts
        cnt_w = share / np.array([self.LOAN_PARAMS[p][0] for p in prods])
        prod = np.full(n, product) if product else rng.choice(prods, size=n, p=cnt_w / cnt_w.sum())
        rows = []
        when = dates.max()
        ind_pool = self._eligible(when, "IND")
        sme_pool = self._eligible(when, "SME")
        seg = c.segment.values
        for pcode in np.unique(prod):
            m = prod == pcode
            k = m.sum()
            med, sig, terms, tp, method, ctype, clo, chi, rnd, _ = self.LOAN_PARAMS[pcode]
            if pcode.startswith("LN_SME"):
                who = rng.choice(sme_pool, k)
            else:
                pool = ind_pool
                if pcode == "LN_TDSECURED" and hasattr(self, "tds"):
                    holders = np.unique(self.tds.cust_idx.values)
                    pool = np.intersect1d(ind_pool, holders)
                w = np.ones(len(pool))
                sp = seg[pool]
                if pcode in ("LN_MORTGAGE", "LN_AUTO"):
                    w = np.select([sp == "PRIORITY", sp == "AFFLUENT"], [4, 3], 1).astype(float)
                if pcode == "LN_HOUSEHOLD":
                    w = np.where(c.occupation.values[pool] == "Chủ doanh nghiệp/hộ kinh doanh", 8.0, 1.0)
                if pcode == "LN_CONSUMER":
                    w = np.where(sp == "MASS", 3.0, 1.0)
                who = rng.choice(pool, k, p=w / w.sum())
            city = np.isin(c.province_code.values[who], ["01", "79"])
            amt = med * rng.lognormal(0, sig, k) * np.where(city & (pcode == "LN_MORTGAGE"), 1.3, 1.0)
            amt = np.maximum(np.round(amt, rnd), 10 ** (-rnd))
            term = rng.choice(terms, k, p=tp)
            coll = np.round(amt * rng.uniform(clo, chi, k), -6) if clo else np.zeros(k)
            rows.append(pd.DataFrame({
                "cust_idx": who, "cif": c.cif.values[who], "product_code": pcode,
                "branch_code": c.home_branch_code.values[who], "disbursement_date": dates[m],
                "term_months": term, "approved_amount": amt.astype(np.int64),
                "interest_rate": np.round(self.lend_rate(month, pcode) + rng.normal(0, 0.25, k), 2),
                "repayment_method": method, "collateral_type": ctype, "collateral_value": coll.astype(np.int64),
            }))
        df = pd.concat(rows, ignore_index=True)
        df["maturity_date"] = [(pd.Timestamp(d) + pd.DateOffset(months=int(t))).date()
                               for d, t in zip(df.disbursement_date, df.term_months)]
        df["outstanding"] = df.approved_amount.astype(float)
        df["overdue"] = 0.0
        df["oldest_due"] = pd.NaT
        df["cic_group"], df["cic_until"] = 0, pd.NaT
        df["close_date"], df["close_reason"] = None, ""
        df["renewal_of"] = ""
        return df

    def _disb_dates(self, p: pd.Period, n: int) -> np.ndarray:
        days = cal.business_days(p.start_time.date(), p.end_time.date())
        x = np.arange(1, len(days) + 1) / len(days)
        w = 1 + 2 * x ** 3 * (2 if p.month in (3, 6, 9, 12) else 1)
        return np.array(days)[self.rng.choice(len(days), n, p=w / w.sum())]

    def build_loans(self, deposits0: float):
        rng = self.rng
        L0 = deposits0 * 0.76
        # ---- initial book
        parts, got = [], 0.0
        while got < L0:
            n = 300
            dd = np.array([self.init_date] * n)
            df = self._new_loans(n, pd.Period("2024-01", "M"), dd)
            el = np.array([int(rng.integers(0, t)) for t in df.term_months])
            df["disbursement_date"] = [(pd.Timestamp(self.init_date) - pd.DateOffset(months=int(e), days=int(rng.integers(0, 28)))).date()
                                       for e in el]
            df["maturity_date"] = [(pd.Timestamp(d) + pd.DateOffset(months=int(t))).date()
                                   for d, t in zip(df.disbursement_date, df.term_months)]
            ep = df.repayment_method == "EQUAL_PRINCIPAL"
            df.loc[ep, "outstanding"] = np.round(df.approved_amount[ep] * (1 - el[ep.values] / df.term_months[ep]), -3)
            df["interest_rate"] = df.interest_rate + 0.4
            df = df[df.maturity_date > self.init_date]
            cum = df.outstanding.cumsum() + got
            df = df[cum.shift(fill_value=got) < L0]
            parts.append(df)
            got += df.outstanding.sum()
        loans = pd.concat(parts, ignore_index=True)
        # small initial delinquency so that the book starts with a realistic NPL
        init_bad = rng.random(len(loans)) < 0.03
        loans.loc[init_bad, "oldest_due"] = [pd.Timestamp(self.init_date) - pd.Timedelta(days=int(d))
                                             for d in rng.choice([20, 45, 75, 120, 150, 200, 280, 400], init_bad.sum(),
                                                                 p=[.28, .2, .14, .1, .08, .08, .06, .06])]
        snaps = [self._loan_snapshot(loans, self.init_date, np.ones(len(loans), bool))]
        # ---- growth path of non-card loans
        g_year = {2024: 0.155, 2025: 0.18, 2026: 0.09}
        sw = {1: .5, 2: .25, 3: 1.2, 4: .8, 5: .9, 6: 1.3, 7: .8, 8: .9, 9: 1.2, 10: .9, 11: 1.1, 12: 2.1}
        target = loans.outstanding.sum()
        for mi, p in enumerate(self.months):
            ms, me = p.start_time.date(), p.end_time.date()
            months_in_year = [m for m in range(1, 13) if pd.Period(f"{p.year}-{m:02d}", "M") in self.months]
            wsum = sum(sw[m] for m in months_in_year)
            # relative controller: grow from the actual book at the end of the previous month
            base_book = loans.loc[loans.close_date.isna(), "outstanding"].sum()
            target = base_book * np.exp(np.log(1 + g_year[p.year]) * sw[p.month] / wsum) * rng.lognormal(0, 0.003)
            loans, closed_rows = self._loan_month(loans, p)
            snaps.append(closed_rows)
            live = loans.close_date.isna()
            current = loans.loc[live, "outstanding"].sum()
            need = target - current
            # portfolio-mix controller: allocate the required growth to products that are below their target share
            cur_p = loans[live].groupby("product_code").outstanding.sum()
            shares = {k: v[9] for k, v in self.LOAN_PARAMS.items()}
            gap = {k: max(target * sh * rng.lognormal(0, 0.05) - cur_p.get(k, 0.0), 0.0) for k, sh in shares.items()}
            gsum = sum(gap.values())
            new_parts = []
            if need > 0 and gsum > 0:
                for prod_code, gp in gap.items():
                    sub_need, got = gp / gsum * need, 0.0
                    while got < sub_need:
                        n = 25
                        df = self._new_loans(n, p, self._disb_dates(p, n), product=prod_code)
                        cum = df.outstanding.cumsum() + got
                        df = df[cum <= sub_need] if (cum <= sub_need).any() else df.iloc[:0]
                        new_parts.append(df)
                        got += df.outstanding.sum()
                        if df.empty:          # next loan would overshoot the monthly target
                            break
            if new_parts:
                loans = pd.concat([loans] + new_parts, ignore_index=True)
            live = loans.close_date.isna().values
            snaps.append(self._loan_snapshot(loans, me, live))
        loans = loans.reset_index(drop=True)
        loans["loan_id"] = ["LD" + pd.Timestamp(d).strftime("%y%m") + f"{i:06d}" for i, d in enumerate(loans.disbursement_date)]
        snap = pd.concat(snaps, ignore_index=True)
        snap["loan_id"] = snap["_row"].map(dict(zip(loans.index, loans.loan_id)))
        snap = snap.drop(columns="_row")
        self.loans = loans
        cols = ["loan_id", "cif", "product_code", "branch_code", "disbursement_date", "maturity_date", "term_months",
                "approved_amount", "interest_rate", "repayment_method", "collateral_type", "collateral_value",
                "close_date", "close_reason"]
        opened = loans[cols].copy()
        opened["close_date"], opened["close_reason"] = None, ""
        opened["_bdate"] = [self.init_date if d <= self.init_date else route_date(d) for d in loans.disbursement_date]
        closed = loans[loans.close_date.notna()][cols].copy()
        closed["_bdate"] = [route_date(d) for d in closed.close_date]
        return pd.concat([opened, closed], ignore_index=True), snap

    def _loan_month(self, loans: pd.DataFrame, p: pd.Period):
        rng = self.rng
        ms, me = p.start_time.date(), p.end_time.date()
        live = np.where(loans.close_date.isna().values & (pd.to_datetime(loans.disbursement_date).values < np.datetime64(ms)))[0]
        L = loans.iloc[live]
        n = len(L)
        prod = L.product_code.values
        p_miss = np.array([self.P_MISS[x] for x in prod])
        macro = {2024: 1.0, 2025: 1.1 if p.month <= 6 else 1.0, 2026: 0.95}[p.year]
        p_miss = p_miss * macro
        ev_lo, ev_hi = EVENTS["npl_window"]
        in_event = np.isin(L.branch_code.values, list(EVENTS["npl_branches"])) & np.isin(prod, list(EVENTS["npl_products"]))
        if ev_lo <= p <= ev_hi:
            p_miss = np.where(in_event, p_miss * 10, p_miss)
        od = pd.to_datetime(L.oldest_due)
        dpd_start = np.where(od.notna(), (pd.Timestamp(ms) - od).dt.days.fillna(0), 0)
        cont = np.select([dpd_start <= 0, dpd_start <= 30, dpd_start <= 90, dpd_start <= 180], [0, .55, .68, .82], .9)
        if ev_lo <= p <= ev_hi:
            cont = np.where(in_event & (cont > 0), np.minimum(cont + 0.2, 0.95), cont)
        prob = np.where(od.notna(), cont, p_miss)
        miss = rng.random(n) < prob
        term = L.term_months.values
        ep = L.repayment_method.values == "EQUAL_PRINCIPAL"
        inst = np.where(ep, L.approved_amount.values / term, 0.0)
        mat_this = (pd.to_datetime(L.maturity_date).values <= np.datetime64(me))
        inst = np.where(~ep & mat_this, L.outstanding.values, inst)
        inst = np.minimum(inst, L.outstanding.values)
        due_day = np.array([min(pd.Timestamp(d).day, 28) for d in L.disbursement_date])
        due = pd.to_datetime([date(p.year, p.month, int(dd)) for dd in due_day])
        out = L.outstanding.values.copy()
        overdue = L.overdue.values.copy()
        oldest = od.values.copy()
        # missed payment
        new_od = miss & od.isna().values
        oldest[new_od] = due.values[new_od]
        overdue[miss] += inst[miss]
        # payments
        pay = ~miss
        was_late = pay & od.notna().values
        full_cure = was_late & (rng.random(n) < 0.65)
        partial = was_late & ~full_cure
        out[pay & ~was_late] -= inst[pay & ~was_late]
        out[full_cure] -= overdue[full_cure] + inst[full_cure]
        overdue[full_cure] = 0
        oldest[full_cure] = np.datetime64("NaT")
        out[partial] -= inst[partial]
        overdue[partial] = np.maximum(overdue[partial] - inst[partial], 0)
        oldest[partial] = (pd.to_datetime(oldest[partial]) + pd.DateOffset(months=1)).values
        out = np.maximum(np.round(out), 0)
        overdue = np.minimum(np.round(overdue), out)
        loans.loc[L.index, "outstanding"] = out
        loans.loc[L.index, "overdue"] = overdue
        loans.loc[L.index, "oldest_due"] = oldest
        dpd_me = np.where(pd.notna(oldest), (pd.Timestamp(me) - pd.to_datetime(oldest)).days, 0)
        dpd_me = np.nan_to_num(np.asarray(dpd_me, dtype=float))
        # CIC-driven group (other credit institutions report worse group) for a small share
        cic_new = (rng.random(n) < 0.003) & (dpd_me < 10)
        loans.loc[L.index[cic_new], "cic_group"] = rng.choice([2, 3], cic_new.sum(), p=[.8, .2])
        loans.loc[L.index[cic_new], "cic_until"] = pd.Timestamp(me) + pd.to_timedelta(rng.integers(30, 150, cic_new.sum()), unit="D")
        expired = pd.to_datetime(loans.loc[L.index, "cic_until"]).values < np.datetime64(me)
        loans.loc[L.index[expired], "cic_group"] = 0
        loans.loc[L.index[expired], "cic_until"] = pd.NaT
        # closures
        reason = np.full(n, "", dtype=object)
        reason[(out <= 0)] = "MATURED"
        prepay_p = np.select([prod == "LN_MORTGAGE", prod == "LN_AUTO", prod == "LN_CONSUMER"], [.005, .006, .008], 0)
        reason[(reason == "") & (dpd_me == 0) & (rng.random(n) < prepay_p)] = "PREPAID"
        secured = L.collateral_value.values > 0
        reason[(reason == "") & secured & (dpd_me > 180) & (rng.random(n) < 0.07)] = "RECOVERED"
        if p.month in (3, 6, 9, 12):
            wo = (reason == "") & (((dpd_me > 360) & (rng.random(n) < 0.4)) |
                                   ((~secured) & (dpd_me > 180) & (rng.random(n) < 0.25)))
            reason[wo] = "WRITTEN_OFF"
        # bullet loans reaching maturity while overdue stay open (overdue principal)
        reason[(reason == "MATURED") & (overdue > 0)] = ""
        closing = reason != ""
        cdates = self.random_dates(ms, me, closing.sum(), "counter")
        loans.loc[L.index[closing], "close_date"] = cdates
        loans.loc[L.index[closing], "close_reason"] = reason[closing]
        closed_rows = self._loan_snapshot(loans, me, np.isin(np.arange(len(loans)), L.index[closing]), closed=True)
        # SME working-capital renewal: 75% of matured WC loans roll into a new facility
        ren = L.index[closing & (reason == "MATURED") & (prod == "LN_SME_WC")]
        ren = ren[rng.random(len(ren)) < 0.75]
        if len(ren):
            old = loans.loc[ren]
            new = self._new_loans(len(ren), p, np.array(list(loans.loc[ren, "close_date"])))
            new["cust_idx"], new["cif"], new["branch_code"] = old.cust_idx.values, old.cif.values, old.branch_code.values
            new["product_code"] = "LN_SME_WC"
            new["repayment_method"], new["collateral_type"] = "BULLET", "BDS_HANG_TON_KHO"
            new["approved_amount"] = np.round(old.approved_amount.values * rng.uniform(0.9, 1.25, len(ren)), -8).astype(np.int64)
            new["outstanding"] = new.approved_amount.astype(float)
            new["term_months"] = rng.choice([3, 6, 9, 12], len(ren), p=[.15, .35, .2, .3])
            new["maturity_date"] = [(pd.Timestamp(d) + pd.DateOffset(months=int(t))).date()
                                    for d, t in zip(new.disbursement_date, new.term_months)]
            new["collateral_value"] = old.collateral_value.values
            new["interest_rate"] = np.round(self.lend_rate(p, "LN_SME_WC") + rng.normal(0, .25, len(ren)), 2)
            loans = pd.concat([loans, new], ignore_index=True)
        return loans, closed_rows

    def _loan_snapshot(self, loans: pd.DataFrame, d: date, mask: np.ndarray, closed: bool = False) -> pd.DataFrame:
        rng = self.rng
        s = loans[mask]
        od = pd.to_datetime(s.oldest_due)
        dpd = np.where(od.notna(), (pd.Timestamp(d) - od).dt.days.clip(lower=0).fillna(0), 0).astype(int)
        tech = (dpd == 0) & (rng.random(len(s)) < 0.035) & (not closed)
        dpd = np.where(tech, rng.integers(1, 10, len(s)), dpd)
        grp = np.select([dpd <= 9, dpd <= 90, dpd <= 180, dpd <= 360], [1, 2, 3, 4], 5)
        cic = s.cic_group.values.astype(int)
        final = np.maximum(grp, cic)
        if closed:
            status = s.close_reason.values
            outst = np.zeros(len(s), dtype=np.int64)
            overdue = np.zeros(len(s), dtype=np.int64)
        else:
            status = np.where(dpd >= 10, "OVERDUE", "ACTIVE")
            outst = s.outstanding.values.astype(np.int64)
            overdue = s.overdue.values.astype(np.int64)
        accrued = np.round(s.outstanding.values * s.interest_rate.values / 100 * rng.integers(1, 30, len(s)) / 365)
        return pd.DataFrame({"snapshot_date": d, "_row": s.index, "outstanding_principal": outst,
                             "overdue_principal": overdue, "dpd": dpd, "loan_group": final,
                             "cic_group": np.where(cic > 0, cic, 0), "accrued_interest": accrued.astype(np.int64),
                             "status": status, "_bdate": d})

    # ================================================================== CARDS
    CARD_LIMIT = {"CD_CREDIT_CLASSIC": (1e7, 3e7), "CD_CREDIT_GOLD": (3e7, 8e7), "CD_CREDIT_PLATINUM": (8e7, 3e8)}
    CARD_LAMBDA = {"CD_CREDIT_CLASSIC": 5, "CD_CREDIT_GOLD": 7, "CD_CREDIT_PLATINUM": 9}
    MCC_PROFILE = {  # mcc: (probability, median amount VND, p_ecom, p_international)
        "5411": (.14, 4.5e5, .05, .01), "5499": (.10, 1.2e5, .02, .0), "5812": (.10, 6.5e5, .02, .02),
        "5814": (.12, 9e4, .05, .0), "5541": (.08, 4e5, .0, .0), "4121": (.10, 1.1e5, .9, .0),
        "4511": (.02, 3.2e6, .7, .25), "7011": (.02, 2.5e6, .5, .2), "5311": (.05, 1.2e6, .05, .01),
        "5691": (.05, 9e5, .3, .03), "5732": (.02, 4.5e6, .3, .02), "5999": (.10, 5.5e5, .9, .15),
        "4814": (.04, 2.5e5, .8, .0), "4900": (.03, 7e5, .8, .0), "5912": (.02, 3e5, .1, .0),
        "8062": (.01, 1.5e6, .05, .0), "8220": (.005, 5e6, .4, .02),
    }
    MERCHANT_WORDS = ["MINH ANH", "HOA SEN", "PHU THINH", "AN KHANG", "THANH DAT", "BAO NGOC", "KIM LONG",
                      "HUNG PHAT", "SAO VIET", "NAM PHONG", "TAN LOC", "GIA HUY", "PHUONG NAM", "HAI AU"]
    MCC_PREFIX = {"5411": "SIEU THI", "5499": "CUA HANG TIEN LOI", "5812": "NHA HANG", "5814": "CAFE",
                  "5541": "CAY XANG", "4121": "XE CONG NGHE", "4511": "HANG BAY", "7011": "KHACH SAN",
                  "5311": "TTTM", "5691": "THOI TRANG", "5732": "DIEN MAY", "5999": "SAN TMDT",
                  "4814": "VIEN THONG", "4900": "DIEN LUC/CAP NUOC", "5912": "NHA THUOC", "8062": "BENH VIEN",
                  "8220": "TRUONG"}

    def build_cards(self):
        rng, c, acc = self.rng, self.cust, self.acc
        # ---- debit cards: one per individual main CASA account
        main = acc[acc.is_main & ~acc._is_sme].copy()
        seg = c.segment.values[main.cust_idx]
        intl = rng.random(len(main)) < np.where(np.isin(seg, ["AFFLUENT", "PRIORITY"]), 0.75, 0.3)
        deb = pd.DataFrame({
            "cif": main.cif.values, "product_code": np.where(intl, "CD_DEBIT_INT", "CD_DEBIT_DOM"),
            "account_ref": main.account_no.values, "branch_code": main.branch_code.values,
            "issue_date": main.open_date.values, "close_date": main.close_date.values,
            "credit_limit": 0,
        })
        act = rng.random(len(deb)) < 0.92
        deb["activation_date"] = [d + timedelta(days=int(rng.integers(0, 10))) if a else None for d, a in zip(deb.issue_date, act)]
        deb["_cust_idx"] = main.cust_idx.values
        # ---- credit cards
        ind_pool_all = np.where((c.customer_type.values == "IND") & c.close_date.isna().values & (c._income.values > 9e6))[0]
        pre_pool = ind_pool_all[c.open_date.values[ind_pool_all] <= self.init_date]
        n_init = int(0.19 * len(pre_pool))
        init_idx = rng.choice(pre_pool, n_init, replace=False)
        cc_rows = [self._new_credit_cards(init_idx, np.array([self.init_date - timedelta(days=int(rng.integers(30, 1800)))
                                                              for _ in init_idx]), campaign=False)]
        have = set(init_idx.tolist())
        for p in self.months:
            me = p.end_time.date()
            pool = np.array([i for i in ind_pool_all if c.open_date.values[i] <= me and i not in have])
            if len(pool) == 0:
                continue
            active_ind = ((c.customer_type.values == "IND") & (c.open_date.values <= me)).sum()
            k = int(0.0055 * active_ind * rng.lognormal(0, 0.1))
            camp = EVENTS["card_campaign"][0] <= p <= EVENTS["card_campaign"][1]
            if camp:
                k *= 3
            k = min(k, len(pool))
            who = rng.choice(pool, k, replace=False)
            have.update(who.tolist())
            dates = self.random_dates(p.start_time.date(), me, k, "counter")
            cc_rows.append(self._new_credit_cards(who, dates, camp))
        cc = pd.concat(cc_rows, ignore_index=True)
        cards = pd.concat([deb, cc], ignore_index=True)
        cards["expiry_date"] = [(pd.Timestamp(d) + pd.DateOffset(years=5 if p == "CD_DEBIT_DOM" else 4)).date()
                                for d, p in zip(cards.issue_date, cards.product_code)]
        is_credit = cards.product_code.str.startswith("CD_CREDIT").values
        n = len(cards)
        cards["card_id"] = [f"{'C' if cr else 'D'}{i:09d}" for i, cr in enumerate(is_credit)]
        pan = []
        for pc in cards.product_code:
            last4 = f"{rng.integers(0, 10000):04d}"
            if pc == "CD_DEBIT_DOM":
                pan.append(f"970488******{last4}")
            elif pc == "CD_DEBIT_INT":
                pan.append(f"422151******{last4}")
            else:
                pan.append(f"{rng.choice(['455376', '524394'])}******{last4}")
        cards["masked_pan"] = pan
        # credit-card lifecycle + transactions + loan accounts
        cc_loans, cc_bal, card_txn = self._credit_card_activity(cards[is_credit].copy())
        cards.loc[is_credit, "close_date"] = cards.loc[is_credit, "card_id"].map(self._cc_close).values
        cards["status"] = np.where(cards.close_date.notna(), "CLOSED",
                                   np.where(cards.activation_date.isna(), "INACTIVE", "ACTIVE"))
        cols = ["card_id", "masked_pan", "cif", "product_code", "account_ref", "branch_code", "issue_date",
                "activation_date", "expiry_date", "credit_limit", "status", "close_date"]
        issued = cards[cols].copy()
        issued["status"], issued["close_date"] = "ISSUED", None
        issued["activation_date"] = None
        issued["_bdate"] = [self.init_date if d <= self.init_date else route_date(d) for d in cards.issue_date]
        activated = cards[cards.activation_date.notna()][cols].copy()
        activated["status"], activated["close_date"] = "ACTIVE", None
        activated["_bdate"] = [self.init_date if d <= self.init_date else route_date(d)
                               for d in activated.activation_date]
        closed = cards[cards.close_date.notna()][cols].copy()
        closed["_bdate"] = [route_date(d) for d in closed.close_date]
        card_file = pd.concat([issued, activated, closed], ignore_index=True)
        # activation same day as issue for migrated cards: collapse to one row (latest wins in ETL)
        return card_file, cc_loans, cc_bal, card_txn

    def _new_credit_cards(self, who: np.ndarray, dates: np.ndarray, campaign: bool) -> pd.DataFrame:
        rng, c = self.rng, self.cust
        seg = c.segment.values[who]
        r = rng.random(len(who))
        prod = np.where(seg == "PRIORITY", np.where(r < 0.7, "CD_CREDIT_PLATINUM", "CD_CREDIT_GOLD"),
                        np.where(seg == "AFFLUENT", np.where(r < 0.25, "CD_CREDIT_PLATINUM",
                                                             np.where(r < 0.8, "CD_CREDIT_GOLD", "CD_CREDIT_CLASSIC")),
                                 np.where(r < 0.12, "CD_CREDIT_GOLD", "CD_CREDIT_CLASSIC")))
        lim = np.array([np.round(rng.uniform(*self.CARD_LIMIT[p]), -6) for p in prod])
        p_act = 0.45 if campaign else 0.82
        act = rng.random(len(who)) < p_act
        return pd.DataFrame({
            "cif": c.cif.values[who], "product_code": prod, "account_ref": "", "branch_code": c.home_branch_code.values[who],
            "issue_date": dates, "close_date": None, "credit_limit": lim.astype(np.int64),
            "activation_date": [d + timedelta(days=int(rng.integers(1, 30))) if a else None for d, a in zip(dates, act)],
            "_cust_idx": who, "_campaign": campaign,
        })

    def _credit_card_activity(self, cc: pd.DataFrame):
        rng = self.rng
        n = len(cc)
        cc = cc.reset_index(drop=True)
        cc["loan_id"] = ["LC" + cid[1:] for cid in cc.card_id]
        pay_type = rng.choice(["FULL", "PARTIAL", "REVOLVE"], n, p=[.55, .35, .10])
        usage = rng.beta(2, 2, n) * np.where(cc._campaign.values, 0.6, 1.0)
        bal = np.zeros(n)
        oldest = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
        # migrated cards start with a balance
        act_d = pd.to_datetime(cc.activation_date).values
        pre = (~np.isnat(act_d)) & (act_d <= np.datetime64(self.init_date))
        bal[pre] = np.round(cc.credit_limit.values[pre] * rng.beta(1.5, 4, pre.sum()) * (pay_type[pre] != "FULL") , -3)
        closed_on: dict[str, date] = {}
        close_arr = np.full(n, None, dtype=object)
        snaps, txn_parts = [], []
        snaps.append(pd.DataFrame({"snapshot_date": self.init_date, "loan_id": cc.loan_id.values[pre],
                                   "outstanding_principal": bal[pre].astype(np.int64), "overdue_principal": 0,
                                   "dpd": 0, "loan_group": 1, "cic_group": 0, "accrued_interest": 0,
                                   "status": "ACTIVE", "_bdate": self.init_date}))
        mcc_codes = list(self.MCC_PROFILE)
        mcc_p = np.array([self.MCC_PROFILE[m][0] for m in mcc_codes])
        mcc_p = mcc_p / mcc_p.sum()
        for p in self.months:
            ms, me = p.start_time.date(), p.end_time.date()
            live = (~np.isnat(act_d)) & (act_d <= np.datetime64(me)) & np.array([x is None for x in close_arr])
            idx = np.where(live)[0]
            # ---- payments on previous balance
            od = oldest[idx]
            late = ~np.isnat(od)
            base_miss = np.select([pay_type[idx] == "FULL", pay_type[idx] == "PARTIAL"], [.004, .018], .055)
            dpd0 = np.where(late, (np.datetime64(ms) - od).astype("timedelta64[D]").astype(float), 0)
            cont = np.select([dpd0 <= 30, dpd0 <= 90, dpd0 <= 180], [.55, .7, .85], .9)
            miss = (bal[idx] > 0) & (rng.random(len(idx)) < np.where(late, cont, base_miss))
            frac = np.select([pay_type[idx] == "FULL", pay_type[idx] == "PARTIAL"], [1.0, rng.uniform(.2, .6, len(idx))], .05)
            payment = np.where(miss, 0, np.round(bal[idx] * frac, -3))
            cured = late & ~miss
            oldest[idx[cured]] = np.datetime64("NaT")
            newly = miss & ~late
            oldest[idx[newly]] = np.datetime64(date(p.year, p.month, 15))
            interest = np.where(pay_type[idx] != "FULL", np.round((bal[idx] - payment) * 0.28 / 12, -3), 0)
            bal[idx] = bal[idx] - payment + interest
            # ---- spending (blocked while seriously overdue)
            blocked = ~np.isnat(oldest[idx]) & ((np.datetime64(me) - oldest[idx]).astype("timedelta64[D]").astype(float) > 30)
            season = 1.15 if p.month == 12 else (1.3 if p.month == pd.Period(cal.TET_DAYS.get(p.year, date(p.year, 2, 1)), "M").month else 1.0)
            lam = np.array([self.CARD_LAMBDA[x] for x in cc.product_code.values[idx]]) * usage[idx] * 2 * season
            lam = np.where(blocked, 0, lam)
            k = rng.poisson(lam)
            rows = np.repeat(idx, k)
            if len(rows):
                mcc = rng.choice(mcc_codes, len(rows), p=mcc_p)
                med = np.array([self.MCC_PROFILE[m][1] for m in mcc])
                amt = np.maximum(np.round(med * rng.lognormal(0, 0.7, len(rows)), -3), 10_000)
                e = pd.DataFrame({"_i": rows, "mcc": mcc, "amount": amt})
                e["_cum"] = e.groupby("_i").amount.cumsum()
                avail = cc.credit_limit.values[rows] - bal[rows]
                e["auth_status"] = np.where((e._cum > avail) | (rng.random(len(e)) < 0.015), "DECLINED", "APPROVED")
                spent = e[e.auth_status == "APPROVED"].groupby("_i").amount.sum()
                bal[spent.index.values] += spent.values
                w, days = cal.day_weights(ms, "digital")
                d_idx = rng.choice(len(days), len(e), p=w)
                # no spend before activation
                a_off = np.array([(pd.Timestamp(x).date() - ms).days for x in act_d[rows]])
                d_idx = np.maximum(d_idx, np.clip(a_off, 0, len(days) - 1))
                e["txn_datetime"] = (np.datetime64(ms) + d_idx.astype("timedelta64[D]") +
                                     self._digital_seconds(len(e)).astype("timedelta64[s]"))
                e["card_id"] = cc.card_id.values[rows]
                e["is_ecommerce"] = (rng.random(len(e)) < np.array([self.MCC_PROFILE[m][2] for m in mcc])).astype(int)
                e["is_international"] = (rng.random(len(e)) < np.array([self.MCC_PROFILE[m][3] for m in mcc])).astype(int)
                e["merchant_name"] = [f"{self.MCC_PREFIX[m]} {rng.choice(self.MERCHANT_WORDS)}" for m in mcc]
                txn_parts.append(e.drop(columns=["_i", "_cum"]))
            # ---- attrition (only with zero balance) and write-off
            dpd = np.where(~np.isnat(oldest[idx]), (np.datetime64(me) - oldest[idx]).astype("timedelta64[D]").astype(float), 0)
            status = np.where(dpd >= 10, "OVERDUE", "ACTIVE").astype(object)
            close_now = (bal[idx] <= 0) & (rng.random(len(idx)) < 0.006)
            if p.month in (3, 6, 9, 12):
                wo = (dpd > 180) & (rng.random(len(idx)) < 0.7)
                status[wo] = "WRITTEN_OFF"
                close_now |= wo
            status[close_now & (status != "WRITTEN_OFF")] = "CLOSED"
            for j in idx[close_now]:
                close_arr[j] = self.random_dates(ms, me, 1, "digital")[0]
            grp = np.select([dpd <= 9, dpd <= 90, dpd <= 180, dpd <= 360], [1, 2, 3, 4], 5)
            out = np.where(close_now, 0, bal[idx]).astype(np.int64)
            snaps.append(pd.DataFrame({"snapshot_date": me, "loan_id": cc.loan_id.values[idx],
                                       "outstanding_principal": out,
                                       "overdue_principal": np.where(dpd >= 10, np.minimum(out, np.round(out * 0.1, -3)), 0).astype(np.int64),
                                       "dpd": dpd.astype(int), "loan_group": grp, "cic_group": 0,
                                       "accrued_interest": np.round(out * 0.28 / 365 * 10).astype(np.int64),
                                       "status": status, "_bdate": me}))
            bal[idx[close_now]] = 0
        self._cc_close = dict(zip(cc.card_id, close_arr))
        loans = pd.DataFrame({
            "loan_id": cc.loan_id, "cif": cc.cif, "product_code": "LN_CREDITCARD", "branch_code": cc.branch_code,
            "disbursement_date": cc.issue_date, "maturity_date": cc.issue_date.map(lambda d: (pd.Timestamp(d) + pd.DateOffset(years=4)).date()),
            "term_months": "", "approved_amount": cc.credit_limit, "interest_rate": 28.0, "repayment_method": "REVOLVING",
            "collateral_type": "", "collateral_value": 0, "close_date": None, "close_reason": "",
        })
        loans["_bdate"] = [self.init_date if d <= self.init_date else route_date(d) for d in loans.disbursement_date]
        cl = loans.copy()
        cl["close_date"] = close_arr
        cl = cl[cl.close_date.notna()]
        cl["close_reason"] = "CLOSED"
        cl["_bdate"] = [route_date(d) for d in cl.close_date]
        txn = pd.concat(txn_parts, ignore_index=True).sort_values("txn_datetime", kind="stable").reset_index(drop=True)
        txn["business_date"] = txn.txn_datetime.dt.date.map(cal.next_business_day)
        txn["card_txn_id"] = "CT" + pd.to_datetime(txn.business_date).dt.strftime("%y%m%d") + \
            (txn.groupby("business_date").cumcount() + 1).map(lambda x: f"{x:06d}")
        txn["_bdate"] = txn.business_date
        txn = txn[["card_txn_id", "card_id", "txn_datetime", "business_date", "mcc", "merchant_name", "amount",
                   "is_ecommerce", "is_international", "auth_status", "_bdate"]]
        txn["amount"] = txn.amount.astype(np.int64)
        return pd.concat([loans, cl], ignore_index=True), pd.concat(snaps, ignore_index=True), txn

    # ================================================================== ATM / BRANCH OPS / COMPLAINTS
    def build_atm_daily(self, txn: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        atms = self.atm_list()
        t = txn[txn.txn_type == "ATM_WD"]
        agg = t.groupby([t.atm_id, t.txn_datetime.dt.date]).amount.agg(["count", "sum"])
        days = [d.date() for d in pd.date_range(self.cfg.sim.start_date, self.cfg.sim.end_date)]
        grid = pd.MultiIndex.from_product([atms.atm_id, days], names=["atm_id", "report_date"])
        df = pd.DataFrame(index=grid).join(agg.rename_axis(["atm_id", "report_date"])).fillna(0).reset_index()
        df["branch_code"] = df.atm_id.str[3:6]
        size = df.branch_code.map(dict(zip(self.branches.branch_code, self.branches.size_weight))).values
        tet = np.array([cal.pre_tet_factor(d) for d in df.report_date])
        lam_off = (df["count"].values * 0.65 + 4 * size) * tet
        df["offus_wd_count"] = rng.poisson(lam_off)
        df["offus_wd_amount"] = np.round(df.offus_wd_count * 1.6e6 * rng.lognormal(0, 0.15, len(df)), -5)
        down = rng.exponential(6, len(df))
        inc = rng.random(len(df)) < 0.03
        down[inc] += rng.uniform(60, 300, inc.sum())
        lo, hi = EVENTS["atm_window"]
        ev = df.branch_code.isin(EVENTS["atm_branches"]).values & (df.report_date >= lo).values & (df.report_date <= hi).values
        ev_inc = ev & (rng.random(len(df)) < 0.35)
        down[ev_inc] += rng.uniform(120, 720, ev_inc.sum())
        cash_out = rng.random(len(df)) < np.where(tet > 1.5, 0.22, 0.01)
        down[cash_out] += rng.uniform(90, 480, cash_out.sum())
        df["uptime_minutes"] = np.clip(np.round(1440 - down), 0, 1440).astype(int)
        df["incident_count"] = (inc | ev_inc).astype(int) + (rng.random(len(df)) < 0.02).astype(int)
        df["cash_out_flag"] = cash_out.astype(int)
        df = df.rename(columns={"count": "onus_wd_count", "sum": "onus_wd_amount"})
        df["onus_wd_count"] = df.onus_wd_count.astype(int)
        df["onus_wd_amount"] = df.onus_wd_amount.astype(np.int64)
        df["offus_wd_amount"] = df.offus_wd_amount.astype(np.int64)
        df["_bdate"] = df.report_date.map(cal.next_business_day)
        df = df.rename(columns={"report_date": "business_date"})
        return df[["business_date", "atm_id", "branch_code", "onus_wd_count", "onus_wd_amount", "offus_wd_count",
                   "offus_wd_amount", "uptime_minutes", "incident_count", "cash_out_flag", "_bdate"]]

    def build_branch_ops(self, txn: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        t = txn[txn.channel_code == "COUNTER"]
        cnt = t.groupby(["branch_code", "business_date"]).size()
        bdays = cal.business_days(self.cfg.sim.start_date, self.cfg.sim.end_date)
        grid = pd.MultiIndex.from_product([self.branches.branch_code, bdays], names=["branch_code", "business_date"])
        df = pd.DataFrame(index=grid).join(cnt.rename("counter_txn_count")).fillna(0).reset_index()
        size = df.branch_code.map(dict(zip(self.branches.branch_code, self.branches.size_weight))).values
        tet = np.array([cal.pre_tet_factor(d) for d in df.business_date])
        df["service_request_count"] = rng.poisson(size * 9 * np.where(tet > 1, tet ** 0.5, 1))
        df["tellers"] = np.maximum(2, np.round(size * 3.5)).astype(int)
        load = (df.counter_txn_count + df.service_request_count) / (df.tellers * 38)
        monday = np.array([d.weekday() == 0 for d in df.business_date])
        payday = np.array([5 <= d.day <= 10 for d in df.business_date])
        wait = (3 + 14 * load ** 2) * rng.lognormal(0, 0.15, len(df)) + monday * 1.5 + payday * 1.0
        wait *= np.where(tet > 1, 1.3, 1.0)
        df["avg_wait_minutes"] = np.round(wait, 1)
        df["avg_service_minutes"] = np.round(6.5 + 1.5 * rng.random(len(df)), 1)
        df["pct_wait_under_15m"] = np.round(1 - np.exp(-15 / np.maximum(wait, 0.5)), 3)
        df["counter_txn_count"] = df.counter_txn_count.astype(int)
        df["_bdate"] = df.business_date
        return df[["business_date", "branch_code", "tellers", "counter_txn_count", "service_request_count",
                   "avg_wait_minutes", "avg_service_minutes", "pct_wait_under_15m", "_bdate"]]

    COMPLAINT_TYPES = {  # type: (probability, SLA working days)
        "ATM_KHONG_NHAN_TIEN": (.14, 7), "CHUYEN_TIEN_LOI": (.18, 5), "TRA_SOAT_THE": (.12, 45),
        "PHI_DICH_VU": (.10, 5), "THAI_DO_PHUC_VU": (.08, 3), "LOI_UNG_DUNG": (.16, 2),
        "THE_BI_KHOA": (.10, 1), "KHOAN_VAY": (.07, 7), "KHAC": (.05, 5),
    }

    def build_complaints(self) -> pd.DataFrame:
        rng, c = self.rng, self.cust
        hol = np.array(sorted(cal.holidays()), dtype="datetime64[D]")
        types = list(self.COMPLAINT_TYPES)
        tp = np.array([self.COMPLAINT_TYPES[t][0] for t in types])
        rows = []
        open64 = pd.to_datetime(c.open_date).values
        close64 = pd.to_datetime(c.close_date).values
        for d in pd.date_range(self.cfg.sim.start_date, self.cfg.sim.end_date):
            d64 = d.to_datetime64()
            d = d.date()
            active = (open64 <= d64) & (np.isnat(close64) | (close64 > d64))
            lam = 4.0 * active.sum() / 12000 * (0.6 if d.weekday() >= 5 else 1.0)
            extra = {}
            lo, hi = EVENTS["atm_window"]
            if lo <= d <= hi:
                extra["ATM_KHONG_NHAN_TIEN"] = 3.0
            lo, hi = EVENTS["app_window"]
            if lo <= d <= hi:
                extra["LOI_UNG_DUNG"] = 12.0
            k = rng.poisson(lam)
            ty = list(rng.choice(types, k, p=tp / tp.sum()))
            for t_, l_ in extra.items():
                ty += [t_] * rng.poisson(l_)
            if not ty:
                continue
            pool = np.where(active)[0]
            who = rng.choice(pool, len(ty))
            if d >= EVENTS["atm_window"][0] and d <= EVENTS["atm_window"][1]:
                atm_ty = np.array(ty) == "ATM_KHONG_NHAN_TIEN"
                sg = np.where(np.isin(c.home_branch_code.values, list(EVENTS["atm_branches"])))[0]
                who[atm_ty] = rng.choice(np.intersect1d(sg, pool), atm_ty.sum())
            rows.append(pd.DataFrame({"received_date": d, "complaint_type": ty, "cust_idx": who}))
        df = pd.concat(rows, ignore_index=True)
        n = len(df)
        df["cif"] = c.cif.values[df.cust_idx]
        df["branch_code"] = c.home_branch_code.values[df.cust_idx]
        df["channel"] = rng.choice(["HOTLINE", "QUAY", "APP", "EMAIL"], n, p=[.45, .25, .2, .1])
        df["sla_days"] = df.complaint_type.map(lambda t: self.COMPLAINT_TYPES[t][1])
        sec = rng.integers(7 * 3600, 21 * 3600, n)
        df["received_datetime"] = pd.to_datetime(df.received_date) + pd.to_timedelta(sec, unit="s")
        ratio = rng.lognormal(np.log(0.55), 0.35, n)
        breach = rng.random(n) < 0.06
        ratio[breach] = rng.uniform(1.2, 3.0, breach.sum())
        wdays = np.maximum(np.ceil(ratio * df.sla_days.values), 0).astype(int)
        start = df.received_date.values.astype("datetime64[D]")
        res_day = np.busday_offset(np.busday_offset(start, 0, roll="forward", holidays=hol), wdays, holidays=hol)
        res = pd.to_datetime(res_day) + pd.to_timedelta(rng.integers(8 * 3600, 18 * 3600, n), unit="s")
        open_ = res.date > np.array([self.cfg.sim.end_date] * n)
        df["resolved_datetime"] = np.where(open_, pd.NaT, res)
        df["status"] = np.where(open_, "OPEN", "CLOSED")
        df["is_valid"] = np.where(open_, "", np.where(rng.random(n) < 0.62, "Y", "N"))
        df = df.sort_values("received_datetime").reset_index(drop=True)
        df["complaint_id"] = "KN" + df.received_datetime.dt.strftime("%y%m%d") + \
            (df.groupby("received_date").cumcount() + 1).map(lambda x: f"{x:04d}")
        rec = df.copy()
        rec["resolved_datetime"], rec["status"], rec["is_valid"] = pd.NaT, "OPEN", ""
        rec["_bdate"] = rec.received_date.map(cal.next_business_day)
        done = df[df.status == "CLOSED"].copy()
        done["_bdate"] = pd.to_datetime(done.resolved_datetime).dt.date.map(cal.next_business_day)
        cols = ["complaint_id", "cif", "branch_code", "received_datetime", "channel", "complaint_type", "sla_days",
                "resolved_datetime", "status", "is_valid", "_bdate"]
        return pd.concat([rec[cols], done[cols]], ignore_index=True)

    # ================================================================== GL
    def build_gl(self, casa_acc, casa_bal, tdf, td_bal, loan_f, loan_bal) -> pd.DataFrame:
        acc_br = casa_acc.drop_duplicates("account_no").set_index("account_no").branch_code
        cb = casa_bal.assign(branch_code=casa_bal.account_no.map(acc_br), gl_account="4211")
        cb = cb.groupby(["snapshot_date", "branch_code", "gl_account"]).balance.sum()
        td_meta = tdf.drop_duplicates("td_id").set_index("td_id")
        tb = td_bal.assign(branch_code=td_bal.td_id.map(td_meta.branch_code),
                           gl_account=np.where(td_bal.td_id.map(td_meta.product_code) == "TD_SME", "4212", "4232"))
        tb = tb.groupby(["snapshot_date", "branch_code", "gl_account"]).principal.sum()
        lm = loan_f.drop_duplicates("loan_id").set_index("loan_id")
        lb = loan_bal[loan_bal.status.isin(["ACTIVE", "OVERDUE"])].copy()
        term = pd.to_numeric(lb.loan_id.map(lm.term_months), errors="coerce").fillna(0)
        bucket = np.where(term <= 12, "211", np.where(term <= 60, "212", "213"))
        lb["gl_account"] = bucket + lb.loan_group.astype(str)
        lb["branch_code"] = lb.loan_id.map(lm.branch_code)
        lb = lb.groupby(["snapshot_date", "branch_code", "gl_account"]).outstanding_principal.sum()
        gl = pd.concat([cb, tb, lb]).rename("balance").reset_index()
        gl["balance"] = gl.balance.astype(np.int64)
        # --- known reconciling items (injected on purpose, documented in docs/02_calibration.md)
        def adj(d, br, acct, delta):
            m = (gl.snapshot_date == d) & (gl.branch_code == br) & (gl.gl_account == acct)
            gl.loc[m, "balance"] += delta
        adj(date(2025, 6, 30), "130", "4211", 1_850_000_000)       # suspense item posted after cut-off
        adj(date(2025, 12, 31), "200", "2121", -2_400_000_000)     # loan classified to group 2 in GL late
        adj(date(2025, 12, 31), "200", "2122", 2_400_000_000)
        adj(date(2026, 3, 31), "400", "4232", 1_250_000)           # rounding difference
        gl["_bdate"] = gl.snapshot_date
        return gl[["snapshot_date", "branch_code", "gl_account", "balance", "_bdate"]]

    # ================================================================== RUN
    def run(self) -> Frames:
        log.info("branches & customers")
        branch = self.build_branches()
        customer = self.build_customers()
        log.info("CASA accounts & transactions")
        casa_acc, casa_bal, txn = self.build_casa()
        casa0 = casa_bal[casa_bal.snapshot_date == self.init_date].balance.sum()
        log.info("term deposits")
        tdf, td_bal = self.build_term_deposits(casa0)
        td0 = td_bal[td_bal.snapshot_date == self.init_date].principal.sum()
        log.info("loans")
        loan_f, loan_bal = self.build_loans(casa0 + td0)
        log.info("cards")
        card_f, cc_loans, cc_bal, card_txn = self.build_cards()
        loan_f = pd.concat([loan_f, cc_loans], ignore_index=True)
        loan_bal = pd.concat([loan_bal, cc_bal], ignore_index=True)
        log.info("ATM, branch operations, complaints")
        atm = self.build_atm_daily(txn)
        ops = self.build_branch_ops(txn)
        comp = self.build_complaints()
        log.info("general ledger")
        gl = self.build_gl(casa_acc, casa_bal, tdf, td_bal, loan_f, loan_bal)
        return Frames(branch, customer, casa_acc, casa_bal, txn, tdf, td_bal, loan_f, loan_bal, card_f, card_txn,
                      atm, ops, comp, gl)
