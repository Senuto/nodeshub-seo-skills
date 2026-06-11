"""Unit + smoke tests for nod-alerting/scripts/alert.py.

Covers the deterministic core: diff_rank() rank-drop threshold,
diff_merged() clicks-drop percent + lost traffic, severity grouping,
and the <2-snapshots clean exit.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- self-contained module loader (no shared conftest) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-alerting" / "scripts" / "alert.py"


def _load():
    spec = importlib.util.spec_from_file_location("alerting_alert", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


al = _load()


def _cat_index(alerts):
    return {a["category"]: a for a in alerts}


# --- diff_rank(): rank-drop threshold ----------------------------------------

def test_rank_drop_crosses_threshold():
    older = {"keywords": {"kw": {"position": 3}}}
    newer = {"keywords": {"kw": {"position": 9}}}  # dropped 6 >= threshold 3
    alerts = al.diff_rank(older, newer, rank_threshold=3)
    idx = _cat_index(alerts)
    assert "rank_drop" in idx
    assert idx["rank_drop"]["delta"] == -6


def test_rank_drop_below_threshold_no_alert():
    older = {"keywords": {"kw": {"position": 5}}}
    newer = {"keywords": {"kw": {"position": 7}}}  # dropped 2 < threshold 3
    alerts = al.diff_rank(older, newer, rank_threshold=3)
    assert alerts == []


def test_rank_lost_when_falls_out():
    older = {"keywords": {"kw": {"position": 2}}}
    newer = {"keywords": {"kw": {}}}  # no position now
    alerts = al.diff_rank(older, newer, rank_threshold=3)
    idx = _cat_index(alerts)
    assert "rank_lost" in idx
    # Was top-3 -> critical.
    assert idx["rank_lost"]["severity"] == "critical"


def test_rank_gained_when_enters():
    older = {"keywords": {"kw": {}}}
    newer = {"keywords": {"kw": {"position": 4}}}
    alerts = al.diff_rank(older, newer, rank_threshold=3)
    idx = _cat_index(alerts)
    assert "rank_gained" in idx
    assert idx["rank_gained"]["severity"] == "info"


def test_rank_gain_is_info():
    older = {"keywords": {"kw": {"position": 10}}}
    newer = {"keywords": {"kw": {"position": 4}}}  # improved 6
    alerts = al.diff_rank(older, newer, rank_threshold=3)
    idx = _cat_index(alerts)
    assert "rank_gain" in idx
    assert idx["rank_gain"]["severity"] == "info"
    assert idx["rank_gain"]["delta"] == 6


# --- diff_merged(): clicks-drop percent + lost traffic -----------------------

def test_merged_traffic_drop_percent():
    older = {"by_url": [{"url": "/p", "clicks": 100, "position": 4.0}], "by_query": []}
    newer = {"by_url": [{"url": "/p", "clicks": 60, "position": 4.0}], "by_query": []}
    # -40% with drop_pct 25 -> alert; 40% < 50% -> warning.
    alerts = al.diff_merged(older, newer, drop_pct=25.0, min_clicks=20.0)
    idx = _cat_index(alerts)
    assert "URL_traffic_drop" in idx
    assert idx["URL_traffic_drop"]["delta"] == -40.0
    assert idx["URL_traffic_drop"]["severity"] == "warning"


def test_merged_traffic_drop_severe_is_critical():
    older = {"by_url": [{"url": "/p", "clicks": 100, "position": 4.0}], "by_query": []}
    newer = {"by_url": [{"url": "/p", "clicks": 30, "position": 4.0}], "by_query": []}
    # -70% >= 50% -> critical.
    alerts = al.diff_merged(older, newer, drop_pct=25.0, min_clicks=20.0)
    idx = _cat_index(alerts)
    assert idx["URL_traffic_drop"]["severity"] == "critical"


def test_merged_traffic_lost_all_clicks():
    older = {"by_url": [{"url": "/p", "clicks": 120, "position": 8.0}], "by_query": []}
    newer = {"by_url": [{"url": "/p", "clicks": 0, "position": 18.0}], "by_query": []}
    alerts = al.diff_merged(older, newer, drop_pct=25.0, min_clicks=20.0)
    idx = _cat_index(alerts)
    assert "URL_traffic_lost" in idx
    assert idx["URL_traffic_lost"]["severity"] == "critical"
    assert idx["URL_traffic_lost"]["after"] == 0


def test_merged_below_min_clicks_skipped():
    # Prior clicks 10 < min_clicks 20 -> not evaluated for drop.
    older = {"by_url": [{"url": "/p", "clicks": 10, "position": 4.0}], "by_query": []}
    newer = {"by_url": [{"url": "/p", "clicks": 1, "position": 4.0}], "by_query": []}
    alerts = al.diff_merged(older, newer, drop_pct=25.0, min_clicks=20.0)
    assert alerts == []


def test_merged_query_rank_drop():
    older = {"by_url": [], "by_query": [{"query": "q", "clicks": 5, "position": 4.0}]}
    newer = {"by_url": [], "by_query": [{"query": "q", "clicks": 5, "position": 9.0}]}
    alerts = al.diff_merged(older, newer, drop_pct=25.0, min_clicks=20.0)
    idx = _cat_index(alerts)
    assert "query_rank_drop" in idx
    assert idx["query_rank_drop"]["delta"] == -5.0


# --- severity grouping --------------------------------------------------------

def test_group_by_severity_buckets():
    alerts = [
        {"severity": "critical", "delta": 5},
        {"severity": "warning", "delta": 1},
        {"severity": "info", "delta": 2},
        {"severity": "critical", "delta": 9},
    ]
    groups = al.group_by_severity(alerts)
    assert len(groups["critical"]) == 2
    assert len(groups["warning"]) == 1
    assert len(groups["info"]) == 1


def test_sort_alerts_orders_by_severity_then_delta():
    alerts = [
        {"severity": "info", "delta": 100},
        {"severity": "critical", "delta": 1},
        {"severity": "critical", "delta": 50},
        {"severity": "warning", "delta": 5},
    ]
    ordered = al.sort_alerts(alerts)
    sevs = [a["severity"] for a in ordered]
    assert sevs == ["critical", "critical", "warning", "info"]
    # Within critical, larger absolute delta comes first.
    assert ordered[0]["delta"] == 50
    assert ordered[1]["delta"] == 1


# --- demo fixture sanity ------------------------------------------------------

def test_demo_merged_diff_has_expected_severities():
    older, newer = al.demo_snapshots()
    alerts = al.diff_merged(older, newer, 25.0, 20.0)
    groups = al.group_by_severity(al.sort_alerts(alerts))
    # /blog/old-post lost all clicks and "best seo tool" halved -> >=2 critical.
    assert len(groups["critical"]) >= 2
    cats = {a["category"] for a in alerts}
    assert "URL_traffic_lost" in cats


# --- < 2 snapshots clean exit -------------------------------------------------

def test_two_newest_returns_none_for_missing_dir(tmp_path):
    missing = tmp_path / "does-not-exist"
    assert al._two_newest(missing) is None


def test_two_newest_returns_none_for_single_snapshot(tmp_path):
    d = tmp_path / "snaps"
    d.mkdir()
    (d / "2026-06-01.json").write_text("{}")
    assert al._two_newest(d) is None


def test_two_newest_returns_pair_ordered(tmp_path):
    d = tmp_path / "snaps"
    d.mkdir()
    (d / "2026-06-01.json").write_text("{}")
    (d / "2026-06-08.json").write_text("{}")
    older, newer = al._two_newest(d)
    assert older.name == "2026-06-01.json"
    assert newer.name == "2026-06-08.json"


# --- smoke test: --demo via subprocess ---------------------------------------

def test_demo_smoke_writes_json():
    # alert.py writes to a cwd-relative data/alerts dir, so run from repo root.
    out_path = _REPO_ROOT / "data" / "alerts" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    data = json.loads(out_path.read_text())
    assert "alerts" in data
    assert "alerts_by_severity" in data
    assert data["alerts_found"] == len(data["alerts"])
