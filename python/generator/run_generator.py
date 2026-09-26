"""Generate the simulated core-banking extracts.

Usage (from the repository root):
    python -m python.generator.run_generator                 # default config
    python -m python.generator.run_generator --customers 5000 # smaller, faster run
"""
from __future__ import annotations

import argparse
import logging
import shutil
import time
from pathlib import Path

from python.common.config import load_config
from python.generator.simulate import Simulator
from python.generator.writer import write_all


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="path to config.yaml (default config/config.yaml)")
    ap.add_argument("--out", default=None, help="output folder (default data/raw)")
    ap.add_argument("--customers", type=int, default=None, help="number of individual customers")
    ap.add_argument("--sme", type=int, default=None, help="number of SME customers")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--clean", action="store_true", help="delete the output folder first")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    cfg = load_config(a.config)
    if a.customers:
        cfg.sim.n_individuals = a.customers
    if a.sme:
        cfg.sim.n_sme = a.sme
    if a.seed:
        cfg.sim.random_seed = a.seed
    out = Path(a.out) if a.out else cfg.paths.raw
    if a.clean and out.exists():
        for p in ("history", "eod"):
            shutil.rmtree(out / p, ignore_errors=True)
    t0 = time.time()
    frames = Simulator(cfg).run()
    meta = write_all(frames, cfg, out)
    logging.info("done in %.0fs -> %s", time.time() - t0, out)
    logging.info("injected defects: %s", meta["injected_defects"])


if __name__ == "__main__":
    main()
