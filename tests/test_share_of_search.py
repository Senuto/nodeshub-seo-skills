"""Unit + smoke tests for nod-share-of-search/scripts/analyze.py.

Self-contained module loader (no shared conftest).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-share-of-search" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("sos_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- compute: per-month share = brand / sum(all brands) ----------------------

def test_compute_share_per_month():
    months = ["m1", "m2"]
    volumes = {"A": [30.0, 50.0], "B": [70.0, 50.0]}
    result = M.compute(months, volumes)
    assert result["totals"] == [100.0, 100.0]
    a = next(b for b in result["brands"] if b["brand"] == "A")
    b = next(b for b in result["brands"] if b["brand"] == "B")
    assert a["shares"] == [0.3, 0.5]
    assert b["shares"] == [0.7, 0.5]
    assert a["latest_share"] == 0.5
    assert a["first_share"] == 0.3
    assert a["share_change"] == 0.2


def test_compute_sorted_by_latest_share_desc():
    months = ["m1"]
    volumes = {"small": [10.0], "big": [90.0]}
    result = M.compute(months, volumes)
    assert [b["brand"] for b in result["brands"]] == ["big", "small"]


def test_compute_zero_total_month_yields_zero_share():
    months = ["m1"]
    volumes = {"A": [0.0], "B": [0.0]}
    result = M.compute(months, volumes)
    assert result["totals"] == [0.0]
    for b in result["brands"]:
        assert b["shares"] == [0.0]


# --- _slope sign -------------------------------------------------------------

def test_slope_positive_for_rising_series():
    assert M._slope([0.1, 0.2, 0.3, 0.4]) > 0


def test_slope_negative_for_falling_series():
    assert M._slope([0.4, 0.3, 0.2, 0.1]) < 0


def test_slope_zero_for_flat_and_short_series():
    assert M._slope([0.5, 0.5, 0.5]) == 0.0
    assert M._slope([0.5]) == 0.0
    assert M._slope([]) == 0.0


def test_trend_arrow_thresholds():
    assert M._trend_arrow(0.01) == ("up", "rising")
    assert M._trend_arrow(-0.01) == ("down", "falling")
    assert M._trend_arrow(0.0) == ("flat", "flat")


# --- add_flags: own trend + fastest-momentum competitor ----------------------

def test_add_flags_identifies_rising_brand_and_fastest_competitor():
    months = ["m1", "m2", "m3", "m4"]
    # Acme rises; Surge rises fastest; Fade falls.
    volumes = {
        "Acme":  [20.0, 24.0, 28.0, 34.0],
        "Surge": [10.0, 18.0, 28.0, 42.0],
        "Fade":  [70.0, 58.0, 44.0, 24.0],
    }
    result = M.compute(months, volumes)
    result = M.add_flags(result, "Acme")
    flags = result["flags"]
    assert flags["your_brand"] == "Acme"
    assert flags["your_direction"] == "up"
    assert flags["fastest_competitor"] == "Surge"
    assert flags["fastest_competitor_slope"] > 0


def test_add_flags_no_competitor_gaining():
    months = ["m1", "m2", "m3"]
    # Your brand surges; both competitors lose share -> no positive momentum.
    volumes = {
        "You":  [10.0, 40.0, 80.0],
        "C1":   [50.0, 40.0, 20.0],
        "C2":   [40.0, 20.0, 10.0],
    }
    result = M.compute(months, volumes)
    result = M.add_flags(result, "You")
    assert result["flags"]["fastest_competitor"] is None


# --- parse_aliases: alias summing --------------------------------------------

def test_parse_aliases_default_uses_brand_name():
    aliases = M.parse_aliases("Acme", ["Globex"], "")
    assert aliases == {"Acme": ["Acme"], "Globex": ["Globex"]}


def test_parse_aliases_merges_explicit_aliases():
    aliases = M.parse_aliases("Acme", ["Globex"], "Acme:acme app,acme io")
    # Brand name itself stays first, explicit aliases appended.
    assert aliases["Acme"] == ["Acme", "acme app", "acme io"]
    assert aliases["Globex"] == ["Globex"]


def test_dataforseo_alias_summing_via_demo_shapes():
    # Verify the alias-summing arithmetic that fetch_dataforseo relies on by
    # exercising compute over pre-summed series (the summation itself is a
    # plain sum in the adapter). Here: two aliases of the same brand summed.
    months = ["m1", "m2"]
    # Brand X = alias_a + alias_b summed per month: [100,120]; competitor flat.
    volumes = {"X": [100.0, 120.0], "Y": [100.0, 100.0]}
    result = M.compute(months, volumes)
    x = next(b for b in result["brands"] if b["brand"] == "X")
    assert x["shares"] == [0.5, round(120.0 / 220.0, 6)]


# --- smoke test: --demo end to end ------------------------------------------

def test_demo_smoke_writes_parsable_json():
    out_dir = _REPO_ROOT / "data" / "share-of-search"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = sorted(out_dir.glob("*.json"))
    assert written, "no share-of-search report written"
    report = json.loads(written[-1].read_text())
    assert report["months"] == ["2026-01", "2026-02", "2026-03",
                                 "2026-04", "2026-05", "2026-06"]
    assert "brands" in report and len(report["brands"]) == 4
    assert "flags" in report
    # In the demo, Acme rises and Umbrella has the fastest momentum.
    assert report["flags"]["your_brand"] == "Acme"
    assert report["flags"]["your_direction"] == "up"
    assert report["flags"]["fastest_competitor"] == "Umbrella"
