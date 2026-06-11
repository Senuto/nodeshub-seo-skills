"""Unit + smoke tests for nod-commercial-value/scripts/analyze.py.

Covers the deterministic core: opportunity() multiplier bands,
score_keyword() = volume*cpc*opportunity, and assign_tiers() splitting.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- self-contained module loader (no shared conftest) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-commercial-value" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("commercial_value_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cv = _load()


# --- opportunity() multiplier bands ------------------------------------------

def test_opportunity_not_ranking_full():
    assert cv.opportunity(None) == ("full", 1.00)


def test_opportunity_position_over_20_full():
    assert cv.opportunity(21) == ("full", 1.00)
    assert cv.opportunity(100) == ("full", 1.00)


def test_opportunity_page2_high():
    # 11-20 -> high, 0.75
    assert cv.opportunity(20) == ("high", 0.75)
    assert cv.opportunity(11) == ("high", 0.75)


def test_opportunity_positions_4_to_10_medium():
    assert cv.opportunity(10) == ("medium", 0.40)
    assert cv.opportunity(4) == ("medium", 0.40)


def test_opportunity_top3_low():
    assert cv.opportunity(3) == ("low", 0.10)
    assert cv.opportunity(1) == ("low", 0.10)


def test_opportunity_boundaries_exact():
    # Boundary checks straddling the bands.
    assert cv.opportunity(3)[1] == 0.10
    assert cv.opportunity(4)[1] == 0.40
    assert cv.opportunity(10)[1] == 0.40
    assert cv.opportunity(11)[1] == 0.75
    assert cv.opportunity(20)[1] == 0.75
    assert cv.opportunity(21)[1] == 1.00


# --- score_keyword() = volume * cpc * opportunity ----------------------------

def test_score_keyword_full_upside():
    # not ranking -> multiplier 1.0
    row = {"keyword": "x", "volume": 1000, "cpc": 5.0, "position": None}
    s = cv.score_keyword(row)
    assert s["commercial_value"] == 5000.0
    assert s["priority"] == 5000.0
    assert s["opportunity"] == "full"
    assert s["valued"] is True


def test_score_keyword_medium_band():
    # position 8 -> medium, 0.40
    row = {"keyword": "y", "volume": 100, "cpc": 2.0, "position": 8}
    s = cv.score_keyword(row)
    assert s["commercial_value"] == 200.0
    assert s["priority"] == 80.0  # 200 * 0.40
    assert s["opportunity_multiplier"] == 0.40


def test_score_keyword_top3_low_priority():
    row = {"keyword": "z", "volume": 1000, "cpc": 10.0, "position": 1}
    s = cv.score_keyword(row)
    assert s["commercial_value"] == 10000.0
    assert s["priority"] == 1000.0  # 10000 * 0.10


def test_score_keyword_unvalued_scores_zero():
    # missing cpc -> not valued -> 0
    row = {"keyword": "novalue", "volume": 1000, "cpc": None, "position": None}
    s = cv.score_keyword(row)
    assert s["valued"] is False
    assert s["commercial_value"] == 0.0
    assert s["priority"] == 0.0


# --- assign_tiers() split -----------------------------------------------------

def _row(kw, vol, cpc, pos):
    return cv.score_keyword({"keyword": kw, "volume": vol, "cpc": cpc, "position": pos})


def test_assign_tiers_sorts_by_priority_desc():
    scored = [
        _row("low", 100, 1.0, None),     # priority 100
        _row("high", 1000, 10.0, None),  # priority 10000
        _row("mid", 500, 2.0, None),     # priority 1000
    ]
    ranked = cv.assign_tiers(scored)
    assert [r["keyword"] for r in ranked] == ["high", "mid", "low"]


def test_assign_tiers_thirds_split():
    # 6 keywords -> third = 2: tier1 first 2, tier2 next 2, tier3 last 2.
    scored = [_row(f"k{i}", 1000 - i * 100, 5.0, None) for i in range(6)]
    ranked = cv.assign_tiers(scored)
    tiers = [r["tier"] for r in ranked]
    assert tiers == [1, 1, 2, 2, 3, 3]


def test_assign_tiers_zero_priority_goes_tier3():
    # An unvalued keyword (priority 0) always lands in tier 3.
    scored = [
        _row("a", 1000, 5.0, None),
        _row("b", 800, 5.0, None),
        _row("zero", 1000, None, None),  # unvalued -> priority 0
    ]
    ranked = cv.assign_tiers(scored)
    by_kw = {r["keyword"]: r["tier"] for r in ranked}
    assert by_kw["zero"] == 3


def test_assign_tiers_single_keyword_all_tier1():
    scored = [_row("solo", 1000, 5.0, None)]
    ranked = cv.assign_tiers(scored)
    assert ranked[0]["tier"] == 1


def test_assign_tiers_empty():
    assert cv.assign_tiers([]) == []


# --- smoke test: --demo via subprocess ---------------------------------------

def test_demo_smoke_writes_json():
    out_path = _REPO_ROOT / "data" / "commercial-value" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    data = json.loads(out_path.read_text())
    assert "summary" in data
    assert "keywords" in data
    assert data["summary"]["keywords"] == len(data["keywords"])
