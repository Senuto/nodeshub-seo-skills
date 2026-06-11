"""Unit + smoke tests for the nod-merger skill (merge.py).

Covers URL normalization, keyword normalization, percent/currency parsing,
the by_url join (GSC + GA4 on URL), the by_query join (GSC + Ads on keyword),
optional-source handling (missing GA4 / Ads), coverage stats, and a --demo
smoke test that asserts the merged dataset is written with documented keys.

Self-contained loader (no shared conftest) so sibling test files do not collide.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MERGE_PATH = _REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts" / "merge.py"


def _load_merge():
    """Import merge.py from its file path as an isolated module object."""
    spec = importlib.util.spec_from_file_location("nod_merge_under_test", _MERGE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


merge = _load_merge()


# --- normalize_url -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("https://example.com/blog/x", "/blog/x"),
    ("http://EXAMPLE.com/Blog/X", "/blog/x"),
    ("/blog/x", "/blog/x"),
    ("/blog/x/", "/blog/x"),            # trailing slash stripped
    ("/blog/x?utm=1", "/blog/x"),       # query stripped
    ("/blog/x#frag", "/blog/x"),        # fragment stripped
    ("blog/x", "/blog/x"),              # leading slash added (no dot host)
    ("https://example.com/", "/"),      # host dropped -> "/" (len 1, not stripped)
    ("", ""),
    (None, ""),
])
def test_normalize_url(raw, expected):
    assert merge.normalize_url(raw) == expected


def test_normalize_url_host_without_slash_keeps_host():
    # No "/" in the post-protocol string, so the host-drop branch is skipped;
    # a leading slash is simply prepended. Documents real (quirky) behavior.
    assert merge.normalize_url("https://example.com") == "/example.com"


def test_normalize_keyword():
    assert merge.normalize_keyword("  SEO   Tools ") == "seo tools"
    assert merge.normalize_keyword("Keyword\tResearch") == "keyword research"
    assert merge.normalize_keyword(None) == ""


# --- numeric parsing ---------------------------------------------------------

def test_to_float_percent_and_currency():
    assert merge._to_float("4.29%") == 4.29
    assert merge._to_float("$3.45") == 3.45
    assert merge._to_float("1,240.50") == 1240.50
    assert merge._to_float(92) == 92.0
    assert merge._to_float("5.1") == 5.1


def test_to_float_failures():
    assert merge._to_float(None) is None
    assert merge._to_float("-") is None
    assert merge._to_float("abc") is None


def test_to_int_rounds():
    assert merge._to_int("11.6") == 12
    assert merge._to_int(None) is None


def test_competition_value_labels_and_index():
    assert merge._competition_value("low") == 0.2
    assert merge._competition_value("medium") == 0.5
    assert merge._competition_value("high") == 0.8
    assert merge._competition_value("80") == 0.8     # 0-100 index -> 0-1
    assert merge._competition_value("0.4") == 0.4    # already 0-1
    assert merge._competition_value("garbage") is None


# --- build_by_url (GSC + GA4 join) ------------------------------------------

def test_build_by_url_matches_on_normalized_url():
    gsc = {"topPages": [
        {"page": "https://example.com/a", "impressions": "1000", "clicks": "50",
         "ctr": "5%", "position": "4.2"},
    ]}
    ga4 = {"topPages": [
        {"page": "/a", "pageviews": 200, "users": 150, "sessions": 180,
         "conversions": 7, "engagementRate": "62%", "avgSessionDuration": 95},
    ]}
    rows = merge.build_by_url(gsc, ga4)
    assert len(rows) == 1
    r = rows[0]
    assert r["url"] == "/a"
    assert r["in_gsc"] is True
    assert r["in_ga4"] is True
    assert r["impressions"] == 1000
    assert r["clicks"] == 50
    assert r["ctr"] == 5.0
    assert r["position"] == 4.2
    assert r["sessions"] == 180
    assert r["conversions"] == 7
    assert r["engagement_rate"] == 62.0


def test_build_by_url_sessions_fall_back_to_users():
    gsc = {"topPages": [{"page": "/a", "impressions": 10, "clicks": 1}]}
    ga4 = {"topPages": [{"page": "/a", "users": 99}]}  # no sessions key
    rows = merge.build_by_url(gsc, ga4)
    assert rows[0]["sessions"] == 99  # users used as proxy


def test_build_by_url_gsc_without_ga4():
    gsc = {"topPages": [{"page": "/a", "impressions": 10, "clicks": 1}]}
    rows = merge.build_by_url(gsc, None)
    assert len(rows) == 1
    assert rows[0]["in_ga4"] is False
    assert rows[0]["sessions"] is None
    assert rows[0]["conversions"] is None


def test_build_by_url_ga4_only_pages_appended():
    gsc = {"topPages": [{"page": "/a", "impressions": 10, "clicks": 1}]}
    ga4 = {"topPages": [
        {"page": "/a", "users": 5},
        {"page": "/orphan", "users": 3, "pageviews": 4},
    ]}
    rows = merge.build_by_url(gsc, ga4)
    by_url = {r["url"]: r for r in rows}
    assert by_url["/orphan"]["in_gsc"] is False
    assert by_url["/orphan"]["in_ga4"] is True
    assert by_url["/orphan"]["impressions"] is None
    assert by_url["/a"]["in_gsc"] is True and by_url["/a"]["in_ga4"] is True


# --- build_by_query (GSC + Ads join) ----------------------------------------

def test_build_by_query_matches_ads_on_keyword():
    gsc = {"topQueries": [
        {"query": "SEO Tools", "clicks": "10", "impressions": "500",
         "ctr": "2%", "position": "7.1"},
    ]}
    ads = [{"keyword": "seo tools", "volume": 12000, "cpc": 3.4, "competition": 0.7}]
    rows = merge.build_by_query(gsc, ads)
    assert len(rows) == 1
    r = rows[0]
    assert r["query"] == "SEO Tools"
    assert r["in_ads"] is True
    assert r["clicks"] == 10
    assert r["impressions"] == 500
    assert r["volume"] == 12000
    assert r["cpc"] == 3.4
    assert r["competition"] == 0.7


def test_build_by_query_without_ads():
    gsc = {"topQueries": [{"query": "seo tools", "clicks": 1, "impressions": 5}]}
    rows = merge.build_by_query(gsc, None)
    assert rows[0]["in_ads"] is False
    assert rows[0]["volume"] is None
    assert rows[0]["cpc"] is None


def test_build_by_query_no_match_when_keyword_differs():
    gsc = {"topQueries": [{"query": "rank tracker", "clicks": 1, "impressions": 5}]}
    ads = [{"keyword": "seo tools", "volume": 100, "cpc": 1.0, "competition": 0.5}]
    rows = merge.build_by_query(gsc, ads)
    assert rows[0]["in_ads"] is False


# --- coverage_stats ----------------------------------------------------------

def test_coverage_stats_counts_matches():
    by_url = [
        {"in_gsc": True, "in_ga4": True},
        {"in_gsc": True, "in_ga4": False},
        {"in_gsc": False, "in_ga4": True},
    ]
    by_query = [{"in_ads": True}, {"in_ads": False}]
    stats = merge.coverage_stats(by_url, by_query)
    assert stats["by_url_rows"] == 3
    assert stats["by_url_gsc_ga4_matched"] == 1
    assert stats["by_query_rows"] == 2
    assert stats["by_query_ads_matched"] == 1


# --- smoke test (--demo) -----------------------------------------------------

def test_demo_smoke_writes_merged_dataset():
    out_path = _REPO_ROOT / "data" / "merged" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_MERGE_PATH), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert set(["meta", "by_url", "by_query"]).issubset(data.keys())
    assert isinstance(data["by_url"], list)
    assert isinstance(data["by_query"], list)
    assert "coverage" in data["meta"]
