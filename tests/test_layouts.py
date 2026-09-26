"""Staging DDL must match the file layouts used by the generator and the loader."""
import re

from python.common.config import ROOT
from python.common.layouts import LAYOUTS


def test_stg_ddl_matches_layouts():
    ddl = (ROOT / "sql" / "01_staging" / "01_stg_tables.sql").read_text(encoding="utf-8")
    for entity, cols in LAYOUTS.items():
        block = re.search(rf"CREATE UNLOGGED TABLE stg\.{entity.lower()} \((.*?)\);", ddl, re.S)
        assert block, f"missing stg.{entity.lower()}"
        ddl_cols = [l.split()[0] for l in block.group(1).strip().splitlines() if not l.strip().startswith("_")]
        assert ddl_cols == cols, entity
