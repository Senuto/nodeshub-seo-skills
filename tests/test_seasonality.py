"""Unit + smoke tests for nod-seasonality/scripts/analyze.py.

Self-contained module loader (no shared conftest) — other agents are writing
sibling files in tests/ concurrently, so we avoid any shared imports.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-seasonality" / "scripts" / "analyze.py"


def _load():
    """Load analyze.py as an isolated module (execution guarded by __main__)."""
    spec = importlib.util.spec_from_file_location("seasonality_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- build_site_curve --------------------------------------------------------

def test_build_site_curve_normalizes_to_mean_100():
    # Single keyword, all volume in Jan. Mean month = total/12, Jan index huge.
    kv = {"kw": [120.0] + [0.0] * 11}
    raw, index = M.build_site_curve(kv)
    assert raw[0] == 120.0
    # mean_month = 120/12 = 10 -> Jan index = 120/10*100 = 1200
    assert index[0] == 1200.0
    assert index[1:] == [0.0] * 11
    # The index average is always 100 by construction.
    assert round(sum(index) / 12.0, 1) == 100.0


def test_build_site_curve_is_volume_weighted_sum():
    # Two keywords; site monthly total is the plain sum (already weighted by
    # each keyword's absolute volume).
    kv = {
        "big": [100.0, 200.0] + [0.0] * 10,
        "small": [10.0, 0.0] + [0.0] * 10,
    }
    raw, _ = M.build_site_curve(kv)
    assert raw[0] == 110.0
    assert raw[1] == 200.0


def test_build_site_curve_flat_when_no_demand():
    kv = {"kw": [0.0] * 12}
    raw, index = M.build_site_curve(kv)
    assert raw == [0.0] * 12
    assert index == [100.0] * 12


# --- find_peaks_troughs ------------------------------------------------------

def test_find_peaks_troughs_basic():
    # Clear single peak in Jul (index 6), trough in Jan (index 0).
    index = [10.0, 20.0, 40.0, 80.0, 120.0, 160.0, 200.0,
             150.0, 90.0, 50.0, 25.0, 15.0]
    pt = M.find_peaks_troughs(index)
    assert pt["peak_months"] == ["Jul"]
    assert pt["trough_months"] == ["Jan"]
    assert pt["peak_index"] == 200.0
    assert pt["trough_index"] == 10.0
    assert pt["peak_trough_ratio"] == 20.0
    assert pt["_peak_indices"] == [6]
    assert pt["_trough_indices"] == [0]


def test_find_peaks_troughs_ties_within_one_point():
    # Two months within 1.0 of the max both count as peaks.
    index = [100.0, 100.5, 50.0, 50.0, 50.0, 50.0,
             50.0, 50.0, 50.0, 50.0, 50.0, 50.0]
    pt = M.find_peaks_troughs(index)
    assert set(pt["_peak_indices"]) == {0, 1}
    assert pt["peak_months"] == ["Jan", "Feb"]


def test_spikiness_labels():
    assert M._spikiness_label(5.0) == "very spiky"
    assert M._spikiness_label(2.5) == "spiky"
    assert M._spikiness_label(1.5) == "moderate"
    assert M._spikiness_label(1.1) == "flat"
    assert M._spikiness_label(None) == "unknown"


# --- publishing_calendar (lead-weeks subtraction) ----------------------------

def test_publishing_calendar_subtracts_lead_months():
    # lead_weeks=6 -> round(6/4.345)=1 month. Peak Jul (6) -> publish Jun (5).
    cal = M.publishing_calendar([6], lead_weeks=6)
    assert len(cal) == 1
    assert cal[0]["publish_month"] == "Jun"
    assert cal[0]["pays_off_month"] == "Jul"
    assert cal[0]["lead_months"] == 1


def test_publishing_calendar_wraps_around_year():
    # lead_weeks=8 -> round(8/4.345)=2 months. Peak Jan (0) -> publish Nov (10).
    cal = M.publishing_calendar([0], lead_weeks=8)
    assert cal[0]["publish_month"] == "Nov"
    assert cal[0]["lead_months"] == 2


def test_publishing_calendar_minimum_one_month():
    # Tiny lead still yields at least one month of lead time.
    cal = M.publishing_calendar([5], lead_weeks=1)
    assert cal[0]["lead_months"] == 1
    # Peak index 5 = Jun; publish one month earlier = May.
    assert cal[0]["publish_month"] == "May"


# --- find_diversification (counter-seasonal selection) -----------------------

def test_find_diversification_picks_opposite_season():
    # Site peak in Jul (6). A winter keyword (peak Jan=0) is 6 months away.
    kv = {
        "summer kw": [0.0] * 5 + [100.0] + [0.0] * 6,   # peak Jun (5)
        "winter kw": [100.0] + [0.0] * 11,              # peak Jan (0)
    }
    rows = M.find_diversification(kv, peak_indices=[6])
    kws = [r["keyword"] for r in rows]
    assert "winter kw" in kws
    # summer kw peaks 1 month from site peak (<4) -> excluded.
    assert "summer kw" not in kws
    winter = next(r for r in rows if r["keyword"] == "winter kw")
    assert winter["peak_month"] == "Jan"
    assert winter["months_from_site_peak"] == 6
    assert winter["annual_volume"] == 100


def test_find_diversification_sorted_by_distance_then_volume():
    # Two valley-fillers: one further from peak, one closer-but-bigger.
    kv = {
        "far": [50.0] + [0.0] * 11,            # peak Jan(0), 6 from Jul
        "near_big": [0.0] * 9 + [500.0, 0.0, 0.0],  # peak Oct(9), 3 from Jul -> excluded (<4)
        "mid": [0.0, 0.0, 80.0] + [0.0] * 9,   # peak Mar(2), 4 from Jul
    }
    rows = M.find_diversification(kv, peak_indices=[6])
    kws = [r["keyword"] for r in rows]
    # near_big is only 3 months away -> not counter-seasonal.
    assert "near_big" not in kws
    # far (6 away) ranks before mid (4 away).
    assert kws == ["far", "mid"]


def test_find_diversification_empty_when_no_peaks():
    assert M.find_diversification({"kw": [1.0] * 12}, peak_indices=[]) == []


# --- helpers -----------------------------------------------------------------

def test_months_apart_circular():
    assert M._months_apart(0, 6) == 6
    assert M._months_apart(0, 11) == 1   # Jan and Dec are adjacent
    assert M._months_apart(2, 2) == 0


def test_to_float_suffixes():
    assert M._to_float("1.2k") == 1200.0
    assert M._to_float("12,345") == 12345.0
    assert M._to_float("2m") == 2_000_000.0
    assert M._to_float("-", default=7.0) == 7.0


# --- smoke test: --demo end to end ------------------------------------------

def test_demo_smoke_writes_parsable_json():
    out_dir = _REPO_ROOT / "data" / "seasonality"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = sorted(out_dir.glob("*.json"))
    assert written, "no seasonality report written"
    report = json.loads(written[-1].read_text())
    assert "site_index" in report
    assert len(report["site_index"]) == 12
    assert "peaks_troughs" in report
    assert "diversification" in report
    # Demo leans summer; winter keywords should surface as diversification.
    div_kws = {r["keyword"] for r in report["diversification"]}
    assert div_kws & {"snow boots", "christmas lights"}
