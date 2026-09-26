"""Small end-to-end checks on the simulator (runs in ~30 s)."""
import numpy as np
import pandas as pd
import pytest

from python.common.config import load_config
from python.generator.simulate import Simulator


@pytest.fixture(scope="module")
def frames():
    cfg = load_config()
    cfg.sim.n_individuals, cfg.sim.n_sme = 800, 40
    return Simulator(cfg).run()


def test_casa_roll_forward(frames):
    """opening balance + credits - debits = closing balance, for every account and month."""
    bal = frames.casa_balance.copy()
    bal["m"] = pd.to_datetime(bal.snapshot_date).dt.to_period("M")
    tx = frames.txn.copy()
    tx["signed"] = np.where(tx.dr_cr == "C", tx.amount, -tx.amount)
    tx["m"] = pd.to_datetime(tx.txn_datetime).dt.to_period("M")
    flows = tx.groupby(["account_no", "m"]).signed.sum()
    b = bal.set_index(["account_no", "m"]).balance.sort_index()
    prev = b.groupby(level=0).shift(1).fillna(0)
    diff = (b - prev - flows.reindex(b.index).fillna(0))
    diff = diff[diff.index.get_level_values(1) >= pd.Period("2024-01", "M")]
    assert (diff != 0).sum() == 0


def test_no_negative_balances(frames):
    assert (frames.casa_balance.balance >= 0).all()


def test_loan_groups_follow_dpd(frames):
    lb = frames.loan_balance[frames.loan_balance.status.isin(["ACTIVE", "OVERDUE"])]
    dpd_group = np.select([lb.dpd <= 9, lb.dpd <= 90, lb.dpd <= 180, lb.dpd <= 360], [1, 2, 3, 4], 5)
    assert (lb.loan_group >= dpd_group).all()


def test_customers_unique_and_ids_formatted(frames):
    c = frames.customer
    init = c[c.record_action.isin(["INIT", "NEW"])]
    assert init.cif.is_unique
    ind = init[init.customer_type == "IND"]
    assert ind.id_number.str.fullmatch(r"\d{12}").all()
