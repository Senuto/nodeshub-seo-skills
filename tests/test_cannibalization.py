"""Unit + smoke tests for the nod-cannibalization skill (detect.py).

Covers group_by_query, pick_strongest ordering (clicks > impressions >
position), score_conflict severity buckets, detect flagging only queries with
>= 2 distinct pages above the impression floor, recommend branches (zero clicks
-> consolidate, even split -> canonical, clear leader -> de-optimize), and a
--demo smoke test asserting the report JSON is written with documented keys.

Self-contained loader (no shared conftest) to avoid sibling-file collisions.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DETECT_PATH = (_REPO_ROOT / ".claude" / "skills" / "nod-cannibalization"
                / "scripts" / "detect.py")


def _load_detect():
    spec = importlib.util.spec_from_file_location("nod_cannibal_under_test", _DETECT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


detect_mod = _load_detect()


def _page(page, clicks, impressions, position):
    """Build a normalized page-row like group_by_query produces."""
    return {"page": page, "clicks": float(clicks),
            "impressions": float(impressions), "ctr": "",
            "position": float(position)}


# --- _to_float ---------------------------------------------------------------

def test_to_float_strips_percent():
    assert detect_mod._to_float("12.3%") == 12.3
    assert detect_mod._to_float("4.5") == 4.5
    assert detect_mod._to_float(7) == 7.0
    assert detect_mod._to_float(None) == 0.0
    assert detect_mod._to_float("bad") == 0.0


# --- group_by_query ----------------------------------------------------------

def test_group_by_query_groups_and_skips_incomplete():
    rows = [
        {"query": "q1", "page": "/a", "clicks": "5", "impressions": "100", "position": "3"},
        {"query": "q1", "page": "/b", "clicks": "2", "impressions": "80", "position": "6"},
        {"query": "q2", "page": "/c", "clicks": "1", "impressions": "10", "position": "9"},
        {"query": "", "page": "/x", "clicks": 0, "impressions": 0, "position": 0},  # skipped
        {"query": "q3", "page": "", "clicks": 0, "impressions": 0, "position": 0},  # skipped
    ]
    grouped = detect_mod.group_by_query(rows)
    assert set(grouped.keys()) == {"q1", "q2"}
    assert len(grouped["q1"]) == 2
    assert grouped["q1"][0]["impressions"] == 100.0


# --- pick_strongest ----------------------------------------------------------

def test_pick_strongest_prefers_clicks():
    pages = [
        _page("/a", clicks=1, impressions=999, position=1),
        _page("/b", clicks=10, impressions=10, position=20),
    ]
    assert detect_mod.pick_strongest(pages)["page"] == "/b"  # clicks dominate


def test_pick_strongest_tiebreak_impressions_then_position():
    # Equal clicks -> more impressions wins.
    pages = [
        _page("/a", clicks=5, impressions=100, position=8),
        _page("/b", clicks=5, impressions=200, position=9),
    ]
    assert detect_mod.pick_strongest(pages)["page"] == "/b"
    # Equal clicks and impressions -> lower (better) position wins.
    pages2 = [
        _page("/a", clicks=5, impressions=100, position=8),
        _page("/b", clicks=5, impressions=100, position=3),
    ]
    assert detect_mod.pick_strongest(pages2)["page"] == "/b"


# --- score_conflict severity buckets ----------------------------------------

def test_score_conflict_high_when_evenly_split():
    # Perfectly even impressions + clicks, ranking flip present -> high severity.
    pages = [
        _page("/a", clicks=50, impressions=500, position=4),
        _page("/b", clicks=50, impressions=500, position=5),
    ]
    tag, score = detect_mod.score_conflict(pages)
    assert tag == "high"
    assert score >= 0.55


def test_score_conflict_low_when_one_page_dominates():
    # One page owns nearly everything -> evenness ~0, no flip -> low severity.
    pages = [
        _page("/a", clicks=100, impressions=1000, position=2),
        _page("/b", clicks=0, impressions=1, position=40),
    ]
    tag, score = detect_mod.score_conflict(pages)
    assert tag == "low"
    assert score < 0.30


# --- recommend branches ------------------------------------------------------

def test_recommend_consolidate_when_zero_clicks():
    pages = [
        _page("/a", clicks=0, impressions=300, position=12),
        _page("/b", clicks=0, impressions=300, position=14),
    ]
    strongest = detect_mod.pick_strongest(pages)
    rec = detect_mod.recommend(pages, strongest)
    assert "Consolidate" in rec


def test_recommend_canonical_when_even_split():
    # Clicks > 0 and impressions split near-evenly -> canonical advice.
    pages = [
        _page("/a", clicks=10, impressions=500, position=5),
        _page("/b", clicks=8, impressions=500, position=6),
    ]
    strongest = detect_mod.pick_strongest(pages)
    rec = detect_mod.recommend(pages, strongest)
    assert "canonical" in rec.lower()


def test_recommend_deoptimize_when_clear_leader():
    # Clicks > 0 but impressions concentrated on one page -> de-optimize advice.
    pages = [
        _page("/a", clicks=40, impressions=950, position=2),
        _page("/b", clicks=2, impressions=50, position=18),
    ]
    strongest = detect_mod.pick_strongest(pages)
    rec = detect_mod.recommend(pages, strongest)
    assert "De-optimize" in rec


# --- detect ------------------------------------------------------------------

def test_detect_flags_only_two_plus_pages_above_floor():
    rows = [
        # q1: two pages, both above floor -> conflict.
        {"query": "q1", "page": "/a", "clicks": "10", "impressions": "100", "position": "4"},
        {"query": "q1", "page": "/b", "clicks": "8", "impressions": "90", "position": "6"},
        # q2: second page below floor -> not a conflict (only 1 distinct above floor).
        {"query": "q2", "page": "/c", "clicks": "5", "impressions": "100", "position": "3"},
        {"query": "q2", "page": "/d", "clicks": "0", "impressions": "5", "position": "30"},
        # q3: only one page -> never a conflict.
        {"query": "q3", "page": "/e", "clicks": "20", "impressions": "300", "position": "2"},
    ]
    conflicts = detect_mod.detect(rows, min_impressions=10)
    queries = {c["query"] for c in conflicts}
    assert queries == {"q1"}
    c = conflicts[0]
    assert c["strongest_url"] == "/a"
    assert c["total_clicks"] == 18.0
    assert c["total_impressions"] == 190.0
    assert c["severity"] in {"high", "medium", "low"}


def test_detect_sorts_by_severity_score_desc():
    rows = [
        # high-severity query (even split + flip).
        {"query": "hi", "page": "/a", "clicks": "50", "impressions": "500", "position": "5"},
        {"query": "hi", "page": "/b", "clicks": "50", "impressions": "500", "position": "4"},
        # low-severity query (clear dominator).
        {"query": "lo", "page": "/c", "clicks": "100", "impressions": "1000", "position": "2"},
        {"query": "lo", "page": "/d", "clicks": "0", "impressions": "11", "position": "40"},
    ]
    conflicts = detect_mod.detect(rows, min_impressions=10)
    assert [c["query"] for c in conflicts] == ["hi", "lo"]
    assert conflicts[0]["severity_score"] >= conflicts[1]["severity_score"]


# --- smoke test (--demo) -----------------------------------------------------

def test_demo_smoke_writes_report():
    out_path = _REPO_ROOT / "data" / "cannibalization" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_DETECT_PATH), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    for key in ("date", "source", "min_impressions", "conflicts_found", "conflicts"):
        assert key in data
    assert isinstance(data["conflicts"], list)
    assert data["conflicts_found"] == len(data["conflicts"])
