#!/usr/bin/env python3
"""
Brand Split — deterministically split Google Search Console demand into BRANDED
vs NON-BRANDED queries.

Branded queries are searches from people who already know the brand (navigational
intent). Non-branded queries are genuine new-demand searches — the acquisition
signal a marketer actually wants to grow. This script reports the split for
clicks and impressions (and conversions where the data allows), the top queries
in each bucket, and — when two snapshots exist — the trend in non-branded share.

No LLM, no API calls. Matching is pure string/regex, so the same input plus the
same brand terms always produces the same report.

Brand matching rule (documented, case-insensitive, word-boundary aware):
  A query is BRANDED if it matches ANY supplied brand term or brand regex.
    * --brand "term1,term2" — each term matches as a whole word/phrase using a
      word boundary on each side (so " acme " matches "acme shoes" but not
      "acmebackwards"). Domain-style terms (containing a dot) match as a
      substring, because boundaries do not behave well around dots.
    * --brand-regex PATTERN — a raw, case-insensitive regular expression for
      misspellings and variants (e.g. "acme|akme|acmecorp").
  Everything that matches no term and no regex is NON-BRANDED.

Usage:
    python3 analyze.py --brand "acme,acme corp"           # newest merged by_query
    python3 analyze.py --gsc PATH --brand-regex "acme|akme"
    python3 analyze.py --file queries.csv --brand "acme"  # CSV with a query column
    python3 analyze.py --demo                              # bundled fixture, no data needed

Output:
    data/brand-split/{YYYY-MM-DD}.json  -> { meta, totals, buckets, top, trend }
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

# --- Paths ------------------------------------------------------------------
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_GSC_DIR = _REPO_ROOT / "knowledge" / "metrics" / "seo"
_OUTPUT_DIR = _REPO_ROOT / "data" / "brand-split"
_MERGER_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"
_API_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"

# Built-in demo fixture: a realistic mix of branded and non-branded demand.
# "acme" is the brand; misspellings and the domain are branded too.
_DEMO_BRAND = "acme,acme corp,acmewidgets.com"
_DEMO_BRAND_REGEX = r"acme|akme"
_DEMO_QUERIES = [
    {"query": "acme", "clicks": 520, "impressions": 6100, "position": 1.2},
    {"query": "acme corp login", "clicks": 410, "impressions": 4800, "position": 1.4},
    {"query": "acme widgets reviews", "clicks": 180, "impressions": 3200, "position": 2.8},
    {"query": "akme widgets", "clicks": 60, "impressions": 1500, "position": 3.5},
    {"query": "acmewidgets.com pricing", "clicks": 95, "impressions": 1900, "position": 2.1},
    {"query": "best industrial widgets", "clicks": 240, "impressions": 14200, "position": 7.4},
    {"query": "widget supplier near me", "clicks": 130, "impressions": 8800, "position": 9.1},
    {"query": "how to choose a widget", "clicks": 310, "impressions": 21000, "position": 6.2},
    {"query": "cheap widgets bulk", "clicks": 85, "impressions": 5400, "position": 11.3},
    {"query": "widget vs gadget difference", "clicks": 150, "impressions": 9700, "position": 8.0},
    {"query": "industrial fasteners guide", "clicks": 70, "impressions": 4300, "position": 12.5},
]


# --- Numeric parsing --------------------------------------------------------

def _to_float(value, default=None):
    """Parse '4.29%', '5.1', 92 into a float; default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _to_int(value, default=0):
    f = _to_float(value, None)
    return int(round(f)) if f is not None else default


def _newest(directory, pattern):
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    return files[0] if files else None


# --- Brand matcher ----------------------------------------------------------

def build_matcher(brand_terms, brand_regex):
    """Build a deterministic, case-insensitive branded-query predicate.

    brand_terms: list of plain terms. A term containing a dot matches as a
        substring (domains); otherwise it matches on word boundaries.
    brand_regex: optional raw regex string (case-insensitive).

    Returns (predicate, compiled_patterns) where predicate(query) -> bool.
    """
    patterns = []
    for term in brand_terms:
        term = term.strip()
        if not term:
            continue
        if "." in term:
            # Domain-like term: substring match (boundaries misbehave on dots).
            patterns.append(re.compile(re.escape(term), re.IGNORECASE))
        else:
            # Whole-word / whole-phrase match, word-boundary aware.
            patterns.append(re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE))

    if brand_regex:
        patterns.append(re.compile(brand_regex, re.IGNORECASE))

    def predicate(query):
        if not query:
            return False
        return any(p.search(query) for p in patterns)

    return predicate, patterns


# --- Loading ----------------------------------------------------------------

def load_from_merged(path):
    """Load by_query rows from a merger output file."""
    data = json.loads(Path(path).read_text())
    rows = data.get("by_query", [])
    return _normalize_rows(rows), data


def load_from_gsc(path):
    """Load topQueries rows from a raw GSC export."""
    data = json.loads(Path(path).read_text())
    rows = data.get("topQueries", [])
    return _normalize_rows(rows), data


def load_from_csv(path):
    """Load query rows from a CSV with a query column (+ optional metrics)."""
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return [], {}
    header = [re.sub(r"[._-]", " ", h.lower()).strip() for h in rows[0]]
    aliases = {
        "query": ["query", "keyword", "term", "phrase", "queries"],
        "clicks": ["clicks", "click"],
        "impressions": ["impressions", "impression", "impr"],
        "position": ["position", "avg position", "pos"],
        "conversions": ["conversions", "conversion", "conv"],
    }
    col = {}
    for field, names in aliases.items():
        for i, h in enumerate(header):
            if h in names:
                col[field] = i
                break
    if "query" not in col:
        return [], {}

    out = []
    for r in rows[1:]:
        if not r:
            continue
        q = r[col["query"]].strip() if col["query"] < len(r) else ""
        if not q:
            continue
        out.append({
            "query": q,
            "clicks": _to_int(r[col["clicks"]]) if "clicks" in col and col["clicks"] < len(r) else 0,
            "impressions": _to_int(r[col["impressions"]]) if "impressions" in col and col["impressions"] < len(r) else 0,
            "position": _to_float(r[col["position"]]) if "position" in col and col["position"] < len(r) else None,
            "conversions": _to_int(r[col["conversions"]]) if "conversions" in col and col["conversions"] < len(r) else None,
        })
    return out, {}


def _normalize_rows(rows):
    """Normalize raw query rows into a consistent shape."""
    out = []
    for r in rows:
        q = r.get("query")
        if not q:
            continue
        out.append({
            "query": q,
            "clicks": _to_int(r.get("clicks")),
            "impressions": _to_int(r.get("impressions")),
            "position": _to_float(r.get("position")),
            "conversions": _to_int(r.get("conversions"), None) if r.get("conversions") is not None else None,
        })
    return out


def conversions_by_query(merged_data):
    """Best-effort per-query conversions via by_url joined on page.

    GSC has no query dimension for conversions, and by_query carries no GA4
    metrics, so true per-query conversions do not exist. We only attempt this
    when the merged dataset exposes queryPages mapping query -> page AND by_url
    carries conversions. If we cannot map it cleanly, we return None and skip
    the conversions split rather than fabricate it.
    """
    if not isinstance(merged_data, dict):
        return None
    by_url = merged_data.get("by_url")
    if not by_url:
        return None
    has_conv = any(r.get("conversions") is not None for r in by_url)
    if not has_conv:
        return None
    # We have URL-level conversions but no reliable query->page edges in by_query.
    # Without a query->page bridge we cannot attribute conversions per query
    # honestly, so we report URL-level conversions are present but unmapped.
    return None


# --- Split logic ------------------------------------------------------------

def _percent(part, whole):
    return round((part / whole) * 100, 1) if whole else 0.0


def _avg_position(rows):
    positions = [r["position"] for r in rows if r.get("position") is not None]
    if not positions:
        return None
    return round(sum(positions) / len(positions), 1)


def split_queries(rows, is_branded):
    """Partition rows into branded / non-branded and compute the split."""
    branded, non_branded = [], []
    for r in rows:
        (branded if is_branded(r["query"]) else non_branded).append(r)

    def bucket_totals(bucket):
        return {
            "queries": len(bucket),
            "clicks": sum(r["clicks"] for r in bucket),
            "impressions": sum(r["impressions"] for r in bucket),
            "avg_position": _avg_position(bucket),
        }

    b = bucket_totals(branded)
    n = bucket_totals(non_branded)
    total_clicks = b["clicks"] + n["clicks"]
    total_impr = b["impressions"] + n["impressions"]

    totals = {
        "total_queries": len(rows),
        "total_clicks": total_clicks,
        "total_impressions": total_impr,
        "branded": {
            **b,
            "clicks_pct": _percent(b["clicks"], total_clicks),
            "impressions_pct": _percent(b["impressions"], total_impr),
            "queries_pct": _percent(b["queries"], len(rows)),
        },
        "non_branded": {
            **n,
            "clicks_pct": _percent(n["clicks"], total_clicks),
            "impressions_pct": _percent(n["impressions"], total_impr),
            "queries_pct": _percent(n["queries"], len(rows)),
        },
    }
    return branded, non_branded, totals


def top_queries(bucket, key="clicks", limit=10):
    """Top queries in a bucket, sorted by clicks then impressions."""
    ordered = sorted(bucket, key=lambda r: (-r["clicks"], -r["impressions"]))
    return [
        {
            "query": r["query"],
            "clicks": r["clicks"],
            "impressions": r["impressions"],
            "position": r["position"],
        }
        for r in ordered[:limit]
    ]


# --- Trend (two newest snapshots) -------------------------------------------

def _snapshot_rows(path):
    """Load query rows from a snapshot file (merged or GSC), or None."""
    try:
        data = json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if "by_query" in data:
        return _normalize_rows(data.get("by_query", []))
    if "topQueries" in data:
        return _normalize_rows(data.get("topQueries", []))
    return None


def find_snapshots():
    """Return up to two newest snapshot paths (merged preferred, then GSC)."""
    merged = sorted(_MERGED_DIR.glob("*.json"), reverse=True) if _MERGED_DIR.exists() else []
    # Drop the -by_url.csv companion (glob already excludes .csv) — keep .json only.
    merged = [p for p in merged if p.suffix == ".json"]
    if len(merged) >= 2:
        return merged[:2]
    gsc = sorted(_GSC_DIR.glob("gsc-*.json"), reverse=True) if _GSC_DIR.exists() else []
    if len(gsc) >= 2:
        return gsc[:2]
    # Mixed: one merged + one GSC if that is all we have.
    combined = (merged + gsc)
    return combined[:2] if len(combined) >= 2 else combined


def compute_trend(is_branded):
    """Compute non-branded share trend between the two newest snapshots.

    Returns a dict, or a single-snapshot note. Never fabricates a second point.
    """
    snaps = find_snapshots()
    if len(snaps) < 2:
        return {
            "available": False,
            "note": "Only one snapshot found. Trend needs two or more dated snapshots "
                    "(data/merged/*.json or knowledge/metrics/seo/gsc-*.json). "
                    "Re-run the fetcher/merger on another date to unlock the trend.",
        }

    newer_path, older_path = snaps[0], snaps[1]
    newer_rows = _snapshot_rows(newer_path)
    older_rows = _snapshot_rows(older_path)
    if not newer_rows or not older_rows:
        return {
            "available": False,
            "note": "Found two snapshot files but could not read query rows from both.",
        }

    _, _, newer_totals = split_queries(newer_rows, is_branded)
    _, _, older_totals = split_queries(older_rows, is_branded)

    newer_share = newer_totals["non_branded"]["clicks_pct"]
    older_share = older_totals["non_branded"]["clicks_pct"]
    delta = round(newer_share - older_share, 1)

    if delta > 0:
        direction = "up"
        reading = ("Non-branded share of clicks is rising — genuine new acquisition "
                   "is growing relative to brand demand.")
    elif delta < 0:
        direction = "down"
        reading = ("Non-branded share of clicks is falling — growth is leaning more on "
                   "people who already know the brand. Check non-branded acquisition.")
    else:
        direction = "flat"
        reading = "Non-branded share of clicks is unchanged between the two snapshots."

    return {
        "available": True,
        "newer_snapshot": newer_path.name,
        "older_snapshot": older_path.name,
        "non_branded_clicks_pct_newer": newer_share,
        "non_branded_clicks_pct_older": older_share,
        "delta_pct_points": delta,
        "direction": direction,
        "reading": reading,
    }


# --- Output -----------------------------------------------------------------

def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _fmt_pos(p):
    return f"{p:.1f}" if p is not None else "-"


def print_summary(report):
    meta = report["meta"]
    totals = report["totals"]
    b = totals["branded"]
    n = totals["non_branded"]

    print()
    print("## Brand Split")
    print(f"**Source:** {meta['source']} | **Date:** {date.today()} | "
          f"**Brand terms:** {', '.join(meta['brand_terms']) or '(none)'}"
          + (f" | **Brand regex:** {meta['brand_regex']}" if meta["brand_regex"] else ""))
    print()

    print("| Bucket | Queries | Clicks | Clicks % | Impressions | Impr % | Avg pos |")
    print("|--------|---------|--------|----------|-------------|--------|---------|")
    print(f"| Branded | {b['queries']} | {b['clicks']} | {b['clicks_pct']}% | "
          f"{b['impressions']} | {b['impressions_pct']}% | {_fmt_pos(b['avg_position'])} |")
    print(f"| Non-branded | {n['queries']} | {n['clicks']} | {n['clicks_pct']}% | "
          f"{n['impressions']} | {n['impressions_pct']}% | {_fmt_pos(n['avg_position'])} |")
    print()
    print(f"**Acquisition signal:** non-branded clicks = {n['clicks']} "
          f"({n['clicks_pct']}% of all clicks). This is demand from people who did not "
          f"search the brand by name.")
    print()

    def _table(title, rows):
        print(f"### Top {title} queries")
        print()
        if not rows:
            print("_None._")
            print()
            return
        print("| Query | Clicks | Impressions | Position |")
        print("|-------|--------|-------------|----------|")
        for r in rows:
            print(f"| {r['query']} | {r['clicks']} | {r['impressions']} | {_fmt_pos(r['position'])} |")
        print()

    _table("branded", report["top"]["branded"])
    _table("non-branded", report["top"]["non_branded"])

    trend = report["trend"]
    print("### Trend (non-branded share of clicks)")
    print()
    if trend.get("available"):
        arrow = {"up": "▲", "down": "▼", "flat": "="}.get(trend["direction"], "")
        print(f"{trend['older_snapshot']}: {trend['non_branded_clicks_pct_older']}%  "
              f"->  {trend['newer_snapshot']}: {trend['non_branded_clicks_pct_newer']}%  "
              f"({arrow} {trend['delta_pct_points']:+} pts)")
        print()
        print(trend["reading"])
    else:
        print(trend["note"])
    print()

    if report["meta"].get("conversions_note"):
        print(f"_Conversions:_ {report['meta']['conversions_note']}")
        print()

    print("Cost: 0 NodesHub tokens (offline, deterministic).")


# --- Source resolution ------------------------------------------------------

def resolve_source(args):
    """Return (rows, raw_data, source_label). Each path is optional."""
    if args.demo:
        rows = _normalize_rows(_DEMO_QUERIES)
        return rows, {}, "demo fixture"
    if args.gsc:
        rows, raw = load_from_gsc(args.gsc)
        return rows, raw, str(args.gsc)
    if args.file:
        rows, raw = load_from_csv(args.file)
        return rows, raw, str(args.file)
    # Default: newest merger by_query.
    merged = _newest(_MERGED_DIR, "*.json")
    if merged is not None and merged.suffix == ".json":
        rows, raw = load_from_merged(merged)
        return rows, raw, str(merged)
    # Fall back to newest raw GSC export.
    gsc = _newest(_GSC_DIR, "gsc-*.json")
    if gsc is not None:
        rows, raw = load_from_gsc(gsc)
        return rows, raw, str(gsc)
    return [], {}, None


# --- CLI --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_API_SCRIPTS))
        from banner import print_banner
        print_banner("Brand Split")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Split GSC demand into branded vs non-branded queries")
    parser.add_argument("--gsc", help="Path to a raw GSC export JSON (uses topQueries)")
    parser.add_argument("--file", help="Path to a CSV with a query column")
    parser.add_argument("--brand", default="",
                        help='Comma-separated brand terms, e.g. "acme,acme corp,acme.com"')
    parser.add_argument("--brand-regex", default="",
                        help='Raw case-insensitive regex for brand variants/misspellings')
    parser.add_argument("--top", type=int, default=10, help="Top N queries per bucket (default: 10)")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the built-in mixed branded/non-branded fixture")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of tables")
    args = parser.parse_args()

    # Demo supplies its own brand terms so it runs with zero arguments.
    brand_str = args.brand
    brand_regex = args.brand_regex
    if args.demo and not brand_str and not brand_regex:
        brand_str = _DEMO_BRAND
        brand_regex = _DEMO_BRAND_REGEX

    brand_terms = [t.strip() for t in brand_str.split(",") if t.strip()]

    if not brand_terms and not brand_regex:
        print("Error: provide brand terms with --brand \"name,variant\" and/or "
              "--brand-regex PATTERN.", file=sys.stderr)
        print("Without a brand definition every query would count as non-branded.",
              file=sys.stderr)
        sys.exit(1)

    rows, raw_data, source = resolve_source(args)
    if source is None:
        print("Error: no query data found.", file=sys.stderr)
        print("Run the merger (data/merged/*.json), provide --gsc PATH, --file CSV, "
              "or try --demo.", file=sys.stderr)
        sys.exit(1)
    if not rows:
        print(f"Error: no queries parsed from {source}.", file=sys.stderr)
        sys.exit(1)

    is_branded, _ = build_matcher(brand_terms, brand_regex)

    branded, non_branded, totals = split_queries(rows, is_branded)
    trend = compute_trend(is_branded)

    conversions_note = None
    if isinstance(raw_data, dict) and raw_data.get("by_url"):
        if conversions_by_query(raw_data) is None and any(
                r.get("conversions") is not None for r in raw_data.get("by_url", [])):
            conversions_note = ("URL-level conversions exist in the merged dataset, but GSC "
                                "has no query dimension for conversions, so they cannot be "
                                "attributed per query. Conversions split skipped (no fabrication).")

    report = {
        "meta": {
            "date": str(date.today()),
            "source": source,
            "brand_terms": brand_terms,
            "brand_regex": brand_regex,
            "matching_rule": ("A query is branded if it matches any brand term (whole-word, "
                              "case-insensitive; domain-like terms match as substring) or the "
                              "brand regex. Everything else is non-branded."),
            "conversions_note": conversions_note,
        },
        "totals": totals,
        "top": {
            "branded": top_queries(branded, limit=args.top),
            "non_branded": top_queries(non_branded, limit=args.top),
        },
        "trend": trend,
    }

    out_path = save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)

    print()
    print(f"Report saved to: {out_path}")


if __name__ == "__main__":
    main()
