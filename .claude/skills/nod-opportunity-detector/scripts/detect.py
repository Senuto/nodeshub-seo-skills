#!/usr/bin/env python3
"""
Opportunity Detector — deterministic SEO action engine.

Reads the merged GSC + GA4 + Ads dataset (produced by nod-merger) and emits a
prioritized list of SEO opportunities. Every rule is pure: the same merged file
always yields the same opportunities and the same priority scores. No LLM, no
network calls, 0 NodesHub tokens.

Rules implemented:
  - striking_distance    position 5-15 with enough impressions; the closer to
                         page 1, the higher the priority (quick ranking wins).
  - low_ctr_vs_position  actual CTR materially below the expected-CTR-by-position
                         curve (title / snippet rewrite opportunity).
  - high_impr_no_conv    URL with real impressions/clicks but zero GA4
                         conversions (intent / landing-page mismatch).
  - decaying_page        clicks dropped beyond a threshold versus the previous
                         merged snapshot (needs two or more snapshots).
  - cannibalization      high/medium conflicts folded in from the
                         nod-cannibalization report, if one exists.

Usage:
    python3 detect.py                         # newest data/merged/*.json
    python3 detect.py --file PATH             # specific merged dataset
    python3 detect.py --demo                  # bundled sample_merged.json
    python3 detect.py --min-impressions 100   # raise the striking-distance floor
    python3 detect.py --raw                    # print raw JSON instead of tables

Output:
    data/opportunities/{YYYY-MM-DD}.json  -> { date, source, counts, opportunities: [...] }
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# --- Paths -------------------------------------------------------------------
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGER_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_CANNIBAL_DIR = _REPO_ROOT / "data" / "cannibalization"
_OUTPUT_DIR = _REPO_ROOT / "data" / "opportunities"
_SAMPLE_FILE = _SKILL_DIR / "sample_merged.json"

# --- Tunable rule constants (no magic numbers buried in logic) ---------------
STRIKING_MIN_POS = 5.0
STRIKING_MAX_POS = 15.0
DEFAULT_MIN_IMPRESSIONS = 50

# Expected CTR by integer rank (organic desktop, conservative industry curve).
# Used to flag rows whose actual CTR sits materially below expectation.
EXPECTED_CTR_BY_POSITION = {
    1: 28.0, 2: 15.0, 3: 11.0, 4: 8.0, 5: 6.0,
    6: 4.5, 7: 3.5, 8: 3.0, 9: 2.8, 10: 2.5,
}
# Below this rank we assume a flat tail; CTR expectation is low and noisy.
CTR_TAIL_EXPECTED = 1.5
# Flag only when actual CTR is at most this fraction of expected (materially below).
CTR_SHORTFALL_RATIO = 0.6
CTR_MIN_IMPRESSIONS = 100  # CTR ratios are noise below this impression count.

NO_CONV_MIN_IMPRESSIONS = 1000  # "high impressions" floor for the conversion rule.
NO_CONV_MIN_CLICKS = 30         # also needs real traffic, not just impressions.

DECAY_DROP_RATIO = -0.25  # -25% clicks MoM flags a decaying page.
DECAY_MIN_PREV_CLICKS = 20  # ignore tiny pages where a drop is just noise.


# --- Parsing helpers ---------------------------------------------------------

def _to_float(value, default=None):
    """Parse '4.29%', '5.1', 92, None into a float; default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().rstrip("%")
    try:
        return float(text)
    except ValueError:
        return default


def _clamp(value, low=0, high=100):
    return max(low, min(high, value))


def load_merged_dataset(path):
    """Load a merged dataset via the merger's load_merged helper, else directly."""
    sys.path.insert(0, str(_MERGER_SCRIPTS))
    try:
        from merge import load_merged  # type: ignore
        return load_merged(str(path)) if path else load_merged(None)
    except ImportError:
        # Fallback: read the file (or newest) directly without the helper.
        target = path or _newest_merged()
        if target is None:
            raise FileNotFoundError(
                f"No merged dataset in {_MERGED_DIR}. Run nod-merger first."
            )
        return json.loads(Path(target).read_text())


def _newest_merged():
    if not _MERGED_DIR.exists():
        return None
    files = sorted(_MERGED_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


def _two_newest_merged():
    """Return (newest, previous) merged paths, or (newest, None) if only one."""
    if not _MERGED_DIR.exists():
        return None, None
    files = sorted(_MERGED_DIR.glob("*.json"), reverse=True)
    newest = files[0] if files else None
    previous = files[1] if len(files) > 1 else None
    return newest, previous


def _newest_cannibalization():
    if not _CANNIBAL_DIR.exists():
        return None
    files = sorted(_CANNIBAL_DIR.glob("*.json"), reverse=True)
    return files[0] if files else None


# --- Rules -------------------------------------------------------------------

def expected_ctr(position):
    """Expected CTR (%) for a given (possibly fractional) position."""
    if position is None:
        return None
    rank = int(round(position))
    if rank < 1:
        rank = 1
    return EXPECTED_CTR_BY_POSITION.get(rank, CTR_TAIL_EXPECTED)


def _striking_priority(position):
    """0-100 — closer to page 1 (lower position) scores higher within 5..15."""
    span = STRIKING_MAX_POS - STRIKING_MIN_POS
    closeness = (STRIKING_MAX_POS - position) / span  # 1.0 at pos 5, 0.0 at pos 15
    return round(_clamp(40 + closeness * 55), 0)


def rule_striking_distance(rows, kind, min_impressions):
    """position 5-15 and impressions >= floor — a nudge could reach page 1."""
    out = []
    for r in rows:
        position = _to_float(r.get("position"))
        impressions = _to_float(r.get("impressions"))
        if position is None or impressions is None:
            continue
        if not (STRIKING_MIN_POS <= position <= STRIKING_MAX_POS):
            continue
        if impressions < min_impressions:
            continue
        target = r.get("query") if kind == "query" else r.get("url")
        priority = _striking_priority(position)
        out.append({
            "type": "striking_distance",
            "target": target,
            "evidence": {
                "kind": kind,
                "position": round(position, 1),
                "impressions": int(impressions),
                "clicks": int(_to_float(r.get("clicks"), 0)),
            },
            "priority": priority,
            "recommended_action": (
                f"On page 2 at position {position:.1f} with {int(impressions)} "
                f"impressions. Strengthen on-page relevance and internal links to "
                f"push '{target}' onto page 1."
            ),
        })
    return out


def rule_low_ctr(rows, kind):
    """Actual CTR materially below the expected-CTR-by-position curve."""
    out = []
    for r in rows:
        position = _to_float(r.get("position"))
        impressions = _to_float(r.get("impressions"))
        actual = _to_float(r.get("ctr"))
        if position is None or impressions is None or actual is None:
            continue
        if impressions < CTR_MIN_IMPRESSIONS:
            continue
        exp = expected_ctr(position)
        if exp is None or exp <= 0:
            continue
        if actual > exp * CTR_SHORTFALL_RATIO:
            continue  # CTR is acceptable for this position.
        target = r.get("query") if kind == "query" else r.get("url")
        # Priority scales with the size of the shortfall and the lost click volume.
        shortfall = (exp - actual) / exp  # 0..1
        lost_clicks = impressions * (exp - actual) / 100.0
        volume_weight = min(lost_clicks / 200.0, 1.0)
        priority = round(_clamp(45 + shortfall * 35 + volume_weight * 20))
        out.append({
            "type": "low_ctr_vs_position",
            "target": target,
            "evidence": {
                "kind": kind,
                "position": round(position, 1),
                "ctr": round(actual, 2),
                "expected_ctr": round(exp, 1),
                "impressions": int(impressions),
                "estimated_lost_clicks": int(round(lost_clicks)),
            },
            "priority": priority,
            "recommended_action": (
                f"CTR {actual:.1f}% sits well below the ~{exp:.0f}% expected at "
                f"position {position:.1f}. Rewrite the title tag and meta "
                f"description for '{target}' to win more clicks "
                f"(~{int(round(lost_clicks))} clicks/period on the table)."
            ),
        })
    return out


def rule_high_impr_no_conversions(by_url):
    """High impressions/clicks but zero GA4 conversions — intent/landing mismatch."""
    out = []
    for r in by_url:
        if not r.get("in_ga4"):
            continue  # conversions unknown without GA4.
        conversions = r.get("conversions")
        if conversions is None:
            continue  # GA4 present but conversion metric not exported.
        impressions = _to_float(r.get("impressions"), 0)
        clicks = _to_float(r.get("clicks"), 0)
        if conversions != 0:
            continue
        if impressions < NO_CONV_MIN_IMPRESSIONS or clicks < NO_CONV_MIN_CLICKS:
            continue
        # Priority scales with the wasted demand (clicks landing, none converting).
        priority = round(_clamp(50 + min(clicks / 500.0, 1.0) * 40))
        out.append({
            "type": "high_impr_no_conversions",
            "target": r.get("url"),
            "evidence": {
                "impressions": int(impressions),
                "clicks": int(clicks),
                "conversions": 0,
                "sessions": int(_to_float(r.get("sessions"), 0)),
            },
            "priority": priority,
            "recommended_action": (
                f"{int(clicks)} clicks and {int(impressions)} impressions but zero "
                f"conversions on '{r.get('url')}'. Check search-intent vs page "
                f"offer, add a clear CTA, and align the landing experience with "
                f"what these searchers want."
            ),
        })
    return out


def rule_decaying_pages(current_by_url, previous_by_url):
    """Flag URLs whose clicks dropped beyond the threshold vs the prior snapshot."""
    if previous_by_url is None:
        return []
    prev = {}
    for r in previous_by_url:
        url = r.get("url")
        if url is not None:
            prev[url] = _to_float(r.get("clicks"), 0)

    out = []
    for r in current_by_url:
        url = r.get("url")
        if url is None or url not in prev:
            continue
        prev_clicks = prev[url]
        curr_clicks = _to_float(r.get("clicks"), 0)
        if prev_clicks < DECAY_MIN_PREV_CLICKS:
            continue
        change = (curr_clicks - prev_clicks) / prev_clicks
        if change > DECAY_DROP_RATIO:
            continue  # not a material drop.
        drop_pct = round(change * 100, 1)
        # Bigger drop on a bigger page = higher priority.
        severity = min(abs(change), 1.0)
        volume_weight = min(prev_clicks / 500.0, 1.0)
        priority = round(_clamp(45 + severity * 35 + volume_weight * 20))
        out.append({
            "type": "decaying_page",
            "target": url,
            "evidence": {
                "previous_clicks": int(prev_clicks),
                "current_clicks": int(curr_clicks),
                "change_pct": drop_pct,
                "position": round(_to_float(r.get("position"), 0), 1),
            },
            "priority": priority,
            "recommended_action": (
                f"Clicks fell {drop_pct:.0f}% ({int(prev_clicks)} -> "
                f"{int(curr_clicks)}) on '{url}'. Refresh the content, check for a "
                f"SERP layout change or new competitor, and re-verify rankings."
            ),
        })
    return out


def rule_cannibalization_foldin(cannibal_path):
    """Fold high/medium cannibalization conflicts in as opportunities."""
    if cannibal_path is None:
        return []
    try:
        report = json.loads(Path(cannibal_path).read_text())
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for c in report.get("conflicts", []):
        severity = c.get("severity")
        if severity not in ("high", "medium"):
            continue
        # Map cannibalization severity onto the shared 0-100 priority scale.
        score = _to_float(c.get("severity_score"), 0) or 0
        priority = round(_clamp(40 + score * 50))
        out.append({
            "type": "cannibalization",
            "target": c.get("query"),
            "evidence": {
                "severity": severity,
                "severity_score": c.get("severity_score"),
                "competing_pages": [p.get("page") for p in c.get("pages", [])],
                "strongest_url": c.get("strongest_url"),
            },
            "priority": priority,
            "recommended_action": c.get("recommendation")
            or f"Resolve cannibalization on '{c.get('query')}' toward {c.get('strongest_url')}.",
        })
    return out


# --- Orchestration -----------------------------------------------------------

def detect(merged, min_impressions, previous_by_url, cannibal_path):
    """Run every rule and return opportunities sorted by priority descending."""
    by_url = merged.get("by_url", []) or []
    by_query = merged.get("by_query", []) or []

    opportunities = []
    opportunities += rule_striking_distance(by_query, "query", min_impressions)
    opportunities += rule_striking_distance(by_url, "url", min_impressions)
    opportunities += rule_low_ctr(by_query, "query")
    opportunities += rule_low_ctr(by_url, "url")
    opportunities += rule_high_impr_no_conversions(by_url)
    opportunities += rule_decaying_pages(by_url, previous_by_url)
    opportunities += rule_cannibalization_foldin(cannibal_path)

    # Deterministic sort: priority desc, then type, then target for stable ties.
    opportunities.sort(
        key=lambda o: (-o["priority"], o["type"], str(o["target"]))
    )
    return opportunities


# --- Output ------------------------------------------------------------------

def save_report(opportunities, meta):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "date": str(date.today()),
        "source": meta.get("source"),
        "min_impressions": meta.get("min_impressions"),
        "decay_compared_against": meta.get("decay_compared_against"),
        "cannibalization_source": meta.get("cannibalization_source"),
        "counts": _counts(opportunities),
        "opportunities_found": len(opportunities),
        "opportunities": opportunities,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _counts(opportunities):
    counts = {}
    for o in opportunities:
        counts[o["type"]] = counts.get(o["type"], 0) + 1
    return counts


_TYPE_LABELS = {
    "striking_distance": "Striking distance (page 2 -> page 1)",
    "low_ctr_vs_position": "Low CTR for position (title/snippet fix)",
    "high_impr_no_conversions": "Traffic without conversions (intent mismatch)",
    "decaying_page": "Decaying pages (clicks dropping)",
    "cannibalization": "Cannibalization (competing pages)",
}
_TYPE_ORDER = list(_TYPE_LABELS.keys())


def print_summary(opportunities, meta):
    print()
    print("## Opportunity Report")
    print(f"**Source:** {meta.get('source')} | **Date:** {date.today()} | "
          f"**Min impressions:** {meta.get('min_impressions')}")
    if meta.get("decay_note"):
        print(f"_{meta['decay_note']}_")
    print()

    if not opportunities:
        print("No opportunities detected from the merged dataset under the current "
              "thresholds.")
        return

    counts = _counts(opportunities)
    summary = ", ".join(f"{_TYPE_LABELS[t].split(' (')[0].lower()}: {counts[t]}"
                        for t in _TYPE_ORDER if t in counts)
    print(f"**Opportunities:** {len(opportunities)} ({summary})")
    print()

    for type_key in _TYPE_ORDER:
        group = [o for o in opportunities if o["type"] == type_key]
        if not group:
            continue
        print(f"### {_TYPE_LABELS[type_key]}")
        print()
        print("| Priority | Target | Evidence | Action |")
        print("|----------|--------|----------|--------|")
        for o in group:
            ev = _evidence_brief(o)
            action = o["recommended_action"].replace("\n", " ")
            if len(action) > 90:
                action = action[:87] + "..."
            print(f"| {int(o['priority'])} | {o['target']} | {ev} | {action} |")
        print()


def _evidence_brief(o):
    """One-line evidence string per opportunity type."""
    e = o["evidence"]
    t = o["type"]
    if t == "striking_distance":
        return f"pos {e['position']}, {e['impressions']} impr"
    if t == "low_ctr_vs_position":
        return f"CTR {e['ctr']}% vs ~{e['expected_ctr']}% @ pos {e['position']}"
    if t == "high_impr_no_conversions":
        return f"{e['clicks']} clicks, 0 conv"
    if t == "decaying_page":
        return f"{e['previous_clicks']} -> {e['current_clicks']} clicks ({e['change_pct']}%)"
    if t == "cannibalization":
        return f"{e['severity']} ({len(e['competing_pages'])} pages)"
    return ""


# --- Main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Opportunity Detector")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Deterministic SEO opportunity detector over the merged dataset")
    parser.add_argument("--file", help="Path to a merged dataset JSON (default: newest in data/merged)")
    parser.add_argument("--demo", action="store_true", help="Run on the bundled sample_merged.json fixture")
    parser.add_argument("--min-impressions", type=int, default=DEFAULT_MIN_IMPRESSIONS,
                        help=f"Striking-distance impression floor (default: {DEFAULT_MIN_IMPRESSIONS})")
    parser.add_argument("--raw", action="store_true", help="Print the raw JSON report instead of tables")
    args = parser.parse_args()

    # Resolve the merged source and the decay comparison snapshot.
    decay_note = None
    previous_by_url = None
    decay_compared_against = None

    if args.demo:
        source = _SAMPLE_FILE
        decay_note = ("Decay rule skipped on demo data: a single fixture snapshot, "
                      "no prior snapshot to compare against.")
        try:
            merged = json.loads(Path(source).read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Error: could not read fixture {source} ({exc})", file=sys.stderr)
            sys.exit(1)
    else:
        if args.file:
            source = Path(args.file)
            if not source.is_file():
                print(f"Error: file not found: {source}", file=sys.stderr)
                sys.exit(1)
        else:
            source = _newest_merged()
            if source is None:
                print("Error: no merged dataset in data/merged/.", file=sys.stderr)
                print("Run the /nod-merger skill first, or use --demo to try the fixture.",
                      file=sys.stderr)
                sys.exit(1)

        try:
            merged = load_merged_dataset(source)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            print(f"Error: could not load merged dataset ({exc})", file=sys.stderr)
            sys.exit(1)

        # Decay: compare the two newest snapshots if a prior one exists.
        newest, previous = _two_newest_merged()
        if previous is not None and str(source) == str(newest):
            try:
                prev_data = json.loads(Path(previous).read_text())
                previous_by_url = prev_data.get("by_url", [])
                decay_compared_against = str(previous)
            except (json.JSONDecodeError, OSError):
                previous_by_url = None
        if previous_by_url is None:
            decay_note = ("Decay rule skipped: only one merged snapshot found. "
                          "Re-run /nod-merger on another day to enable month-over-month "
                          "decay detection.")

    cannibal_path = None if args.demo else _newest_cannibalization()

    opportunities = detect(merged, args.min_impressions, previous_by_url, cannibal_path)

    meta = {
        "source": str(source),
        "min_impressions": args.min_impressions,
        "decay_compared_against": decay_compared_against,
        "cannibalization_source": str(cannibal_path) if cannibal_path else None,
        "decay_note": decay_note,
    }
    out_path = save_report(opportunities, meta)

    if args.raw:
        print(json.dumps({
            "date": str(date.today()),
            "source": str(source),
            "min_impressions": args.min_impressions,
            "counts": _counts(opportunities),
            "opportunities_found": len(opportunities),
            "opportunities": opportunities,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(opportunities, meta)

    print(f"\nReport saved to: {out_path}")
    print("Cost: 0 NodesHub tokens (deterministic, reads local merged data).")


if __name__ == "__main__":
    main()
