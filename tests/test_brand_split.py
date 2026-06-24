"""Unit + smoke tests for nod-brand-split/scripts/analyze.py.

Self-contained module loader (no shared conftest).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-brand-split" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("brand_split_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()


# --- build_matcher: word-boundary, domain substring, regex -------------------

def test_build_matcher_word_boundary_match():
    pred, _ = M.build_matcher(["acme"], "")
    assert pred("acme shoes") is True
    assert pred("buy acme") is True
    # Word-boundary aware: "acmebackwards" must NOT match.
    assert pred("acmebackwards") is False
    assert pred("widget supplier") is False


def test_build_matcher_phrase_term():
    pred, _ = M.build_matcher(["acme corp"], "")
    assert pred("acme corp login") is True
    assert pred("acme corporation") is False  # boundary after "corp" fails


def test_build_matcher_domain_substring():
    # Dotted term matches as a substring (boundaries misbehave on dots).
    pred, _ = M.build_matcher(["acmewidgets.com"], "")
    assert pred("acmewidgets.com pricing") is True
    assert pred("visit acmewidgets.com/about") is True


def test_build_matcher_regex_variants():
    pred, _ = M.build_matcher([], r"acme|akme")
    assert pred("akme widgets") is True
    assert pred("acme tools") is True
    assert pred("generic tools") is False


def test_build_matcher_case_insensitive():
    pred, _ = M.build_matcher(["acme"], "")
    assert pred("ACME Shoes") is True
    assert pred("Acme Corp") is True


def test_build_matcher_empty_query_is_not_branded():
    pred, _ = M.build_matcher(["acme"], "")
    assert pred("") is False
    assert pred(None) is False


# --- _percent ----------------------------------------------------------------

def test_percent_basic():
    assert M._percent(1, 4) == 25.0
    assert M._percent(1, 3) == 33.3
    assert M._percent(0, 0) == 0.0   # zero whole -> 0, no division error


# --- split_queries: totals and percentages -----------------------------------

def _rows():
    # 2 branded, 2 non-branded.
    return [
        {"query": "acme", "clicks": 100, "impressions": 1000, "position": 1.0},
        {"query": "acme login", "clicks": 50, "impressions": 500, "position": 2.0},
        {"query": "best widgets", "clicks": 30, "impressions": 600, "position": 5.0},
        {"query": "buy widgets", "clicks": 20, "impressions": 400, "position": 9.0},
    ]


def test_split_queries_partitions_and_totals():
    pred, _ = M.build_matcher(["acme"], "")
    branded, non_branded, totals = M.split_queries(_rows(), pred)
    assert {r["query"] for r in branded} == {"acme", "acme login"}
    assert {r["query"] for r in non_branded} == {"best widgets", "buy widgets"}

    assert totals["total_queries"] == 4
    assert totals["total_clicks"] == 200
    assert totals["total_impressions"] == 2500

    b = totals["branded"]
    n = totals["non_branded"]
    assert b["clicks"] == 150
    assert n["clicks"] == 50
    # 150/200 = 75.0%, 50/200 = 25.0%
    assert b["clicks_pct"] == 75.0
    assert n["clicks_pct"] == 25.0
    # Impressions: branded 1500/2500 = 60.0%
    assert b["impressions_pct"] == 60.0
    assert b["queries_pct"] == 50.0


def test_split_queries_avg_position():
    pred, _ = M.build_matcher(["acme"], "")
    _, _, totals = M.split_queries(_rows(), pred)
    # branded positions 1.0, 2.0 -> avg 1.5
    assert totals["branded"]["avg_position"] == 1.5
    # non-branded 5.0, 9.0 -> avg 7.0
    assert totals["non_branded"]["avg_position"] == 7.0


def test_avg_position_none_when_no_positions():
    rows = [{"query": "x", "clicks": 1, "impressions": 1, "position": None}]
    assert M._avg_position(rows) is None


# --- top_queries -------------------------------------------------------------

def test_top_queries_sorts_by_clicks_then_impressions():
    bucket = [
        {"query": "a", "clicks": 10, "impressions": 100, "position": 1.0},
        {"query": "b", "clicks": 50, "impressions": 200, "position": 2.0},
        {"query": "c", "clicks": 50, "impressions": 900, "position": 3.0},
    ]
    top = M.top_queries(bucket, limit=2)
    # b and c tie on clicks; c wins on impressions; only 2 returned.
    assert [r["query"] for r in top] == ["c", "b"]


# --- smoke test: --demo end to end ------------------------------------------

def test_demo_smoke_writes_parsable_json():
    out_dir = _REPO_ROOT / "data" / "brand-split"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    written = sorted(out_dir.glob("*.json"))
    assert written, "no brand-split report written"
    report = json.loads(written[-1].read_text())
    assert "totals" in report and "top" in report and "trend" in report
    t = report["totals"]
    # Branded + non-branded clicks must sum to the total.
    assert (t["branded"]["clicks"] + t["non_branded"]["clicks"]
            == t["total_clicks"])
    # Demo fixture: "akme widgets" is caught by the brand regex.
    branded_qs = {r["query"] for r in report["top"]["branded"]}
    assert "akme widgets" in branded_qs
