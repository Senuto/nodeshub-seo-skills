"""Unit + smoke tests for the nod-brief-builder skill (build.py).

Covers slugify, read_keywords dedup, the deterministic demo clustering
(group-by-shared-first-word), _normalize_clusters ordering, pick_primary
(volume-aware) selection, build_mapping (cluster -> page mapping with primary /
secondary roles), render_brief_md, and a --demo smoke test asserting the
mapping.json output is written with documented top-level keys.

Self-contained loader (no shared conftest) to avoid sibling-file collisions.
"""

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BUILD_PATH = (_REPO_ROOT / ".claude" / "skills" / "nod-brief-builder"
               / "scripts" / "build.py")


def _load_build():
    spec = importlib.util.spec_from_file_location("nod_brief_under_test", _BUILD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bb = _load_build()


# --- slugify -----------------------------------------------------------------

def test_slugify():
    assert bb.slugify("CRM Software!") == "crm-software"
    assert bb.slugify("  Email   Marketing  ") == "email-marketing"
    assert bb.slugify("###") == "cluster"  # empty after strip -> fallback


# --- read_keywords dedup -----------------------------------------------------

def test_read_keywords_from_string_dedupes_case_insensitive():
    args = argparse.Namespace(file=None, keywords="crm software, Best CRM, crm software, best crm")
    kws = bb.read_keywords(args)
    assert kws == ["crm software", "Best CRM"]  # order preserved, dups dropped


def test_read_keywords_from_file(tmp_path):
    f = tmp_path / "kw.txt"
    f.write_text("crm software\nbest crm\ncrm software\n\n", encoding="utf-8")
    args = argparse.Namespace(file=str(f), keywords=None)
    assert bb.read_keywords(args) == ["crm software", "best crm"]


# --- clustering (demo) + normalize ------------------------------------------

def test_cluster_demo_groups_by_first_word():
    keywords = ["crm software", "crm pricing", "email marketing", "email automation"]
    result = bb.cluster_demo(keywords)
    assert result["method"] == "demo"
    assert result["tokens_used"] == 0
    by_kw = {tuple(c["keywords"]) for c in result["clusters"]}
    # Two clusters: crm* and email*.
    assert len(result["clusters"]) == 2
    crm = [c for c in result["clusters"] if c["keywords"][0].startswith("crm")][0]
    assert set(crm["keywords"]) == {"crm software", "crm pricing"}


def test_normalize_clusters_drops_empty_and_sorts_by_size():
    clusters = [
        {"name": "small", "keywords": ["a"]},
        {"name": "empty", "keywords": []},
        {"name": "big", "keywords": ["b", "c", "d"]},
    ]
    out = bb._normalize_clusters(clusters)
    assert [c["name"] for c in out] == ["big", "small"]  # empties dropped, size desc


def test_normalize_clusters_defaults_name_to_first_keyword():
    out = bb._normalize_clusters([{"name": None, "keywords": ["alpha", "beta"]}])
    assert out[0]["name"] == "alpha"


# --- pick_primary ------------------------------------------------------------

def test_pick_primary_uses_highest_volume():
    cluster = {"name": "c", "keywords": ["a", "b", "c"]}
    volumes = {"a": 100, "b": 900, "c": 50}
    assert bb.pick_primary(cluster, volumes) == "b"


def test_pick_primary_falls_back_to_first_without_volumes():
    cluster = {"name": "c", "keywords": ["first", "second"]}
    assert bb.pick_primary(cluster, {}) == "first"
    # Volumes present but all zero -> still first keyword.
    assert bb.pick_primary(cluster, {"first": 0, "second": 0}) == "first"


# --- build_mapping -----------------------------------------------------------

def test_build_mapping_primary_secondary_and_index():
    clusters = [
        {"name": "CRM cluster", "keywords": ["crm software", "best crm", "crm pricing"]},
        {"name": "Email cluster", "keywords": ["email marketing"]},
    ]
    volumes = {"best crm": 1000, "crm software": 500}
    mapping = bb.build_mapping(clusters, volumes)
    pages = mapping["pages"]
    assert len(pages) == 2

    crm_page = pages[0]
    assert crm_page["cluster_id"] == 0
    assert crm_page["primary_keyword"] == "best crm"  # highest volume
    assert set(crm_page["secondary_keywords"]) == {"crm software", "crm pricing"}
    assert crm_page["page_slug"] == "crm-cluster"
    assert crm_page["keyword_count"] == 3

    index = mapping["keyword_to_page"]
    assert index["best crm"]["role"] == "primary"
    assert index["crm software"]["role"] == "secondary"
    assert index["email marketing"]["role"] == "primary"
    assert index["crm pricing"]["cluster_id"] == 0


# --- render_brief_md ---------------------------------------------------------

def test_render_brief_md_includes_primary_and_secondary():
    page = {
        "cluster_id": 0, "cluster_name": "CRM cluster", "page_slug": "crm-cluster",
        "primary_keyword": "best crm",
        "secondary_keywords": ["crm software", "crm pricing"],
        "keyword_count": 3,
    }
    research = bb.research_mock("best crm")
    md = bb.render_brief_md(page, research)
    assert "# Content Brief: CRM cluster" in md
    assert "**Primary keyword:** best crm" in md
    assert "crm software" in md
    assert "MOCKED DEMO OUTPUT" in md  # mocked flag surfaces the warning


# --- smoke test (--demo) -----------------------------------------------------

def test_demo_smoke_writes_mapping():
    out_path = _REPO_ROOT / "data" / "briefs" / "demo" / "mapping.json"
    proc = subprocess.run(
        [sys.executable, str(_BUILD_PATH), "--demo"],
        cwd=str(_REPO_ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text())
    for key in ("method", "input_keyword_count", "pages", "keyword_to_page"):
        assert key in data
    assert data["method"] == "demo"
    assert isinstance(data["pages"], list) and len(data["pages"]) >= 1
