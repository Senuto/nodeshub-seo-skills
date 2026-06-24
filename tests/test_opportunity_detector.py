"""Unit + smoke tests for the nod-opportunity-detector skill (detect.py).

Covers the striking-distance rule (position 5-15 + impressions floor), the
low-CTR-vs-expected rule, the high-impressions-no-conversions rule, the
expected_ctr curve, the priority sort order, and a --demo smoke test asserting
the report JSON is written with documented top-level keys.

Self-contained loader (no shared conftest) to avoid sibling-file collisions.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DETECT_PATH = (_REPO_ROOT / ".claude" / "skills" / "nod-opportunity-detector"
                / "scripts" / "detect.py")


def _load_detect():
    spec = importlib.util.spec_from_file_location("nod_opp_under_test", _DETECT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


opp = _load_detect()


# --- expected_ctr ------------------------------------------------------------

def test_expected_ctr_curve_and_tail():
    assert opp.expected_ctr(1) == 28.0
    assert opp.expected_ctr(3.2) == 11.0     # rounds to rank 3
    assert opp.expected_ctr(10) == 2.5
    assert opp.expected_ctr(20) == opp.CTR_TAIL_EXPECTED  # below table -> tail
    assert opp.expected_ctr(None) is None
    assert opp.expected_ctr(0.4) == 28.0     # rank floored to 1


# --- striking distance -------------------------------------------------------

def test_striking_distance_flags_position_5_to_15():
    rows = [
        {"query": "in-range", "position": 8.0, "impressions": 300, "clicks": 5},
        {"query": "too-good", "position": 3.0, "impressions": 300, "clicks": 5},   # < 5
        {"query": "too-deep", "position": 20.0, "impressions": 300, "clicks": 0},  # > 15
        {"query": "low-impr", "position": 8.0, "impressions": 10, "clicks": 0},    # below floor
    ]
    out = opp.rule_striking_distance(rows, "query", min_impressions=50)
    targets = {o["target"] for o in out}
    assert targets == {"in-range"}
    o = out[0]
    assert o["type"] == "striking_distance"
    assert o["evidence"]["position"] == 8.0
    assert o["evidence"]["impressions"] == 300


def test_striking_priority_higher_closer_to_page_one():
    rows_close = [{"url": "/a", "position": 5.0, "impressions": 100, "clicks": 0}]
    rows_far = [{"url": "/b", "position": 15.0, "impressions": 100, "clicks": 0}]
    close = opp.rule_striking_distance(rows_close, "url", 50)[0]["priority"]
    far = opp.rule_striking_distance(rows_far, "url", 50)[0]["priority"]
    assert close > far


def test_striking_distance_skips_missing_fields():
    rows = [{"query": "x", "position": None, "impressions": 500, "clicks": 0}]
    assert opp.rule_striking_distance(rows, "query", 50) == []


# --- low CTR vs position -----------------------------------------------------

def test_low_ctr_flags_material_shortfall():
    # Position 3 expects 11%; actual 2% is well below 0.6 * 11 = 6.6.
    rows = [{"url": "/a", "position": 3.0, "impressions": 5000, "ctr": 2.0}]
    out = opp.rule_low_ctr(rows, "url")
    assert len(out) == 1
    o = out[0]
    assert o["type"] == "low_ctr_vs_position"
    assert o["evidence"]["expected_ctr"] == 11.0
    assert o["evidence"]["ctr"] == 2.0


def test_low_ctr_ignores_acceptable_ctr():
    # Actual 9% is above 0.6 * 11 = 6.6 -> not flagged.
    rows = [{"url": "/a", "position": 3.0, "impressions": 5000, "ctr": 9.0}]
    assert opp.rule_low_ctr(rows, "url") == []


def test_low_ctr_ignores_low_impressions():
    # Below CTR_MIN_IMPRESSIONS the ratio is noise -> skipped.
    rows = [{"url": "/a", "position": 3.0, "impressions": 50, "ctr": 0.1}]
    assert opp.rule_low_ctr(rows, "url") == []


# --- high impressions, no conversions ---------------------------------------

def test_high_impr_no_conversions_flagged():
    rows = [{
        "url": "/a", "in_ga4": True, "conversions": 0,
        "impressions": 5000, "clicks": 200, "sessions": 180,
    }]
    out = opp.rule_high_impr_no_conversions(rows)
    assert len(out) == 1
    assert out[0]["type"] == "high_impr_no_conversions"
    assert out[0]["evidence"]["conversions"] == 0
    assert out[0]["evidence"]["clicks"] == 200


def test_high_impr_no_conversions_requires_ga4_and_conv_metric():
    no_ga4 = [{"url": "/a", "in_ga4": False, "conversions": 0,
               "impressions": 5000, "clicks": 200}]
    assert opp.rule_high_impr_no_conversions(no_ga4) == []
    conv_none = [{"url": "/a", "in_ga4": True, "conversions": None,
                  "impressions": 5000, "clicks": 200}]
    assert opp.rule_high_impr_no_conversions(conv_none) == []


def test_high_impr_no_conversions_respects_floors():
    # Below the impression / click floor it is not "high impressions".
    rows = [{"url": "/a", "in_ga4": True, "conversions": 0,
             "impressions": 500, "clicks": 10}]
    assert opp.rule_high_impr_no_conversions(rows) == []
    # With conversions present it is not a zero-conversion page.
    rows2 = [{"url": "/a", "in_ga4": True, "conversions": 5,
              "impressions": 5000, "clicks": 200}]
    assert opp.rule_high_impr_no_conversions(rows2) == []


# --- detect orchestration + sort --------------------------------------------

def test_detect_sorts_by_priority_descending():
    merged = {
        "by_query": [
            {"query": "near", "position": 5.0, "impressions": 1000, "clicks": 5, "ctr": 1.0},
            {"query": "far", "position": 15.0, "impressions": 1000, "clicks": 5, "ctr": 1.0},
        ],
        "by_url": [],
    }
    opps = opp.detect(merged, min_impressions=50, previous_by_url=None, cannibal_path=None)
    priorities = [o["priority"] for o in opps]
    assert priorities == sorted(priorities, reverse=True)
    assert len(opps) >= 2


# --- smoke test (--demo) -----------------------------------------------------

def test_demo_smoke_writes_report():
    out_path = _REPO_ROOT / "data" / "opportunities" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_DETECT_PATH), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    for key in ("date", "source", "counts", "opportunities_found", "opportunities"):
        assert key in data
    assert isinstance(data["opportunities"], list)
    assert data["opportunities_found"] == len(data["opportunities"])
