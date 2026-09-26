"""pack_data -> unpack_data must rebuild byte-identical CSV extracts."""
import filecmp
import subprocess
import sys

from python.common.config import ROOT


def test_roundtrip(tmp_path):
    raw, pq, raw2 = tmp_path / "raw", tmp_path / "pq", tmp_path / "raw2"
    py = sys.executable
    subprocess.run([py, "-m", "python.generator.run_generator", "--customers", "300", "--sme", "15",
                    "--out", str(raw)], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([py, "-m", "python.tools.pack_data", "--raw", str(raw), "--out", str(pq)],
                   cwd=ROOT, check=True, capture_output=True)
    subprocess.run([py, "-m", "python.tools.unpack_data", "--src", str(pq), "--raw", str(raw2)],
                   cwd=ROOT, check=True, capture_output=True)
    files = [p.relative_to(raw) for p in raw.rglob("*.csv")]
    assert files
    for f in files:
        assert filecmp.cmp(raw / f, raw2 / f, shallow=False), f
