"""Unit + smoke tests for nod-aio/scripts/analyze.py.

Covers the deterministic core: classify() (cited/opportunity/gap/no_aio),
AIO presence rate, citation rate, and competitor citation frequency.
"""

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

# --- self-contained module loader (no shared conftest) -----------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".claude" / "skills" / "nod-aio" / "scripts" / "analyze.py"


def _load():
    spec = importlib.util.spec_from_file_location("aio_analyze", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aio = _load()


def _rec(kw, present, cited, organic):
    return aio.make_record(kw, present, cited, organic)


# --- classify(): per-keyword class -------------------------------------------

def test_classify_no_aio():
    rec = _rec("kw", False, [], ["other.com"])
    cls, you_cited, you_rank = aio.classify(rec, "example.com")
    assert cls == aio.CLASS_NO_AIO
    assert you_cited is False


def test_classify_cited():
    rec = _rec("kw", True, ["example.com", "moz.com"], ["example.com"])
    cls, you_cited, you_rank = aio.classify(rec, "example.com")
    assert cls == aio.CLASS_CITED
    assert you_cited is True


def test_classify_opportunity_present_not_cited_but_ranks():
    rec = _rec("kw", True, ["moz.com", "ahrefs.com"], ["moz.com", "example.com"])
    cls, you_cited, you_rank = aio.classify(rec, "example.com")
    assert cls == aio.CLASS_OPPORTUNITY
    assert you_cited is False
    assert you_rank is True


def test_classify_gap_present_not_cited_not_ranking():
    rec = _rec("kw", True, ["moz.com"], ["moz.com", "ahrefs.com"])
    cls, you_cited, you_rank = aio.classify(rec, "example.com")
    assert cls == aio.CLASS_GAP
    assert you_cited is False
    assert you_rank is False


def test_classify_subdomain_matches_domain():
    # blog.example.com should match example.com (subdomain rule).
    rec = _rec("kw", True, ["blog.example.com"], [])
    cls, _, _ = aio.classify(rec, "example.com")
    assert cls == aio.CLASS_CITED


# --- analyze(): rates and competitor frequency -------------------------------

def test_aio_presence_rate():
    recs = [
        _rec("a", True, ["x.com"], []),
        _rec("b", True, ["x.com"], []),
        _rec("c", False, [], []),
        _rec("d", False, [], []),
    ]
    _, summary, _ = aio.analyze(recs, "example.com")
    assert summary["aio_present_count"] == 2
    assert summary["aio_presence_rate"] == 0.5


def test_citation_rate_of_aio():
    # 3 AIO queries, you cited on 1 -> 0.333.
    recs = [
        _rec("a", True, ["example.com"], []),
        _rec("b", True, ["moz.com"], []),
        _rec("c", True, ["ahrefs.com"], []),
    ]
    _, summary, _ = aio.analyze(recs, "example.com")
    assert summary["aio_present_count"] == 3
    assert summary["you_cited_count"] == 1
    assert summary["citation_rate_of_aio"] == 0.333


def test_competitor_citation_frequency_excludes_own_domain():
    recs = [
        _rec("a", True, ["example.com", "ahrefs.com"], []),
        _rec("b", True, ["ahrefs.com", "moz.com"], []),
        _rec("c", True, ["ahrefs.com"], []),
    ]
    _, _, top = aio.analyze(recs, "example.com")
    freq = {row["domain"]: row["aio_citations"] for row in top}
    assert freq["ahrefs.com"] == 3
    assert freq["moz.com"] == 1
    # Own domain is excluded from competitor frequency.
    assert "example.com" not in freq
    # Sorted by citations desc -> ahrefs first.
    assert top[0]["domain"] == "ahrefs.com"


def test_no_aio_set_rates_zero():
    recs = [_rec("a", False, [], []), _rec("b", False, [], [])]
    _, summary, top = aio.analyze(recs, "example.com")
    assert summary["aio_presence_rate"] == 0.0
    assert summary["citation_rate_of_aio"] == 0.0
    assert top == []


def test_class_counts_sum_to_total():
    recs = [
        _rec("a", True, ["example.com"], []),         # cited
        _rec("b", True, ["x.com"], ["example.com"]),  # opportunity
        _rec("c", True, ["x.com"], ["x.com"]),        # gap
        _rec("d", False, [], []),                     # no_aio
    ]
    classified, summary, _ = aio.analyze(recs, "example.com")
    counts = summary["class_counts"]
    assert counts[aio.CLASS_CITED] == 1
    assert counts[aio.CLASS_OPPORTUNITY] == 1
    assert counts[aio.CLASS_GAP] == 1
    assert counts[aio.CLASS_NO_AIO] == 1
    assert sum(counts.values()) == len(classified)


def test_split_classes_buckets():
    recs = [
        _rec("zebra", True, ["example.com"], []),
        _rec("alpha", False, [], []),
    ]
    classified, _, _ = aio.analyze(recs, "example.com")
    buckets = aio.split_classes(classified)
    assert [r["keyword"] for r in buckets[aio.CLASS_CITED]] == ["zebra"]
    assert [r["keyword"] for r in buckets[aio.CLASS_NO_AIO]] == ["alpha"]


# --- demo fixture sanity ------------------------------------------------------

def test_demo_classes_match_design():
    recs = list(aio._demo_records("example.com").values())
    classified, summary, _ = aio.analyze(recs, "example.com")
    by_kw = {r["keyword"]: r["class"] for r in classified}
    assert by_kw["what is technical seo"] == aio.CLASS_CITED
    assert by_kw["best seo tools 2026"] == aio.CLASS_OPPORTUNITY
    assert by_kw["enterprise seo platform"] == aio.CLASS_GAP
    assert by_kw["seo agency near me"] == aio.CLASS_NO_AIO
    assert summary["aio_presence_rate"] == 0.8


# --- smoke test: --demo via subprocess ---------------------------------------

def test_demo_smoke_writes_json():
    out_path = _REPO_ROOT / "data" / "aio" / f"{date.today()}.json"
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--demo", "--domain", "example.com"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.is_file()
    data = json.loads(out_path.read_text())
    assert "summary" in data
    assert "classes" in data
    assert "keywords" in data
    assert data["summary"]["keyword_count"] == len(data["keywords"])
