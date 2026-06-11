"""Unit + smoke tests for nod-demand-trajectory/scripts/analyze.py.

Covers the deterministic core: yoy_growth() (last 12 vs prior 12),
slope sign, classify() thresholds (rising/declining/stable/emerging/fading),
and the spiky-but-flat case staying Stable.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- self-contained module loader (no shared conftest) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-demand-trajectory" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("demand_trajectory_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dt = _load()


# --- yoy_growth(): last 12 vs prior 12 ---------------------------------------

def test_yoy_none_when_under_24_months():
    assert dt.yoy_growth([100.0] * 12) is None
    assert dt.yoy_growth([100.0] * 23) is None


def test_yoy_doubling():
    # prior 12 sum 1200, last 12 sum 2400 -> +100%.
    series = [100.0] * 12 + [200.0] * 12
    assert dt.yoy_growth(series) == 100.0


def test_yoy_decline():
    # prior 12 sum 1200, last 12 sum 600 -> -50%.
    series = [100.0] * 12 + [50.0] * 12
    assert dt.yoy_growth(series) == -50.0


def test_yoy_flat_zero():
    series = [100.0] * 24
    assert dt.yoy_growth(series) == 0.0


def test_yoy_none_when_prior_year_zero():
    series = [0.0] * 12 + [100.0] * 12
    assert dt.yoy_growth(series) is None


# --- slope sign ---------------------------------------------------------------

def test_slope_positive_for_rising():
    series = [float(v) for v in range(100, 100 + 24)]  # strictly increasing
    assert dt.slope_pct_per_month(series) > 0


def test_slope_negative_for_declining():
    series = [float(v) for v in range(124, 100, -1)]  # strictly decreasing
    assert dt.slope_pct_per_month(series) < 0


def test_slope_near_zero_for_flat():
    series = [500.0] * 24
    assert dt.slope_pct_per_month(series) == 0.0


def test_least_squares_slope_basic():
    # y = 2x -> slope 2.
    assert dt.least_squares_slope([0.0, 2.0, 4.0, 6.0]) == 2.0


# --- classify(): thresholds ---------------------------------------------------

def test_classify_rising_yoy_over_15():
    assert dt.classify(20.0, 1.0, 24) == "Rising"


def test_classify_declining_yoy_under_minus15():
    assert dt.classify(-20.0, -1.0, 24) == "Declining"


def test_classify_stable_in_band():
    assert dt.classify(5.0, 0.5, 24) == "Stable"


def test_classify_emerging_on_steep_slope_in_stable_band():
    # YoY in stable band but slope >= +1.5%/mo -> Emerging.
    assert dt.classify(5.0, 2.0, 24) == "Emerging"


def test_classify_fading_on_steep_negative_slope_in_stable_band():
    assert dt.classify(5.0, -2.0, 24) == "Fading"


def test_classify_short_history_uses_slope_only():
    # No YoY (12 months): steep positive -> Emerging, steep negative -> Fading.
    assert dt.classify(None, 2.0, 12) == "Emerging"
    assert dt.classify(None, -2.0, 12) == "Fading"
    assert dt.classify(None, 0.5, 12) == "Stable"


def test_classify_threshold_overrides():
    # Custom rising threshold of +5 -> a +10% YoY becomes Rising.
    assert dt.classify(10.0, 0.0, 24, rising_threshold=5.0) == "Rising"


# --- analyze_keyword() + demo: spiky-but-flat stays Stable -------------------

def test_demo_classifications():
    ds = dt._demo_series()
    labels = {kw: dt.analyze_keyword(kw, s)["classification"] for kw, s in ds.items()}
    assert labels["ai agents"] == "Rising"
    assert labels["fax machine"] == "Declining"
    assert labels["project management software"] == "Stable"
    # The spiky-but-flat case must NOT be mistaken for a trend.
    assert labels["garden furniture"] == "Stable"


def test_spiky_but_flat_stays_stable():
    spiky = dt._demo_series()["garden furniture"]
    row = dt.analyze_keyword("garden furniture", spiky)
    assert row["classification"] == "Stable"
    assert abs(row["yoy_pct"]) < 15.0


def test_analyze_keyword_reports_history_length():
    row = dt.analyze_keyword("x", [100.0] * 24)
    assert row["months_of_history"] == 24
    assert row["latest_12m_volume"] == 1200


# --- smoke test: --demo via subprocess ---------------------------------------

def test_demo_smoke_writes_json():
    out_path = _REPO_ROOT / "data" / "demand-trajectory" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    data = json.loads(out_path.read_text())
    assert "keywords" in data
    assert "portfolio" in data
    assert data["meta"]["keyword_count"] == len(data["keywords"])
