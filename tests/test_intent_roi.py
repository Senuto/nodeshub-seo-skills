"""Unit + smoke tests for nod-intent-roi/scripts/analyze.py.

Self-contained module loader (no shared conftest).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-intent-roi" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("intent_roi_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- canonical_intent --------------------------------------------------------

def test_canonical_intent_aliases():
    assert M.canonical_intent("buy") == "transactional"
    assert M.canonical_intent("info") == "informational"
    assert M.canonical_intent("compare") == "commercial"
    assert M.canonical_intent("brand") == "navigational"
    assert M.canonical_intent("transactional") == "transactional"
    assert M.canonical_intent("nonsense") == "unknown"
    assert M.canonical_intent(None) == "unknown"


# --- aggregate: roll-up + conversions counted once per URL -------------------

def _fixture():
    by_query = [
        {"query": "buy shoes", "clicks": 100, "position": 3.0},
        {"query": "cheap shoes deal", "clicks": 50, "position": 4.0},
        {"query": "shoe size guide", "clicks": 200, "position": 6.0},
    ]
    by_url = [
        {"url": "/shop", "clicks": 150, "sessions": 1000, "conversions": 90},
        {"url": "/guide", "clicks": 200, "sessions": 800, "conversions": 4},
    ]
    # Both transactional queries map to /shop; informational to /guide.
    query_page_map = {
        "buy shoes": "/shop",
        "cheap shoes deal": "/shop",
        "shoe size guide": "/guide",
    }
    intents = {
        "buy shoes": "transactional",
        "cheap shoes deal": "transactional",
        "shoe size guide": "informational",
    }
    return by_query, by_url, query_page_map, intents


def test_aggregate_conversions_counted_once_per_url():
    by_query, by_url, qpm, intents = _fixture()
    buckets, stats = M.aggregate(by_query, by_url, qpm, intents)
    trans = buckets["transactional"]
    info = buckets["informational"]
    # Two transactional queries share /shop; its 90 conversions counted ONCE.
    assert trans["conversions"] == 90.0
    assert trans["sessions"] == 1000.0
    # Clicks accumulate per query (100 + 50).
    assert trans["clicks"] == 150.0
    assert trans["queries"] == 2
    assert info["conversions"] == 4.0
    assert info["clicks"] == 200.0
    # Two URLs attributed in total.
    assert stats["urls_attributed"] == 2
    assert stats["queries_attributed"] == 3


def test_aggregate_conversion_rate_and_roi():
    by_query, by_url, qpm, intents = _fixture()
    buckets, _ = M.aggregate(by_query, by_url, qpm, intents)
    trans = buckets["transactional"]
    # CvR against sessions: 90 / 1000 = 0.09
    assert trans["conversion_rate"] == 0.09
    # ROI per 100 clicks: 90 / 150 * 100 = 60.0
    assert trans["roi_per_100_clicks"] == 60.0
    info = buckets["informational"]
    # CvR 4/800 = 0.005 ; ROI 4/200*100 = 2.0
    assert info["conversion_rate"] == 0.005
    assert info["roi_per_100_clicks"] == 2.0


# --- rank_and_recommend: best/worst selection + ordering ---------------------

def test_rank_and_recommend_best_worst():
    by_query, by_url, qpm, intents = _fixture()
    buckets, _ = M.aggregate(by_query, by_url, qpm, intents)
    ranked, best, worst, recommendation, total_conv = M.rank_and_recommend(buckets)
    assert total_conv == 94.0
    # Transactional (ROI 60) is most efficient; informational (ROI 2) least.
    assert best["intent"] == "transactional"
    assert worst["intent"] == "informational"
    # Ranked descending by ROI proxy: transactional before informational.
    eff_order = [b["intent"] for b in ranked]
    assert eff_order.index("transactional") < eff_order.index("informational")
    assert "transactional" in recommendation


def test_rank_and_recommend_shares_sum_to_one():
    by_query, by_url, qpm, intents = _fixture()
    buckets, _ = M.aggregate(by_query, by_url, qpm, intents)
    M.rank_and_recommend(buckets)
    total = sum(b["share_of_conversions"] for b in buckets.values())
    assert round(total, 4) == 1.0
    # transactional 90/94, informational 4/94
    assert buckets["transactional"]["share_of_conversions"] == round(90 / 94, 4)


def test_rank_and_recommend_no_conversions_returns_none_best():
    by_query = [{"query": "x", "clicks": 10, "position": 5.0}]
    by_url = [{"url": "/p", "clicks": 10, "sessions": 100, "conversions": 0}]
    qpm = {"x": "/p"}
    intents = {"x": "informational"}
    buckets, _ = M.aggregate(by_query, by_url, qpm, intents)
    _, best, worst, recommendation, _ = M.rank_and_recommend(buckets)
    assert best is None
    assert "No intent bucket" in recommendation


# --- build_query_page_map ----------------------------------------------------

def test_build_query_page_map_explicit_page_wins():
    by_query = [{"query": "kw", "page": "/explicit", "clicks": 5}]
    by_url = [{"url": "/explicit"}]
    qpm = M.build_query_page_map(by_query, by_url, query_pages=None)
    assert qpm["kw"] == "/explicit"


def test_build_query_page_map_uses_query_pages_best_click():
    by_query = [{"query": "kw", "clicks": 5}]
    by_url = [{"url": "/a"}, {"url": "/b"}]
    query_pages = [
        {"query": "kw", "page": "/a", "clicks": 10},
        {"query": "kw", "page": "/b", "clicks": 40},
    ]
    qpm = M.build_query_page_map(by_query, by_url, query_pages)
    # The page with the most clicks (/b) wins.
    assert qpm["kw"] == "/b"


# --- smoke test: --demo end to end ------------------------------------------

def test_demo_smoke_writes_parsable_json():
    out_dir = _REPO_ROOT / "data" / "intent-roi"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = sorted(out_dir.glob("*.json"))
    assert written, "no intent-roi report written"
    report = json.loads(written[-1].read_text())
    assert "intents" in report and "best_converting_intent" in report
    # Demo: transactional (/shop, 152 conv on 470 clicks) is the best converter.
    assert report["best_converting_intent"] == "transactional"
    assert report["total_conversions"] > 0
