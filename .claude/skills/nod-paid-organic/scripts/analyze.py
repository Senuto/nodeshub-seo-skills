#!/usr/bin/env python3
"""
Paid vs Organic — deterministic overlap analysis between Google Ads spend and
organic Search Console rankings for the same keywords.

The headline insight: keywords where you PAY in Google Ads but ALSO already rank
well organically (top 3). That paid cost is a wasted-spend candidate — you might
be buying clicks you would win for free. The flip side matters too: keywords
where organic is weak (or absent) are where paid is genuinely doing the work, so
keep paying. Mid positions sit in a defend/monitor grey zone.

Why a separate paid CSV is required: the merger's Ads view holds keyword METRICS
(volume / cpc / competition), which is search demand, not proof that you actually
run ads on those terms. To see real spend you need your Ads campaign export — the
keywords you bid on, with cost, paid clicks, and conversions. This skill ingests
that export and joins it with ORGANIC positions from the merger's by_query view.

Classification (pure rules, no LLM, repeatable):
  - Wasted spend candidate : paid cost AND organic position <= 3
  - Justified paid         : paid cost AND organic position > 10 (or not ranking)
  - Defend / monitor       : paid cost AND organic position 4-10

Usage:
    python3 analyze.py --demo                       # bundled fixture, runs now
    python3 analyze.py --paid-csv ads-campaign.csv  # join with newest merged
    python3 analyze.py --paid-csv x.csv --merged data/merged/2026-06-11.json
    python3 analyze.py --paid-csv x.csv --check-serp-ads --gl us --hl en

Output:
    data/paid-organic/{YYYY-MM-DD}.json  -> { meta, summary, wasted, justified, defend }
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

# Paths.
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_OUTPUT_DIR = _REPO_ROOT / "data" / "paid-organic"
_SAMPLE_PAID = _SKILL_DIR / "sample_paid.csv"

# Classification thresholds (organic position).
_TOP_RANK = 3        # position <= this -> you already rank well organically
_WEAK_RANK = 10      # position > this (or no rank) -> paid is doing the work


# -- normalization (mirrors nod-merger) --------------------------------------

def normalize_keyword(raw):
    """Lowercase + collapse whitespace, for joining paid <-> organic."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().lower())


def _to_float(value):
    """Parse '1,240.50', '$3.45', '5.1', 92 into a float; None on failure."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(value):
    f = _to_float(value)
    return int(round(f)) if f is not None else None


# -- paid keyword CSV ingest -------------------------------------------------
# Mirrors the column-normalization idea from scripts/fetch-google-ads.js: lower-
# case, strip punctuation from headers, then alias-match onto our fields.

_PAID_CSV_ALIASES = {
    "keyword": ["keyword", "query", "term", "phrase", "search term", "keywords"],
    "cost": ["cost", "spend", "total cost", "amount spent", "cost usd",
             "ad spend", "total spend"],
    "clicks": ["clicks", "paid clicks", "ad clicks"],
    "conversions": ["conversions", "conv", "conversion", "conv.", "goal completions"],
    "cpc": ["cpc", "avg cpc", "avg cpc usd", "cost per click", "average cpc"],
}


def _normalize_header(label):
    return re.sub(r"\s+", " ", re.sub(r"[._-]", " ", str(label).lower())).strip()


def _map_columns(header_row):
    """Build { field: column_index } from a header row using the alias table."""
    normalized = [_normalize_header(h) for h in header_row]
    col = {}
    for field, aliases in _PAID_CSV_ALIASES.items():
        for i, h in enumerate(normalized):
            if h in aliases:
                col[field] = i
                break
    return col


def load_paid_csv(path):
    """Read a paid-keywords export into normalized rows.

    Each row: { keyword, cost, clicks, conversions, cpc }. Rows without a
    keyword are dropped; duplicate keywords are aggregated (cost/clicks/conv
    summed) so a campaign that splits one term across ad groups still nets out
    to a single spend figure.
    """
    p = Path(path)
    rows = list(csv.reader(p.open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return []
    col = _map_columns(rows[0])
    if "keyword" not in col:
        raise ValueError(
            f"No keyword column found in {p.name}. "
            f"Expected one of: {', '.join(_PAID_CSV_ALIASES['keyword'])}."
        )

    def cell(row, field):
        i = col.get(field)
        return row[i] if i is not None and i < len(row) else None

    agg = {}
    order = []
    for r in rows[1:]:
        if not r:
            continue
        kw = (cell(r, "keyword") or "").strip()
        if not kw:
            continue
        key = normalize_keyword(kw)
        cost = _to_float(cell(r, "cost")) or 0.0
        clicks = _to_int(cell(r, "clicks")) or 0
        conv = _to_float(cell(r, "conversions")) or 0.0
        cpc = _to_float(cell(r, "cpc"))
        if key not in agg:
            agg[key] = {"keyword": kw, "key": key, "cost": 0.0,
                        "clicks": 0, "conversions": 0.0, "cpc": cpc}
            order.append(key)
        agg[key]["cost"] += cost
        agg[key]["clicks"] += clicks
        agg[key]["conversions"] += conv
        if agg[key]["cpc"] is None and cpc is not None:
            agg[key]["cpc"] = cpc

    return [agg[k] for k in order]


# -- organic positions from the merger ---------------------------------------

def load_organic_positions(merged_path=None):
    """Return { normalized_keyword: organic_position } from the merger by_query.

    Uses nod-merger's load_merged() so the data contract stays in one place.
    """
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"))
    from merge import load_merged  # noqa: E402

    merged = load_merged(merged_path)
    positions = {}
    for row in merged.get("by_query", []):
        key = normalize_keyword(row.get("query"))
        if not key:
            continue
        pos = row.get("position")
        if pos is not None:
            positions[key] = float(pos)
    return positions, merged.get("meta", {})


# -- classification (deterministic) ------------------------------------------

def classify(paid_rows, organic_positions):
    """Bucket each paid keyword by its organic position. Pure rules.

    Returns (wasted, justified, defend) — three lists of enriched rows.
    """
    wasted, justified, defend = [], [], []
    for row in paid_rows:
        pos = organic_positions.get(row["key"])
        item = {
            "keyword": row["keyword"],
            "cost": round(row["cost"], 2),
            "paid_clicks": row["clicks"],
            "conversions": round(row["conversions"], 2),
            "cpc": row["cpc"],
            "organic_position": pos,
            "ranks_organically": pos is not None,
        }
        if pos is not None and pos <= _TOP_RANK:
            item["classification"] = "wasted_spend_candidate"
            item["rationale"] = (
                f"You rank #{pos:.1f} organically (top {_TOP_RANK}) yet still pay "
                f"for this term. The ${item['cost']:.2f} here is potentially reclaimable."
            )
            wasted.append(item)
        elif pos is None or pos > _WEAK_RANK:
            where = "does not rank in the data" if pos is None else f"ranks #{pos:.1f}"
            item["classification"] = "justified_paid"
            item["rationale"] = (
                f"Organic {where} (weaker than #{_WEAK_RANK}). Paid is doing the work — keep it."
            )
            justified.append(item)
        else:
            item["classification"] = "defend_monitor"
            item["rationale"] = (
                f"Organic sits at #{pos:.1f} (positions {_TOP_RANK + 1}-{_WEAK_RANK}). "
                f"Borderline — watch position before cutting paid."
            )
            defend.append(item)

    # Money-shot first: heaviest reclaimable spend on top.
    wasted.sort(key=lambda x: -x["cost"])
    justified.sort(key=lambda x: -x["cost"])
    defend.sort(key=lambda x: -x["cost"])
    return wasted, justified, defend


def build_summary(paid_rows, wasted, justified, defend):
    total_spend = round(sum(r["cost"] for r in paid_rows), 2)
    reclaimable = round(sum(r["cost"] for r in wasted), 2)
    pct = round((reclaimable / total_spend * 100), 1) if total_spend > 0 else 0.0
    return {
        "paid_keywords": len(paid_rows),
        "total_spend": total_spend,
        "estimated_reclaimable_spend": reclaimable,
        "reclaimable_pct_of_spend": pct,
        "wasted_spend_candidates": len(wasted),
        "justified_paid": len(justified),
        "defend_monitor": len(defend),
    }


# -- optional: competitor ads on your organic terms --------------------------

def check_serp_ads(wasted, defend, gl, hl):
    """For terms where you rank organically, see if competitor ads sit on the
    SERP (a defend signal). Optional, costs 1 NodesHub token per checked term,
    and skips gracefully with no key. Annotates rows in place.
    """
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
    try:
        from client import NodeshubClient, NodeshubError
    except ImportError:
        print("  (check-serp-ads skipped: NodesHub client not found)")
        return
    try:
        client = NodeshubClient()
    except Exception:
        print("  (check-serp-ads skipped: no NodesHub API key configured)")
        return

    targets = wasted + defend
    print(f"\nChecking {len(targets)} organic-ranking terms for competitor ads "
          f"(cost: {len(targets)} tokens)...")
    for item in targets:
        try:
            serp = client.search(item["keyword"], gl=gl, hl=hl)
            data = serp.get("data", {}).get("results", serp.get("data", {}))
            ads = data.get("ads") or data.get("paid_results") or []
            item["competitor_ads_on_serp"] = len(ads)
            if ads:
                item["rationale"] += (
                    f" {len(ads)} competitor ad(s) sit on this SERP — defend before pausing."
                )
            print(f"  {item['keyword']}: {len(ads)} ad(s) on SERP")
        except NodeshubError as exc:
            item["competitor_ads_on_serp"] = None
            print(f"  {item['keyword']}: SERP ads check failed ({exc})")


# -- output ------------------------------------------------------------------

def save_report(summary, wasted, justified, defend, meta):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "generatedAt": str(date.today()),
            "note": ("Reclaimable spend is an ESTIMATE: it assumes paid clicks on "
                     "top-3 organic terms could be recovered organically. Real "
                     "recovery depends on SERP layout, brand vs non-brand intent, "
                     "and incrementality testing."),
            **meta,
        },
        "summary": summary,
        "wasted_spend_candidates": wasted,
        "justified_paid": justified,
        "defend_monitor": defend,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _print_table(title, rows):
    print(f"### {title} ({len(rows)})")
    print()
    if not rows:
        print("_None._\n")
        return
    print("| Keyword | Spend | Paid clicks | Conv. | Organic pos |")
    print("|---------|-------|-------------|-------|-------------|")
    for r in rows:
        pos = f"{r['organic_position']:.1f}" if r["organic_position"] is not None else "—"
        print(f"| {r['keyword']} | ${r['cost']:.2f} | {r['paid_clicks']} | "
              f"{r['conversions']:.0f} | {pos} |")
    print()


def print_summary(summary, wasted, justified, defend):
    print()
    print("## Paid vs Organic Report")
    print(f"**Date:** {date.today()} | **Paid keywords:** {summary['paid_keywords']}")
    print()
    print(f"- Total ad spend:            ${summary['total_spend']:.2f}")
    print(f"- Estimated reclaimable:     ${summary['estimated_reclaimable_spend']:.2f} "
          f"({summary['reclaimable_pct_of_spend']}% of spend)")
    print(f"- Wasted spend candidates:   {summary['wasted_spend_candidates']}")
    print(f"- Justified paid:            {summary['justified_paid']}")
    print(f"- Defend / monitor:          {summary['defend_monitor']}")
    print()
    _print_table("Wasted spend candidates (you already rank top-3)", wasted)
    _print_table("Justified paid (organic weak or absent)", justified)
    _print_table("Defend / monitor (organic mid positions)", defend)
    print("_Reclaimable spend is an estimate — confirm with incrementality testing "
          "before pausing campaigns._")


# -- demo fixture ------------------------------------------------------------

def _demo_organic_positions():
    """Inline organic positions (normalized keyword -> position) covering all
    three classes against sample_paid.csv. No real data needed on this machine.
    """
    return {
        "seo tools": 2.1,                 # top-3  -> wasted
        "keyword research": 1.4,          # top-3  -> wasted
        "content brief generator": 3.0,   # top-3  -> wasted
        "serp analysis": 6.8,             # 4-10   -> defend
        "rank tracker": 24.5,             # >10    -> justified
        "ai content detector": 14.2,      # >10    -> justified
        # "backlink checker" intentionally absent -> justified (not ranking)
    }, {"source": "demo fixture (inline organic positions)"}


# -- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Paid vs Organic")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Overlap analysis between Google Ads spend and organic GSC rankings")
    parser.add_argument("--paid-csv", help="Path to your Ads campaign keywords export (CSV)")
    parser.add_argument("--merged", help="Path to a merged dataset (default: newest in data/merged)")
    parser.add_argument("--demo", action="store_true",
                        help="Run on bundled sample_paid.csv + inline organic fixture")
    parser.add_argument("--check-serp-ads", action="store_true",
                        help="Check competitor ads on your organic terms (1 token/term)")
    parser.add_argument("--gl", default="us", help="Country code for --check-serp-ads (default: us)")
    parser.add_argument("--hl", default="en", help="Language code for --check-serp-ads (default: en)")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of tables")
    args = parser.parse_args()

    # Resolve paid keywords + organic positions.
    if args.demo:
        paid_path = _SAMPLE_PAID
        organic_positions, organic_meta = _demo_organic_positions()
    else:
        if not args.paid_csv:
            print("Error: --paid-csv is required (or use --demo).", file=sys.stderr)
            print("Pass your Google Ads campaign keywords export: the terms you bid on,",
                  file=sys.stderr)
            print("with cost / clicks / conversions columns.", file=sys.stderr)
            sys.exit(1)
        paid_path = Path(args.paid_csv)
        if not paid_path.is_file():
            print(f"Error: paid CSV not found: {paid_path}", file=sys.stderr)
            sys.exit(1)
        try:
            organic_positions, organic_meta = load_organic_positions(args.merged)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print("Run nod-merger first (it provides organic positions in by_query):",
                  file=sys.stderr)
            print("  python3 .claude/skills/nod-merger/scripts/merge.py", file=sys.stderr)
            sys.exit(1)

    try:
        paid_rows = load_paid_csv(paid_path)
    except (ValueError, OSError) as exc:
        print(f"Error reading paid CSV: {exc}", file=sys.stderr)
        sys.exit(1)

    if not paid_rows:
        print(f"No paid keywords parsed from {paid_path}.", file=sys.stderr)
        sys.exit(1)

    wasted, justified, defend = classify(paid_rows, organic_positions)

    if args.check_serp_ads:
        check_serp_ads(wasted, defend, args.gl, args.hl)

    summary = build_summary(paid_rows, wasted, justified, defend)
    meta = {
        "paid_csv": str(paid_path),
        "organic_source": organic_meta.get("source") or organic_meta,
        "serp_ads_checked": bool(args.check_serp_ads),
        "thresholds": {"top_rank": _TOP_RANK, "weak_rank": _WEAK_RANK},
    }
    out_path = save_report(summary, wasted, justified, defend, meta)

    if args.raw:
        print(json.dumps({
            "summary": summary,
            "wasted_spend_candidates": wasted,
            "justified_paid": justified,
            "defend_monitor": defend,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(summary, wasted, justified, defend)

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
