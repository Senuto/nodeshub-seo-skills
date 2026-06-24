"""Unit + smoke tests for nod-money-keywords/scripts/analyze.py.

Self-contained module loader (no shared conftest).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-money-keywords" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("money_keywords_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- ctr_at_position ---------------------------------------------------------

def test_ctr_at_position_curve_and_clamp():
    assert M.ctr_at_position(5) == 0.06
    assert M.ctr_at_position(1) == 0.30
    assert M.ctr_at_position(10) == 0.018
    # Clamp out-of-range positions to 1..10.
    assert M.ctr_at_position(0) == 0.30
    assert M.ctr_at_position(99) == 0.018
    # Rounds to nearest integer position.
    assert M.ctr_at_position(4.6) == M.ctr_at_position(5)


# --- analyze: filter + classification ----------------------------------------

def test_analyze_money_keyword_filter_and_value_formula():
    rows = [
        # money: cpc>=1, vol>=200, not ranking
        {"query": "crm software", "position": None, "volume": 1000, "cpc": 10.0},
        # money: weak rank (>10)
        {"query": "payroll", "position": 15.0, "volume": 500, "cpc": 4.0},
        # almost there: position 4..10
        {"query": "invoicing", "position": 6.0, "volume": 400, "cpc": 8.0},
        # excluded: already top-3
        {"query": "team chat", "position": 2.0, "volume": 900, "cpc": 5.0},
        # excluded: cpc too low
        {"query": "free notes", "position": 20.0, "volume": 900, "cpc": 0.30},
        # excluded: volume too low
        {"query": "niche widget", "position": None, "volume": 90, "cpc": 12.0},
        # excluded: no cpc signal
        {"query": "what is saas", "position": 15.0, "volume": 700, "cpc": None},
    ]
    money, almost = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=5)
    money_kws = {m["keyword"] for m in money}
    almost_kws = {a["keyword"] for a in almost}
    assert money_kws == {"crm software", "payroll"}
    assert almost_kws == {"invoicing"}

    # Value formula: volume * CTR_at_target(5)=0.06 * cpc.
    crm = next(m for m in money if m["keyword"] == "crm software")
    assert crm["est_reclaimable_monthly_value"] == round(1000 * 0.06 * 10.0, 2)  # 600.0
    assert crm["ranks_organically"] is False
    assert crm["current_position"] is None
    assert crm["assumed_ctr_at_target"] == 0.06

    inv = next(a for a in almost if a["keyword"] == "invoicing")
    assert inv["est_reclaimable_monthly_value"] == round(400 * 0.06 * 8.0, 2)  # 192.0
    assert inv["current_position"] == 6.0


def test_analyze_excludes_top3_from_both_lists():
    rows = [{"query": "won already", "position": 1.5, "volume": 5000, "cpc": 9.0}]
    money, almost = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=5)
    assert money == []
    assert almost == []


def test_analyze_boundary_weak_rank_position_exactly_10_is_almost():
    # position == 10 is in the almost-there band (4..10), not money.
    rows = [{"query": "edge", "position": 10.0, "volume": 1000, "cpc": 5.0}]
    money, almost = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=5)
    assert money == []
    assert [a["keyword"] for a in almost] == ["edge"]


def test_analyze_position_11_is_money():
    rows = [{"query": "edge2", "position": 11.0, "volume": 1000, "cpc": 5.0}]
    money, almost = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=5)
    assert [m["keyword"] for m in money] == ["edge2"]
    assert almost == []


def test_analyze_sorted_by_value_descending():
    rows = [
        {"query": "small", "position": None, "volume": 300, "cpc": 2.0},
        {"query": "big", "position": None, "volume": 9000, "cpc": 20.0},
        {"query": "mid", "position": None, "volume": 2000, "cpc": 5.0},
    ]
    money, _ = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=5)
    values = [m["est_reclaimable_monthly_value"] for m in money]
    assert values == sorted(values, reverse=True)
    assert money[0]["keyword"] == "big"


def test_analyze_target_position_changes_ctr():
    rows = [{"query": "kw", "position": None, "volume": 1000, "cpc": 10.0}]
    money, _ = M.analyze(rows, min_cpc=1.0, min_volume=200, target_position=3)
    # CTR at position 3 = 0.10 -> 1000 * 0.10 * 10 = 1000.0
    assert money[0]["est_reclaimable_monthly_value"] == 1000.0
    assert money[0]["assumed_ctr_at_target"] == 0.10


# --- build_summary -----------------------------------------------------------

def test_build_summary_totals():
    money = [
        {"est_reclaimable_monthly_value": 600.0},
        {"est_reclaimable_monthly_value": 120.0},
    ]
    almost = [{"est_reclaimable_monthly_value": 192.0}]
    summary = M.build_summary(money, almost, min_cpc=1.0, min_volume=200, target_position=5)
    assert summary["money_keywords"] == 2
    assert summary["almost_there"] == 1
    assert summary["total_addressable_monthly_value"] == 720.0
    assert summary["almost_there_monthly_value"] == 192.0
    assert summary["assumed_ctr_at_target"] == 0.06


# --- smoke test: --demo end to end ------------------------------------------

def test_demo_smoke_writes_parsable_json():
    out_dir = _REPO_ROOT / "data" / "money-keywords"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = sorted(out_dir.glob("*.json"))
    assert written, "no money-keywords report written"
    report = json.loads(written[-1].read_text())
    assert "summary" in report and "money_keywords" in report and "almost_there" in report
    # Demo fixture: 4 money keywords, 2 almost-there.
    assert report["summary"]["money_keywords"] == 4
    assert report["summary"]["almost_there"] == 2
    money_kws = {m["keyword"] for m in report["money_keywords"]}
    assert "enterprise crm software" in money_kws
    # Excluded terms must not appear.
    assert "team chat app" not in money_kws
    assert "free notes app" not in money_kws
