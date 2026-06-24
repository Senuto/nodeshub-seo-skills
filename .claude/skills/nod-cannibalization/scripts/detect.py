#!/usr/bin/env python3
"""
Cannibalization — deterministic keyword cannibalization detector for GSC data.

Reads the `queryPages` array from a GSC export (query x page pairs) and flags
queries where two or more distinct pages compete for the same query. Detection
is pure rule-based, so the same input always produces the same output. The only
optional network call is `--verify-serp`, which confirms the live ranking URL.

Usage:
    python3 detect.py                       # newest knowledge/metrics/seo/gsc-*.json
    python3 detect.py --file PATH           # specific export
    python3 detect.py --demo                # bundled fixture (no GSC data needed)
    python3 detect.py --min-impressions 25  # raise the noise floor
    python3 detect.py --verify-serp --gl us --hl en   # confirm live ranker (1 token/keyword)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
METRICS_DIR = _REPO_ROOT / "knowledge" / "metrics" / "seo"
SAMPLE_FILE = Path(__file__).resolve().parent / "sample_gsc.json"
OUTPUT_DIR = _REPO_ROOT / "data" / "cannibalization"


# --- parsing helpers ---------------------------------------------------------

def _to_float(value, default=0.0):
    """Parse GSC numeric strings ('12.3%', '4.5') and numbers into a float."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return default


def newest_export(metrics_dir=METRICS_DIR):
    """Return the most recent gsc-*.json export, or None if there is none."""
    if not metrics_dir.exists():
        return None
    files = sorted(metrics_dir.glob("gsc-*.json"), reverse=True)
    return files[0] if files else None


def load_query_pages(path):
    """Load and return the queryPages array from a GSC export file."""
    data = json.loads(Path(path).read_text())
    return data.get("queryPages")


# --- detection ---------------------------------------------------------------

def group_by_query(query_pages):
    """Group queryPages rows into {query: [page-row, ...]}."""
    grouped = {}
    for row in query_pages:
        query = row.get("query")
        page = row.get("page")
        if not query or not page:
            continue
        grouped.setdefault(query, []).append({
            "page": page,
            "clicks": _to_float(row.get("clicks")),
            "impressions": _to_float(row.get("impressions")),
            "ctr": str(row.get("ctr", "")),
            "position": _to_float(row.get("position")),
        })
    return grouped


def pick_strongest(pages):
    """Strongest URL: most clicks, then most impressions, then best (lowest) position."""
    return sorted(
        pages,
        key=lambda p: (-p["clicks"], -p["impressions"], p["position"]),
    )[0]


def _share_evenness(values):
    """Return 0..1 — how evenly a metric is split across pages (1 = perfectly even)."""
    total = sum(values)
    if total <= 0 or len(values) < 2:
        return 0.0
    n = len(values)
    # Normalized distance from a perfectly even split, inverted so even = 1.
    even_share = 1.0 / n
    spread = sum(abs((v / total) - even_share) for v in values)
    max_spread = 2.0 * (1.0 - even_share)  # worst case: one page owns everything
    if max_spread <= 0:
        return 0.0
    return 1.0 - (spread / max_spread)


def score_conflict(pages):
    """
    Deterministic severity for one cannibalized query.

    Higher when impressions and clicks are split evenly across pages (no clear
    winner) and when the top-impression page differs from the top-click page
    (the ranking URL flips). Returns (tag, score 0..1).
    """
    impressions = [p["impressions"] for p in pages]
    clicks = [p["clicks"] for p in pages]

    impr_even = _share_evenness(impressions)
    click_even = _share_evenness(clicks)

    # Flip: the page Google sends impressions to is not the page earning clicks.
    top_by_impr = max(pages, key=lambda p: (p["impressions"], -p["position"]))
    top_by_click = max(pages, key=lambda p: (p["clicks"], p["impressions"]))
    flip = 1.0 if top_by_impr["page"] != top_by_click["page"] else 0.0

    # More competing pages = messier, capped contribution.
    page_pressure = min(len(pages) - 2, 3) / 3.0  # 0 for 2 pages, up to 1 for 5+

    score = (0.45 * impr_even) + (0.30 * click_even) + (0.15 * flip) + (0.10 * page_pressure)
    score = round(min(score, 1.0), 3)

    if score >= 0.55:
        tag = "high"
    elif score >= 0.30:
        tag = "medium"
    else:
        tag = "low"
    return tag, score


def recommend(pages, strongest):
    """Rule-based recommendation for resolving one conflict."""
    impressions = [p["impressions"] for p in pages]
    impr_even = _share_evenness(impressions)
    total_clicks = sum(p["clicks"] for p in pages)

    if total_clicks == 0:
        # Nobody earns clicks — the pages dilute each other with no payoff.
        return (
            f"Consolidate: merge these pages into one and redirect the rest to "
            f"{strongest['page']}. None of them convert impressions into clicks."
        )
    if impr_even >= 0.6:
        # Impressions split near-evenly: Google can't decide which page to rank.
        return (
            f"Set canonical to the strongest URL ({strongest['page']}) and point "
            f"internal links there. Google is splitting impressions between near-equal pages."
        )
    # One page clearly leads — trim the weaker pages so they stop competing.
    return (
        f"De-optimize the weaker page(s) for this query and keep {strongest['page']} "
        f"as the target. One URL already leads; the others only dilute it."
    )


def detect(query_pages, min_impressions):
    """Return a list of conflict dicts, sorted by severity score descending."""
    grouped = group_by_query(query_pages)
    conflicts = []

    for query, pages in grouped.items():
        competing = [p for p in pages if p["impressions"] >= min_impressions]
        distinct = {p["page"] for p in competing}
        if len(distinct) < 2:
            continue

        # Collapse duplicate page rows (defensive) and sort strongest first.
        competing = sorted(competing, key=lambda p: (-p["clicks"], -p["impressions"], p["position"]))
        strongest = pick_strongest(competing)
        tag, score = score_conflict(competing)

        conflicts.append({
            "query": query,
            "pages": competing,
            "strongest_url": strongest["page"],
            "severity": tag,
            "severity_score": score,
            "recommendation": recommend(competing, strongest),
            "total_clicks": round(sum(p["clicks"] for p in competing), 1),
            "total_impressions": round(sum(p["impressions"] for p in competing), 1),
        })

    conflicts.sort(key=lambda c: (-c["severity_score"], -c["total_impressions"]))
    return conflicts


# --- optional live SERP verification ----------------------------------------

def verify_serp(conflicts, gl, hl):
    """
    Confirm which URL actually ranks live for each cannibalized query.
    Costs 1 NodesHub token per query. Skips gracefully without an API key.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "nod-nodeshub-api" / "scripts"))
    try:
        from client import NodeshubClient, NodeshubError
    except ImportError:
        print("  (verify-serp skipped: NodesHub client not found)")
        return

    try:
        client = NodeshubClient()
    except Exception:
        print("  (verify-serp skipped: no NodesHub API key configured)")
        return

    print(f"\nVerifying {len(conflicts)} queries against live SERP "
          f"(cost: {len(conflicts)} tokens)...")
    for c in conflicts:
        try:
            serp = client.search(c["query"], gl=gl, hl=hl)
            organic = serp.get("data", {}).get("results", {}).get("organic_results", [])
            own_pages = {p["page"] for p in c["pages"]}
            ranking_url = None
            for r in organic:
                url = r.get("url", r.get("link", "")) or ""
                for page in own_pages:
                    # Match on path suffix — exports store relative paths.
                    if page and (url.endswith(page) or page in url):
                        ranking_url = url
                        c["serp_ranking_url"] = url
                        c["serp_position"] = r.get("pos", r.get("global_pos"))
                        break
                if ranking_url:
                    break
            if not ranking_url:
                c["serp_ranking_url"] = None
                c["serp_position"] = None
            print(f"  {c['query']}: live ranker = {ranking_url or 'not in top 10'}")
        except NodeshubError as exc:
            c["serp_error"] = str(exc)
            print(f"  {c['query']}: SERP check failed ({exc})")


# --- output ------------------------------------------------------------------

def save_report(conflicts, meta):
    """Write the structured report to data/cannibalization/{date}.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "date": str(date.today()),
        "source": meta.get("source"),
        "min_impressions": meta.get("min_impressions"),
        "conflicts_found": len(conflicts),
        "conflicts": conflicts,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def print_summary(conflicts, meta):
    """Print a readable table summary to stdout."""
    print()
    print("## Cannibalization Report")
    print(f"**Source:** {meta.get('source')} | **Date:** {date.today()} | "
          f"**Min impressions:** {meta.get('min_impressions')}")
    print()

    if not conflicts:
        print("No cannibalization detected. No query has two or more pages above the "
              "impression floor.")
        return

    high = sum(1 for c in conflicts if c["severity"] == "high")
    medium = sum(1 for c in conflicts if c["severity"] == "medium")
    low = sum(1 for c in conflicts if c["severity"] == "low")
    print(f"**Conflicts:** {len(conflicts)} "
          f"(high: {high}, medium: {medium}, low: {low})")
    print()

    for c in conflicts:
        print(f"### \"{c['query']}\"  —  severity: {c['severity']} ({c['severity_score']})")
        print()
        print("| URL | Clicks | Impressions | Position | Strongest |")
        print("|-----|--------|-------------|----------|-----------|")
        for p in c["pages"]:
            mark = "yes" if p["page"] == c["strongest_url"] else ""
            print(f"| {p['page']} | {p['clicks']:.0f} | {p['impressions']:.0f} | "
                  f"{p['position']:.1f} | {mark} |")
        if c.get("serp_ranking_url") is not None or "serp_ranking_url" in c:
            live = c.get("serp_ranking_url") or "not in top 10"
            print(f"\n_Live SERP ranker:_ {live}")
        print(f"\n**Recommendation:** {c['recommendation']}")
        print()


# --- main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Detect keyword cannibalization from GSC data")
    parser.add_argument("--file", help="Path to a GSC export JSON (default: newest in knowledge/metrics/seo)")
    parser.add_argument("--demo", action="store_true", help="Run on bundled sample fixture")
    parser.add_argument("--min-impressions", type=int, default=10,
                        help="Minimum impressions for a page to count as competing (default: 10)")
    parser.add_argument("--verify-serp", action="store_true",
                        help="Confirm live ranking URL via NodesHub (1 token/query)")
    parser.add_argument("--gl", default="us", help="Country code for --verify-serp (default: us)")
    parser.add_argument("--hl", default="en", help="Language code for --verify-serp (default: en)")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON report instead of a table")
    args = parser.parse_args()

    # Resolve the source export.
    if args.demo:
        source = SAMPLE_FILE
    elif args.file:
        source = Path(args.file)
    else:
        source = newest_export()

    if source is None:
        print("Error: no GSC export found in knowledge/metrics/seo/.", file=sys.stderr)
        print("Run `npm run fetch-gsc` to create one, or use --demo to try the fixture.",
              file=sys.stderr)
        sys.exit(1)
    if not Path(source).is_file():
        print(f"Error: file not found: {source}", file=sys.stderr)
        sys.exit(1)

    try:
        query_pages = load_query_pages(source)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: could not read {source} ({exc})", file=sys.stderr)
        sys.exit(1)

    if query_pages is None:
        print(f"Error: '{source}' has no `queryPages` array.", file=sys.stderr)
        print("This export predates cannibalization support. Re-run `npm run fetch-gsc` "
              "to refresh it with query x page pairs.", file=sys.stderr)
        sys.exit(1)

    conflicts = detect(query_pages, args.min_impressions)

    if args.verify_serp and conflicts:
        verify_serp(conflicts, args.gl, args.hl)

    meta = {"source": str(source), "min_impressions": args.min_impressions}
    out_path = save_report(conflicts, meta)

    if args.raw:
        print(json.dumps({
            "date": str(date.today()),
            "source": str(source),
            "min_impressions": args.min_impressions,
            "conflicts_found": len(conflicts),
            "conflicts": conflicts,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(conflicts, meta)

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
