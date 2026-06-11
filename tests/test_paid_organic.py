"""Unit + smoke tests for the nod-paid-organic skill (analyze.py).

Covers normalize_keyword, currency/number parsing, load_paid_csv aggregation
of duplicate keywords, classification (wasted = paid + organic pos <= 3;
justified = pos > 10 or not ranking; defend = pos 4-10), reclaimable-spend
summary math, and a --demo smoke test asserting the report JSON is written
with documented top-level keys.

Self-contained loader (no shared conftest) to avoid sibling-file collisions.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANALYZE_PATH = (_REPO_ROOT / ".claude" / "skills" / "nod-paid-organic"
                 / "scripts" / "analyze.py")


def _load_analyze():
    spec = importlib.util.spec_from_file_location("nod_paid_under_test", _ANALYZE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pao = _load_analyze()


# --- parsing helpers ---------------------------------------------------------

def test_normalize_keyword():
    assert pao.normalize_keyword("  SEO   Tools ") == "seo tools"
    assert pao.normalize_keyword(None) == ""


def test_to_float_currency_and_thousands():
    assert pao._to_float("$3.45") == 3.45
    assert pao._to_float("1,240.50") == 1240.50
    assert pao._to_float(92) == 92.0
    assert pao._to_float("-") is None
    assert pao._to_float(None) is None


def test_to_int_rounds():
    assert pao._to_int("11.6") == 12
    assert pao._to_int(None) is None


# --- load_paid_csv -----------------------------------------------------------

def _write_csv(tmp_path, text):
    p = tmp_path / "ads.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_paid_csv_basic_and_alias_headers(tmp_path):
    csv_text = (
        "Keyword,Cost,Clicks,Conversions,Avg CPC\n"
        "seo tools,$100.00,40,3,2.50\n"
        "rank tracker,50,20,1,2.50\n"
    )
    rows = pao.load_paid_csv(_write_csv(tmp_path, csv_text))
    by_kw = {r["key"]: r for r in rows}
    assert by_kw["seo tools"]["cost"] == 100.0
    assert by_kw["seo tools"]["clicks"] == 40
    assert by_kw["seo tools"]["conversions"] == 3.0
    assert by_kw["rank tracker"]["cost"] == 50.0


def test_load_paid_csv_aggregates_duplicate_keywords(tmp_path):
    csv_text = (
        "keyword,cost,clicks,conversions\n"
        "seo tools,100,40,3\n"
        "SEO Tools,50,10,1\n"   # same normalized key -> summed
    )
    rows = pao.load_paid_csv(_write_csv(tmp_path, csv_text))
    assert len(rows) == 1
    assert rows[0]["cost"] == 150.0
    assert rows[0]["clicks"] == 50
    assert rows[0]["conversions"] == 4.0


def test_load_paid_csv_missing_keyword_column_raises(tmp_path):
    csv_text = "cost,clicks\n100,40\n"
    try:
        pao.load_paid_csv(_write_csv(tmp_path, csv_text))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "keyword" in str(exc).lower()


# --- classify ----------------------------------------------------------------

def _paid(keyword, cost=10.0, clicks=5, conversions=1.0, cpc=2.0):
    return {"keyword": keyword, "key": pao.normalize_keyword(keyword),
            "cost": cost, "clicks": clicks, "conversions": conversions, "cpc": cpc}


def test_classify_three_buckets():
    paid = [
        _paid("seo tools", cost=100),       # organic pos 2 -> wasted
        _paid("serp analysis", cost=40),    # organic pos 6 -> defend
        _paid("rank tracker", cost=30),     # organic pos 24 -> justified
        _paid("backlink checker", cost=20), # not ranking -> justified
    ]
    organic = {"seo tools": 2.0, "serp analysis": 6.0, "rank tracker": 24.0}
    wasted, justified, defend = pao.classify(paid, organic)
    assert {w["keyword"] for w in wasted} == {"seo tools"}
    assert {d["keyword"] for d in defend} == {"serp analysis"}
    assert {j["keyword"] for j in justified} == {"rank tracker", "backlink checker"}
    assert wasted[0]["classification"] == "wasted_spend_candidate"
    assert defend[0]["classification"] == "defend_monitor"
    assert all(j["classification"] == "justified_paid" for j in justified)


def test_classify_boundary_positions():
    # pos == 3 is top-3 -> wasted; pos == 10 is still defend; pos == 11 -> justified.
    paid = [_paid("a"), _paid("b"), _paid("c")]
    organic = {"a": 3.0, "b": 10.0, "c": 11.0}
    wasted, justified, defend = pao.classify(paid, organic)
    assert {w["keyword"] for w in wasted} == {"a"}
    assert {d["keyword"] for d in defend} == {"b"}
    assert {j["keyword"] for j in justified} == {"c"}


def test_classify_sorts_by_cost_desc():
    paid = [_paid("a", cost=10), _paid("b", cost=99)]
    organic = {"a": 1.0, "b": 2.0}  # both top-3 -> both wasted
    wasted, _, _ = pao.classify(paid, organic)
    assert [w["keyword"] for w in wasted] == ["b", "a"]


# --- build_summary -----------------------------------------------------------

def test_build_summary_reclaimable_math():
    paid = [_paid("a", cost=100), _paid("b", cost=40), _paid("c", cost=60)]
    organic = {"a": 2.0, "c": 1.0}  # a + c wasted, b justified
    wasted, justified, defend = pao.classify(paid, organic)
    summary = pao.build_summary(paid, wasted, justified, defend)
    assert summary["paid_keywords"] == 3
    assert summary["total_spend"] == 200.0
    assert summary["estimated_reclaimable_spend"] == 160.0  # 100 + 60
    assert summary["reclaimable_pct_of_spend"] == 80.0
    assert summary["wasted_spend_candidates"] == 2
    assert summary["justified_paid"] == 1


def test_build_summary_zero_spend_no_div_by_zero():
    summary = pao.build_summary([], [], [], [])
    assert summary["total_spend"] == 0.0
    assert summary["reclaimable_pct_of_spend"] == 0.0


# --- smoke test (--demo) -----------------------------------------------------

def test_demo_smoke_writes_report():
    out_path = _REPO_ROOT / "data" / "paid-organic" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_ANALYZE_PATH), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    for key in ("meta", "summary", "wasted_spend_candidates",
                "justified_paid", "defend_monitor"):
        assert key in data
    assert "estimated_reclaimable_spend" in data["summary"]
