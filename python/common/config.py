"""Project configuration: paths, simulation parameters, DB connection."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass
class SimConfig:
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2026, 8, 31)
    eod_start_date: date = date(2026, 8, 1)   # from this date files are emitted daily (EOD mode)
    random_seed: int = 20260925
    n_individuals: int = 12000
    n_sme: int = 500


@dataclass
class Paths:
    raw: Path = ROOT / "data" / "raw"
    reference: Path = ROOT / "data" / "reference"
    excel: Path = ROOT / "excel"
    logs: Path = ROOT / "logs"


@dataclass
class Config:
    bank_code: str = "DLB"
    sim: SimConfig = field(default_factory=SimConfig)
    paths: Paths = field(default_factory=Paths)

    @property
    def pg_dsn(self) -> str:
        _load_dotenv()
        return (
            f"host={os.getenv('PG_HOST', 'localhost')} "
            f"port={os.getenv('PG_PORT', '5432')} "
            f"dbname={os.getenv('PG_DATABASE', 'dlb_dwh')} "
            f"user={os.getenv('PG_USER', 'postgres')} "
            f"password={os.getenv('PG_PASSWORD', '')}"
        )


def load_config(path: str | Path | None = None) -> Config:
    cfg = Config()
    path = Path(path) if path else ROOT / "config" / "config.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sim = data.get("simulation", {})
        for k, v in sim.items():
            if hasattr(cfg.sim, k):
                setattr(cfg.sim, k, v)
        for k, v in (data.get("paths") or {}).items():
            if hasattr(cfg.paths, k):
                setattr(cfg.paths, k, (ROOT / v) if not Path(v).is_absolute() else Path(v))
    return cfg
