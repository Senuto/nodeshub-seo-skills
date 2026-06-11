"""Unit + smoke tests for nod-content-gap/scripts/analyze.py.

Covers the deterministic core: build_universe() prevalence,
classify_gaps() (missing/weak/shared), and potential_score() ordering.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- self-contained module loader (no shared conftest) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-content-gap" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("content_gap_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cg = _load()


# --- build_universe(): prevalence + best competitor --------------------------

def test_build_universe_prevalence_counts_competitors():
    comp = {
        "a.com": {"kw1": {"position": 5.0, "volume": 1000.0}},
        "b.com": {"kw1": {"position": 3.0, "volume": 1000.0}},
    }
    uni = cg.build_universe(comp, rank_window=20)
    assert uni["kw1"]["prevalence"] == 2
    # Best competitor = lowest position number.
    assert uni["kw1"]["best_competitor"] == "b.com"
    assert uni["kw1"]["best_position"] == 3.0


def test_build_universe_excludes_outside_rank_window():
    comp = {"a.com": {"deep": {"position": 25.0, "volume": 500.0}}}
    uni = cg.build_universe(comp, rank_window=20)
    assert "deep" not in uni


def test_build_universe_missing_volume_defaults_zero():
    comp = {"a.com": {"kw": {"position": 4.0, "volume": None}}}
    uni = cg.build_universe(comp, rank_window=20)
    assert uni["kw"]["volume"] == 0.0


# --- classify_gaps(): missing / weak / shared --------------------------------

def test_classify_missing_when_you_dont_rank():
    mine = {}  # you rank for nothing
    comp = {"a.com": {"kw": {"position": 3.0, "volume": 1000.0}}}
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    assert [r["keyword"] for r in missing] == ["kw"]
    assert weak == []
    assert shared == 0


def test_classify_weak_when_beaten_by_margin():
    # You rank #14, competitor #3 -> gap 11 >= margin 5 -> weak.
    mine = {"kw": {"position": 14.0, "volume": 1000.0}}
    comp = {"a.com": {"kw": {"position": 3.0, "volume": 1000.0}}}
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    assert missing == []
    assert len(weak) == 1
    assert weak[0]["keyword"] == "kw"
    assert weak[0]["gap_to_best"] == 11.0


def test_classify_shared_when_within_margin():
    # You rank #7, competitor #5 -> gap 2 < margin 5 -> shared/strong, not a gap.
    mine = {"kw": {"position": 7.0, "volume": 1000.0}}
    comp = {"a.com": {"kw": {"position": 5.0, "volume": 1000.0}}}
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    assert missing == []
    assert weak == []
    assert shared == 1


def test_classify_you_outside_window_counts_as_missing():
    # You rank #25 (outside window) -> treated as not ranking -> missing.
    mine = {"kw": {"position": 25.0, "volume": 1000.0}}
    comp = {"a.com": {"kw": {"position": 4.0, "volume": 1000.0}}}
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    assert [r["keyword"] for r in missing] == ["kw"]


def test_classify_weak_margin_boundary_exact():
    # gap exactly == margin -> weak (>=).
    mine = {"kw": {"position": 9.0, "volume": 1000.0}}
    comp = {"a.com": {"kw": {"position": 4.0, "volume": 1000.0}}}
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    assert len(weak) == 1
    assert weak[0]["gap_to_best"] == 5.0


# --- potential_score(): volume * prevalence / difficulty ---------------------

def test_potential_score_formula():
    # difficulty = 1 + (21 - capped_pos)/10; pos 9 -> 1 + 1.2 = 2.2
    score = cg.potential_score(1000.0, 2, 9.0)
    assert score == round((1000.0 * 2) / 2.2, 2)


def test_potential_score_higher_prevalence_wins():
    a = cg.potential_score(1000.0, 3, 5.0)
    b = cg.potential_score(1000.0, 1, 5.0)
    assert a > b


def test_potential_score_winnability_rewards_weaker_best_competitor():
    # Corrected behavior: difficulty grows as the best competitor sits closer to
    # the top. A gap whose strongest competitor only reaches #18 is easier to win
    # and scores HIGHER than one locked down at #2.
    near_top = cg.potential_score(1000.0, 1, 2.0)
    deeper = cg.potential_score(1000.0, 1, 18.0)
    assert deeper > near_top


def test_missing_sorted_by_potential_desc():
    comp = {
        "a.com": {
            "big": {"position": 5.0, "volume": 40000.0},
            "small": {"position": 5.0, "volume": 100.0},
        }
    }
    uni = cg.build_universe(comp, 20)
    missing, _, _ = cg.classify_gaps({}, uni, 20, 5)
    assert [r["keyword"] for r in missing] == ["big", "small"]


# --- demo fixture sanity ------------------------------------------------------

def test_demo_classification_matches_design():
    domain, comp, mine = cg._demo_data()
    uni = cg.build_universe(comp, 20)
    missing, weak, shared = cg.classify_gaps(mine, uni, 20, 5)
    missing_kws = {r["keyword"] for r in missing}
    assert "project management software" in missing_kws
    assert "kanban board" in missing_kws
    assert [r["keyword"] for r in weak] == ["gantt chart maker"]
    # "free task tracker" you own; "team collaboration tool" within margin -> shared.
    assert shared == 1


# --- smoke test: --demo via subprocess ---------------------------------------

def test_demo_smoke_writes_json():
    out_path = _REPO_ROOT / "data" / "content-gap" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    data = json.loads(out_path.read_text())
    assert "summary" in data
    assert "missing" in data
    assert "weak" in data
    assert data["summary"]["missing"] == len(data["missing"])
