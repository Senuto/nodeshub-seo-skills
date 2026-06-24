#!/usr/bin/env python3
"""
Commercial Value — deterministically rank a keyword set by REVENUE potential,
not by traffic.

A keyword with high search volume can still be worth little money, and a smaller
keyword with a high CPC can be worth a lot. This lens scores every keyword by its
commercial value (a money proxy) and how far it sits from page one, then ranks
the set into Tier 1 / 2 / 3 so the client can decide what to work on FIRST by
revenue rather than by search volume.

Scoring (documented, pure rules — no LLM, same input always yields same output):

    commercial_value = volume * cpc

        Monetary demand. Volume is how many people search; CPC is what an
        advertiser will pay for one click, which is the market's own estimate of
        a click's worth. Their product is a clean proxy for the money on the
        table behind a keyword.

    opportunity_multiplier (from current organic position):

        not ranking / position > 20  -> 1.00  (full upside, nothing captured)
        page 2 (11 - 20)             -> 0.75  (high upside, close to page one)
        positions 4 - 10             -> 0.40  (medium upside, partly captured)
        top 3 (1 - 3)                -> 0.10  (low upside, already captured)

    priority = commercial_value * opportunity_multiplier

        The money behind the keyword, weighted by how much of it you have NOT
        captured yet. A keyword you already own at #1 has high commercial value
        but little priority — the revenue is already yours.

Tiers split the ranked set by priority: top third = Tier 1, middle = Tier 2,
bottom = Tier 3 (with sensible handling for small sets).

This complements nod-money-keywords: that skill is the paid-CAC-reduction angle
(rank organically for terms you currently pay for). This one is the general
prioritization lens for ANY keyword set, ranked or not.

Usage:
    python3 analyze.py                       # keywords from newest merged dataset (by_query)
    python3 analyze.py --file keywords.csv   # CSV: keyword, volume, cpc, position (position optional)
    python3 analyze.py --merged PATH         # explicit merged dataset JSON
    python3 analyze.py --demo                # bundled fixture (no data / key needed)
    python3 analyze.py --raw                 # print raw JSON instead of the table

Output:
    data/commercial-value/{YYYY-MM-DD}.json
Cost:
    0 NodesHub tokens. Reads local data and runs offline.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_OUTPUT_DIR = _REPO_ROOT / "data" / "commercial-value"
_SAMPLE_FILE = _SKILL_DIR / "sample_keywords.csv"


# ── Parsing helpers ───────────────────────────────────────────────────────

def _to_float(value, default=None):
    """Parse '4.29%', '$3.45', '1,300', 92 into a float; default on failure."""
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


def _to_int(value, default=None):
    f = _to_float(value, None)
    return int(round(f)) if f is not None else default


# ── Generic CSV ingest (mirrors fetch-google-ads.js / merger normalization) ─

_CSV_ALIASES = {
    "keyword": ["keyword", "query", "term", "phrase", "keywords"],
    "volume": ["volume", "avg monthly searches", "avg_monthly_searches",
               "search volume", "searches", "sv"],
    "cpc": ["cpc", "avg cpc", "avg_cpc", "cost per click", "cpc usd"],
    "position": ["position", "pos", "rank", "ranking", "current position",
                 "avg position", "average position"],
}


def load_csv(path):
    """Read a keyword CSV into rows of {keyword, volume, cpc, position}.

    keyword, volume, cpc are expected; position is optional (treated as not
    ranking when absent). Reuses the alias/normalization idea from the Ads
    fetcher so Google Ads, DataForSEO, and Senuto exports all work.
    """
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return []
    header = [re.sub(r"[._-]", " ", h.lower()).strip() for h in rows[0]]
    col = {}
    for field, aliases in _CSV_ALIASES.items():
        for i, h in enumerate(header):
            if h in aliases:
                col[field] = i
                break
    if "keyword" not in col:
        raise ValueError(
            "CSV has no keyword column. Expected a header like: "
            "keyword, volume, cpc, position. Found: " + ", ".join(header)
        )

    out, seen = [], set()
    for r in rows[1:]:
        if not r:
            continue
        kw = r[col["keyword"]].strip() if col["keyword"] < len(r) else ""
        if not kw or kw.lower() in seen:
            continue
        seen.add(kw.lower())
        out.append({
            "keyword": kw,
            "volume": _to_int(r[col["volume"]]) if "volume" in col and col["volume"] < len(r) else None,
            "cpc": _to_float(r[col["cpc"]]) if "cpc" in col and col["cpc"] < len(r) else None,
            "position": _to_float(r[col["position"]]) if "position" in col and col["position"] < len(r) else None,
        })
    return out


def load_from_merged(path):
    """Pull keywords from a merger dataset's by_query view."""
    data = json.loads(Path(path).read_text())
    rows = []
    for q in data.get("by_query", []):
        rows.append({
            "keyword": q.get("query"),
            "volume": _to_int(q.get("volume")),
            "cpc": _to_float(q.get("cpc")),
            "position": _to_float(q.get("position")),
        })
    return rows


def _newest_merged():
    if not _MERGED_DIR.exists():
        return None
    files = sorted(_MERGED_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


# ── Scoring ───────────────────────────────────────────────────────────────

def opportunity(position):
    """Return (label, multiplier) for a current organic position.

    A keyword you already rank well for has little upside left — the revenue is
    already captured. A keyword you do not rank for has all of it ahead.
    """
    if position is None or position > 20:
        return "full", 1.00
    if position > 10:          # page 2: 11 - 20
        return "high", 0.75
    if position > 3:           # positions 4 - 10
        return "medium", 0.40
    return "low", 0.10         # top 3


def score_keyword(row):
    """Attach commercial_value, opportunity, and priority to one keyword row.

    Keywords missing volume or cpc cannot be valued; they are scored at zero so
    they sort to the bottom rather than crashing the ranking.
    """
    volume = row.get("volume")
    cpc = row.get("cpc")
    position = row.get("position")

    valued = volume is not None and cpc is not None
    commercial_value = round(volume * cpc, 2) if valued else 0.0
    opp_label, opp_mult = opportunity(position)
    priority = round(commercial_value * opp_mult, 2)

    return {
        "keyword": row.get("keyword"),
        "volume": volume,
        "cpc": cpc,
        "position": position,
        "commercial_value": commercial_value,
        "opportunity": opp_label,
        "opportunity_multiplier": opp_mult,
        "priority": priority,
        "valued": valued,
    }


def assign_tiers(scored):
    """Sort by priority desc and split into Tier 1 / 2 / 3 by thirds.

    Small sets degrade gracefully: 1 keyword -> all Tier 1; 2 -> Tier 1 and 2.
    Keywords with zero priority (unvalued or already top-ranked, no demand) all
    land in Tier 3 regardless of the split, since there is no revenue to chase.
    """
    ranked = sorted(
        scored,
        key=lambda k: (-k["priority"], -k["commercial_value"]),
    )
    n = len(ranked)
    if n == 0:
        return ranked

    third = max(1, round(n / 3))
    for i, k in enumerate(ranked):
        if k["priority"] <= 0:
            k["tier"] = 3
        elif i < third:
            k["tier"] = 1
        elif i < 2 * third:
            k["tier"] = 2
        else:
            k["tier"] = 3
    return ranked


def summarize(ranked):
    """Totals: set-wide commercial value, priority, and Tier 1 concentration."""
    total_value = round(sum(k["commercial_value"] for k in ranked), 2)
    total_priority = round(sum(k["priority"] for k in ranked), 2)
    tier1 = [k for k in ranked if k.get("tier") == 1]
    tier1_value = round(sum(k["commercial_value"] for k in tier1), 2)
    tier1_priority = round(sum(k["priority"] for k in tier1), 2)
    share = round(100 * tier1_priority / total_priority, 1) if total_priority > 0 else 0.0
    return {
        "keywords": len(ranked),
        "total_commercial_value": total_value,
        "total_priority": total_priority,
        "tier1_count": len(tier1),
        "tier1_commercial_value": tier1_value,
        "tier1_priority": tier1_priority,
        "tier1_priority_share_pct": share,
    }


# ── Output ────────────────────────────────────────────────────────────────

def save_report(ranked, summary, meta):
    """Write the structured report to data/commercial-value/{date}.json."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "date": str(date.today()),
        "source": meta.get("source"),
        "formula": "priority = (volume * cpc) * opportunity_multiplier",
        "summary": summary,
        "keywords": ranked,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _fmt_money(value):
    return f"${value:,.0f}" if value else "$0"


def _fmt_cell(value, kind):
    if value is None:
        return "n/a"
    if kind == "int":
        return f"{value:,.0f}"
    if kind == "cpc":
        return f"${value:.2f}"
    if kind == "pos":
        return f"{value:.1f}"
    return str(value)


def print_summary(ranked, summary, meta):
    """Print a readable, tiered Markdown summary to stdout."""
    print()
    print("## Commercial Value Report")
    print(f"**Source:** {meta.get('source')} | **Date:** {date.today()}")
    print()

    if not ranked:
        print("No keywords to rank. Provide a CSV (keyword, volume, cpc, position) "
              "or a merged dataset with by_query Ads metrics.")
        return

    unvalued = sum(1 for k in ranked if not k["valued"])
    print(f"**Keywords:** {summary['keywords']}"
          + (f" ({unvalued} missing volume/cpc, scored 0)" if unvalued else ""))
    print(f"**Total commercial value:** {_fmt_money(summary['total_commercial_value'])} "
          f"(volume x cpc across the set)")
    print(f"**Tier 1 share of priority:** {summary['tier1_priority_share_pct']}% "
          f"in {summary['tier1_count']} keyword(s)")
    print()

    labels = {
        1: "Tier 1 — work on first (highest revenue priority)",
        2: "Tier 2 — second wave",
        3: "Tier 3 — low priority (small money or already captured)",
    }
    for tier in (1, 2, 3):
        members = [k for k in ranked if k.get("tier") == tier]
        if not members:
            continue
        print(f"### {labels[tier]}")
        print()
        print("| Keyword | Volume | CPC | Commercial value | Position | Opportunity | Priority |")
        print("|---------|--------|-----|------------------|----------|-------------|----------|")
        for k in members:
            pos = _fmt_cell(k["position"], "pos") if k["position"] is not None else "not ranking"
            print(f"| {k['keyword']} "
                  f"| {_fmt_cell(k['volume'], 'int')} "
                  f"| {_fmt_cell(k['cpc'], 'cpc')} "
                  f"| {_fmt_money(k['commercial_value'])} "
                  f"| {pos} "
                  f"| {k['opportunity']} "
                  f"| {_fmt_money(k['priority'])} |")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────

def resolve_rows(args):
    """Decide the input source and return (rows, source_label)."""
    if args.demo:
        return load_csv(_SAMPLE_FILE), str(_SAMPLE_FILE)
    if args.file:
        return load_csv(args.file), str(args.file)
    merged = Path(args.merged) if args.merged else _newest_merged()
    if merged is None or not Path(merged).is_file():
        return None, None
    return load_from_merged(merged), str(merged)


def main():
    # Banner first (CLAUDE.md rule). Suppress under --raw so stdout is pure JSON.
    if "--raw" not in sys.argv:
        try:
            sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
            from banner import print_banner
            print_banner("Commercial Value")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Rank a keyword set by revenue potential (volume x cpc x opportunity gap)")
    parser.add_argument("--file", help="CSV with columns keyword, volume, cpc, position (position optional)")
    parser.add_argument("--merged", help="Explicit merged dataset JSON (default: newest in data/merged)")
    parser.add_argument("--demo", action="store_true", help="Run on the bundled sample fixture")
    parser.add_argument("--raw", action="store_true", help="Print the raw JSON report instead of the table")
    args = parser.parse_args()

    try:
        rows, source = resolve_rows(args)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if rows is None:
        print("Error: no keyword source found.", file=sys.stderr)
        print("Provide --file keywords.csv (keyword, volume, cpc, position), or run the", file=sys.stderr)
        print("merger first (python3 .claude/skills/nod-merger/scripts/merge.py), or use --demo.",
              file=sys.stderr)
        sys.exit(1)

    scored = [score_keyword(r) for r in rows if r.get("keyword")]
    ranked = assign_tiers(scored)
    summary = summarize(ranked)
    meta = {"source": source}
    out_path = save_report(ranked, summary, meta)

    if args.raw:
        print(json.dumps({
            "date": str(date.today()),
            "source": source,
            "summary": summary,
            "keywords": ranked,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(ranked, summary, meta)
        print(f"\nReport saved to: {out_path}")
        print("Cost: 0 NodesHub tokens.")


if __name__ == "__main__":
    main()
