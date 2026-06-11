#!/usr/bin/env python3
"""
Money Keywords — deterministically find the expensive paid terms you could win
organically to cut your customer acquisition cost (CAC).

The pitch: every month you (or your competitors) buy clicks on high-CPC, high-
volume keywords. Some of those terms you do NOT yet rank for organically — so
the only way you get the click today is to pay for it. Win them with SEO and you
stop paying for those clicks. This skill surfaces that hit list and estimates the
monthly paid value you could replace by ranking organically instead.

This is the INVERSE of nod-paid-organic:
  - nod-paid-organic = wasted spend on terms you ALREADY rank top-3 for (stop paying).
  - nod-money-keywords = expensive terms you do NOT yet rank for (start winning).

Definition of a "money keyword" (pure rules, no LLM, repeatable):
  cpc      >= --min-cpc     (default 1.0)   -> commercially expensive click
  AND volume >= --min-volume (default 200)  -> enough monthly demand to matter
  AND organic position is weak (> 10 or not ranking)  -> you can only buy it today

Scoring — estimated monthly paid value you could replace:
  value = volume * CTR_at_target_position * cpc
where CTR_at_target_position comes from a fixed organic CTR curve for a realistic
achievable position (default: position 5 ~ 6% CTR; tune with --target-position).
It is the money you would stop spending if you ranked there organically. This is
clearly an ESTIMATE — real savings depend on whether you actually reach the target
position, SERP layout, and intent.

A secondary "almost there" list flags high-CPC terms where you already rank 4-10:
a small organic push there is a big, cheap paid saving.

Usage:
    python3 analyze.py --demo                          # bundled fixture, runs now
    python3 analyze.py                                 # newest merged dataset
    python3 analyze.py --merged data/merged/2026-06-11.json
    python3 analyze.py --min-cpc 2.0 --min-volume 500
    python3 analyze.py --target-position 3             # assume you can reach #3

Output:
    data/money-keywords/{YYYY-MM-DD}.json
        -> { meta, summary, money_keywords, almost_there }
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# Paths.
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_OUTPUT_DIR = _REPO_ROOT / "data" / "money-keywords"

# Position thresholds.
_WEAK_RANK = 10      # position > this (or no rank) -> you can only buy this click
_ALMOST_LOW = 4      # "almost there" band: positions 4..10 inclusive
_ALMOST_HIGH = 10

# Fixed organic CTR curve (share of clicks by position). Conservative, widely
# cited shape — used only to ESTIMATE reclaimable value, not as ground truth.
_CTR_CURVE = {
    1: 0.30,
    2: 0.15,
    3: 0.10,
    4: 0.08,
    5: 0.06,
    6: 0.045,
    7: 0.035,
    8: 0.028,
    9: 0.022,
    10: 0.018,
}
_DEFAULT_TARGET_POSITION = 5


# -- small helpers -----------------------------------------------------------

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


def ctr_at_position(position):
    """Return the CTR-curve value for an integer position (clamped to 1..10)."""
    pos = max(1, min(int(round(position)), 10))
    return _CTR_CURVE[pos]


# -- load merged by_query ----------------------------------------------------

def load_by_query(merged_path=None):
    """Return (by_query rows, merged meta) using nod-merger's load_merged().

    Keeps the data contract in one place: query, position, volume, cpc.
    """
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"))
    from merge import load_merged  # noqa: E402

    merged = load_merged(merged_path)
    return merged.get("by_query", []), merged.get("meta", {})


# -- detection + scoring (deterministic) -------------------------------------

def analyze(by_query, min_cpc, min_volume, target_position):
    """Split keywords into money_keywords and almost_there lists.

    money_keywords : cpc >= min_cpc AND volume >= min_volume AND weak organic
                     (position > 10 or not ranking). Scored by estimated monthly
                     paid value you could replace at the target position.
    almost_there   : cpc >= min_cpc AND volume >= min_volume AND position 4..10.
                     Already close — a small push is a big paid saving.

    Both lists are ranked by estimated reclaimable monthly value, descending.
    Pure rules — same input always yields the same output.
    """
    target_ctr = ctr_at_position(target_position)
    money, almost = [], []

    for row in by_query:
        volume = _to_float(row.get("volume"))
        cpc = _to_float(row.get("cpc"))
        # Need both commercial signals to judge a paid term.
        if volume is None or cpc is None:
            continue
        if cpc < min_cpc or volume < min_volume:
            continue

        pos = row.get("position")
        pos = float(pos) if pos is not None else None
        ranks = pos is not None

        # Estimated monthly paid value replaceable if you reach the target rank.
        est_value = round(volume * target_ctr * cpc, 2)

        item = {
            "keyword": row.get("query"),
            "volume": int(round(volume)),
            "cpc": round(cpc, 2),
            "current_position": round(pos, 1) if ranks else None,
            "ranks_organically": ranks,
            "target_position": int(round(target_position)),
            "assumed_ctr_at_target": round(target_ctr, 4),
            "est_reclaimable_monthly_value": est_value,
        }

        if not ranks or pos > _WEAK_RANK:
            where = "does not rank in the data" if not ranks else f"ranks #{pos:.1f}"
            item["rationale"] = (
                f"High-value paid term (CPC ${cpc:.2f}, {int(round(volume))} searches/mo) "
                f"where organic {where} (weaker than #{_WEAK_RANK}). Today you can only "
                f"buy this click. Rank at #{int(round(target_position))} and you replace "
                f"an estimated ${est_value:.2f}/mo of paid value."
            )
            money.append(item)
        elif _ALMOST_LOW <= pos <= _ALMOST_HIGH:
            item["rationale"] = (
                f"Almost there: organic sits at #{pos:.1f} on an expensive term "
                f"(CPC ${cpc:.2f}). A small push into the top of page one turns paid "
                f"clicks into free ones — an estimated ${est_value:.2f}/mo saving."
            )
            almost.append(item)
        # position <= 3 -> already won organically; not this skill's job
        # (that overlap is nod-paid-organic's wasted-spend case).

    money.sort(key=lambda x: -x["est_reclaimable_monthly_value"])
    almost.sort(key=lambda x: -x["est_reclaimable_monthly_value"])
    return money, almost


def build_summary(money, almost, min_cpc, min_volume, target_position):
    total_addressable = round(
        sum(x["est_reclaimable_monthly_value"] for x in money), 2
    )
    almost_value = round(
        sum(x["est_reclaimable_monthly_value"] for x in almost), 2
    )
    return {
        "money_keywords": len(money),
        "almost_there": len(almost),
        "total_addressable_monthly_value": total_addressable,
        "almost_there_monthly_value": almost_value,
        "min_cpc": min_cpc,
        "min_volume": min_volume,
        "target_position": int(round(target_position)),
        "assumed_ctr_at_target": round(ctr_at_position(target_position), 4),
    }


# -- output ------------------------------------------------------------------

def save_report(summary, money, almost, meta):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "generatedAt": str(date.today()),
            "note": ("Reclaimable monthly value is an ESTIMATE: volume * assumed CTR "
                     "at the target position * CPC. It assumes you actually reach the "
                     "target organic position and ignores SERP layout, brand vs non-brand "
                     "intent, and seasonality. Treat it as a prioritized hit list to win "
                     "organically, not a guaranteed saving. Complement to nod-paid-organic "
                     "(which finds wasted spend on terms you already rank top-3 for)."),
            **meta,
        },
        "summary": summary,
        "money_keywords": money,
        "almost_there": almost,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _print_table(title, rows):
    print(f"### {title} ({len(rows)})")
    print()
    if not rows:
        print("_None._\n")
        return
    print("| Keyword | Volume | CPC | Current pos | Est. reclaimable $/mo |")
    print("|---------|--------|-----|-------------|-----------------------|")
    for r in rows:
        pos = f"{r['current_position']:.1f}" if r["current_position"] is not None else "not ranking"
        print(f"| {r['keyword']} | {r['volume']} | ${r['cpc']:.2f} | "
              f"{pos} | ${r['est_reclaimable_monthly_value']:.2f} |")
    print()


def print_summary(summary, money, almost):
    print()
    print("## Money Keywords Report")
    print(f"**Date:** {date.today()} | "
          f"**Filters:** CPC >= ${summary['min_cpc']:.2f}, volume >= {summary['min_volume']} | "
          f"**Target position:** #{summary['target_position']} "
          f"(~{summary['assumed_ctr_at_target'] * 100:.1f}% CTR)")
    print()
    print(f"- Money keywords (don't rank, expensive):  {summary['money_keywords']}")
    print(f"- Total addressable paid value:            ${summary['total_addressable_monthly_value']:.2f}/mo (est.)")
    print(f"- Almost there (rank 4-10):                {summary['almost_there']}")
    print(f"- Almost-there paid value:                 ${summary['almost_there_monthly_value']:.2f}/mo (est.)")
    print()
    _print_table("Money keywords — stop paying, win these with SEO", money)
    _print_table("Almost there — small push, big paid saving (rank 4-10)", almost)
    print("_Reclaimable value is an estimate (volume x assumed CTR at the target "
          "position x CPC). This is the inverse of nod-paid-organic: here you do NOT "
          "yet rank, so winning these cuts CAC._")


# -- demo fixture ------------------------------------------------------------

def _demo_by_query():
    """Inline by_query rows covering every branch against fixed filters.

    No real merged dataset is needed on this machine.
    """
    rows = [
        # money keywords: expensive, in-demand, not ranking or weak (>10)
        {"query": "enterprise crm software", "position": None, "volume": 8100, "cpc": 14.20},
        {"query": "project management tool", "position": 18.4, "volume": 12000, "cpc": 9.50},
        {"query": "payroll software", "position": 27.0, "volume": 4400, "cpc": 11.30},
        {"query": "vpn for business", "position": None, "volume": 2900, "cpc": 6.10},
        # almost there: expensive, in-demand, position 4..10
        {"query": "time tracking app", "position": 6.2, "volume": 3600, "cpc": 7.80},
        {"query": "invoicing software", "position": 4.0, "volume": 5400, "cpc": 8.40},
        # excluded: already top-3 (nod-paid-organic territory, not here)
        {"query": "team chat app", "position": 2.1, "volume": 6600, "cpc": 5.90},
        # excluded: CPC too low
        {"query": "free notes app", "position": 22.0, "volume": 9000, "cpc": 0.30},
        # excluded: volume too low
        {"query": "niche b2b widget", "position": None, "volume": 90, "cpc": 12.00},
        # excluded: missing commercial signal (no cpc)
        {"query": "what is saas", "position": 15.0, "volume": 7000, "cpc": None},
    ]
    return rows, {"source": "demo fixture (inline by_query rows)"}


# -- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Money Keywords")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Find expensive paid terms you don't yet rank for, to cut CAC by winning them organically")
    parser.add_argument("--merged", help="Path to a merged dataset (default: newest in data/merged)")
    parser.add_argument("--demo", action="store_true",
                        help="Run on a bundled inline by_query fixture (no data/key needed)")
    parser.add_argument("--min-cpc", type=float, default=1.0,
                        help="Minimum CPC for a term to count as expensive (default: 1.0)")
    parser.add_argument("--min-volume", type=int, default=200,
                        help="Minimum monthly search volume (default: 200)")
    parser.add_argument("--target-position", type=float, default=_DEFAULT_TARGET_POSITION,
                        help="Realistic achievable organic position for the CTR estimate (default: 5)")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of tables")
    args = parser.parse_args()

    if args.min_cpc < 0 or args.min_volume < 0:
        print("Error: --min-cpc and --min-volume must be non-negative.", file=sys.stderr)
        sys.exit(1)

    # Resolve the by_query rows.
    if args.demo:
        by_query, source_meta = _demo_by_query()
    else:
        try:
            by_query, source_meta = load_by_query(args.merged)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print("Run nod-merger first (it provides volume/cpc/position in by_query):",
                  file=sys.stderr)
            print("  python3 .claude/skills/nod-merger/scripts/merge.py", file=sys.stderr)
            print("Or try: python3 analyze.py --demo", file=sys.stderr)
            sys.exit(1)

    money, almost = analyze(by_query, args.min_cpc, args.min_volume, args.target_position)
    summary = build_summary(money, almost, args.min_cpc, args.min_volume, args.target_position)
    meta = {
        "source": source_meta.get("source") or source_meta,
        "thresholds": {
            "min_cpc": args.min_cpc,
            "min_volume": args.min_volume,
            "weak_rank": _WEAK_RANK,
            "target_position": int(round(args.target_position)),
        },
    }
    out_path = save_report(summary, money, almost, meta)

    if args.raw:
        print(json.dumps({
            "summary": summary,
            "money_keywords": money,
            "almost_there": almost,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(summary, money, almost)

    print(f"\nReport saved to: {out_path}")
    print("Cost: 0 NodesHub tokens (local merged data only).")


if __name__ == "__main__":
    main()
