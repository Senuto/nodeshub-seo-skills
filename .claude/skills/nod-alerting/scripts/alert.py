#!/usr/bin/env python3
"""
Alerting — deterministic change monitor for SEO snapshots.

Turns one-off snapshots into monitoring. It reads what other skills already
saved (rank-tracker, visibility-monitor, merger), finds the two newest
snapshots for the chosen source, computes deltas, and raises alerts when a
ranking, visibility, or traffic change crosses a threshold. No new data is
fetched and no model judgment is used — the same two snapshots always yield
the same alerts.

Sources:
  rank        data/rank-history/{domain}/{date}.json   (per-keyword positions)
  visibility  data/visibility/{domain}/{date}.json     (weighted visibility score)
  merged      data/merged/{date}.json                  (by_url / by_query funnel)

Usage:
    python3 alert.py                          # auto-detect source (prefers merged)
    python3 alert.py --source rank --domain example.com
    python3 alert.py --source visibility --domain example.com
    python3 alert.py --source merged
    python3 alert.py --demo                    # bundled snapshots, shows drops + gains
    python3 alert.py --rank-threshold 5 --drop-pct 30 --vis-threshold 5

Output:
    data/alerts/{YYYY-MM-DD}.json  (severity-grouped alerts)
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# ── Paths (cwd-relative, matching the other nod- snapshot skills) ──────────
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
RANK_DIR = Path("data/rank-history")
VIS_DIR = Path("data/visibility")
MERGED_DIR = Path("data/merged")
OUTPUT_DIR = Path("data/alerts")

# Position past which a keyword counts as "out of the running" for lost/gained.
TOP_BAND = 10


# ── Snapshot discovery ─────────────────────────────────────────────────────

def _two_newest(directory, pattern="*.json"):
    """Return (older, newer) paths for the two most recent snapshots, or None."""
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    files = [f for f in files if f.is_file()]
    if len(files) < 2:
        return None
    newer, older = files[0], files[1]
    return older, newer


def _domain_dir(base, domain):
    """Resolve the domain-scoped snapshot directory (rank/visibility)."""
    return base / domain.lower().replace("www.", "")


def _list_domains(base):
    """Domains (subdirs) that have a snapshot folder under base."""
    if not base.exists():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def autodetect_source(domain):
    """Pick a source that has >= 2 snapshots, preferring merged, then rank, then visibility."""
    if _two_newest(MERGED_DIR):
        return "merged"
    for src, base in (("rank", RANK_DIR), ("visibility", VIS_DIR)):
        if domain:
            if _two_newest(_domain_dir(base, domain)):
                return src
        else:
            for d in _list_domains(base):
                if _two_newest(_domain_dir(base, d)):
                    return src
    return None


def resolve_snapshots(source, domain):
    """Return (older_path, newer_path) for the chosen source, or None if < 2 exist."""
    if source == "merged":
        return _two_newest(MERGED_DIR)

    base = RANK_DIR if source == "rank" else VIS_DIR
    if domain:
        return _two_newest(_domain_dir(base, domain))

    # No domain given: use the first domain that has two snapshots.
    for d in _list_domains(base):
        pair = _two_newest(_domain_dir(base, d))
        if pair:
            return pair
    return None


# ── Alert construction ─────────────────────────────────────────────────────

def _alert(severity, category, entity, before, after, delta, message):
    """Build one normalized alert record."""
    return {
        "severity": severity,
        "category": category,
        "entity": entity,
        "before": before,
        "after": after,
        "delta": delta,
        "message": message,
    }


# ── Rank source ────────────────────────────────────────────────────────────

def diff_rank(older, newer, rank_threshold):
    """
    Compare two rank-tracker snapshots keyed by keyword.

    Rank drops (position worsened by >= threshold), lost rankings (was in top,
    now absent), big gains, and recovered rankings.
    """
    alerts = []
    prev = older.get("keywords", {})
    curr = newer.get("keywords", {})

    for kw, c in curr.items():
        p = prev.get(kw, {})
        prev_pos = p.get("position")
        curr_pos = c.get("position")

        # Lost ranking: was in the top band, now absent.
        if prev_pos and not curr_pos:
            sev = "critical" if prev_pos <= 3 else "warning"
            alerts.append(_alert(
                sev, "rank_lost", kw, f"#{prev_pos}", "not ranked", "lost",
                f'"{kw}" fell out of the top {TOP_BAND} (was #{prev_pos}).',
            ))
            continue

        # Recovered: was absent, now ranks.
        if curr_pos and not prev_pos:
            alerts.append(_alert(
                "info", "rank_gained", kw, "not ranked", f"#{curr_pos}", "new",
                f'"{kw}" entered the top {TOP_BAND} at #{curr_pos}.',
            ))
            continue

        if not prev_pos or not curr_pos:
            continue

        # diff > 0 means improvement (lower position number is better).
        diff = prev_pos - curr_pos
        if diff <= -rank_threshold:
            drop = -diff
            sev = "critical" if curr_pos > TOP_BAND or prev_pos <= 3 else "warning"
            alerts.append(_alert(
                sev, "rank_drop", kw, f"#{prev_pos}", f"#{curr_pos}", -drop,
                f'"{kw}" dropped {drop} positions (#{prev_pos} -> #{curr_pos}).',
            ))
        elif diff >= rank_threshold:
            alerts.append(_alert(
                "info", "rank_gain", kw, f"#{prev_pos}", f"#{curr_pos}", diff,
                f'"{kw}" climbed {diff} positions (#{prev_pos} -> #{curr_pos}).',
            ))

    return alerts


# ── Visibility source ──────────────────────────────────────────────────────

def diff_visibility(older, newer, vis_threshold):
    """
    Compare two visibility-monitor snapshots: the overall score and per-keyword
    entries/exits from the top band.
    """
    alerts = []
    domain = newer.get("domain", older.get("domain", ""))

    prev_pct = float(older.get("visibility_pct", 0) or 0)
    curr_pct = float(newer.get("visibility_pct", 0) or 0)
    delta = round(curr_pct - prev_pct, 1)

    if abs(delta) >= vis_threshold:
        if delta < 0:
            sev = "critical" if abs(delta) >= 2 * vis_threshold else "warning"
            alerts.append(_alert(
                sev, "visibility_drop", domain or "site",
                f"{prev_pct}%", f"{curr_pct}%", delta,
                f"Visibility dropped {abs(delta)} points ({prev_pct}% -> {curr_pct}%).",
            ))
        else:
            alerts.append(_alert(
                "info", "visibility_gain", domain or "site",
                f"{prev_pct}%", f"{curr_pct}%", delta,
                f"Visibility rose {delta} points ({prev_pct}% -> {curr_pct}%).",
            ))

    # Per-keyword entries/exits from the top band.
    prev_kws = older.get("keywords", {})
    curr_kws = newer.get("keywords", {})
    for kw, c in curr_kws.items():
        prev_pos = prev_kws.get(kw, {}).get("position")
        curr_pos = c.get("position")
        if prev_pos and not curr_pos:
            sev = "critical" if prev_pos <= 3 else "warning"
            alerts.append(_alert(
                sev, "rank_lost", kw, f"#{prev_pos}", "not in top 10", "lost",
                f'"{kw}" left the top {TOP_BAND} (was #{prev_pos}).',
            ))
        elif curr_pos and not prev_pos:
            alerts.append(_alert(
                "info", "rank_gained", kw, "not in top 10", f"#{curr_pos}", "new",
                f'"{kw}" entered the top {TOP_BAND} at #{curr_pos}.',
            ))

    return alerts


# ── Merged source ──────────────────────────────────────────────────────────

def _index_by(rows, key):
    """Index a list of dict rows by a key field, last-wins on duplicates."""
    out = {}
    for r in rows or []:
        k = r.get(key)
        if k:
            out[k] = r
    return out


def diff_merged(older, newer, drop_pct, min_clicks):
    """
    Compare two merged snapshots. Traffic alerts on clicks dropping by
    >= drop_pct on URLs/queries that had meaningful prior clicks, plus position
    moves on by_query, plus big traffic gains and fully lost traffic.
    """
    alerts = []
    threshold = drop_pct / 100.0

    def _clicks(row):
        v = row.get("clicks")
        return float(v) if isinstance(v, (int, float)) else 0.0

    def traffic_pair(prev_rows, curr_rows, key, label):
        prev = _index_by(prev_rows, key)
        curr = _index_by(curr_rows, key)
        for entity, crow in curr.items():
            prow = prev.get(entity)
            if not prow:
                continue
            before = _clicks(prow)
            after = _clicks(crow)
            if before < min_clicks:
                continue

            change = after - before
            pct = change / before if before else 0.0

            if after == 0:
                alerts.append(_alert(
                    "critical", f"{label}_traffic_lost", entity,
                    int(before), 0, -int(before),
                    f"{label} {entity} lost all clicks "
                    f"({int(before)} -> 0).",
                ))
            elif pct <= -threshold:
                sev = "critical" if abs(pct) >= 0.5 else "warning"
                alerts.append(_alert(
                    sev, f"{label}_traffic_drop", entity,
                    int(before), int(after), round(pct * 100, 1),
                    f"{label} {entity} clicks fell {abs(round(pct * 100, 1))}% "
                    f"({int(before)} -> {int(after)}).",
                ))
            elif pct >= threshold:
                alerts.append(_alert(
                    "info", f"{label}_traffic_gain", entity,
                    int(before), int(after), round(pct * 100, 1),
                    f"{label} {entity} clicks rose {round(pct * 100, 1)}% "
                    f"({int(before)} -> {int(after)}).",
                ))

    traffic_pair(older.get("by_url", []), newer.get("by_url", []), "url", "URL")
    traffic_pair(older.get("by_query", []), newer.get("by_query", []), "query", "Query")

    # Position moves on by_query (query is the natural rank key in merged data).
    prev_q = _index_by(older.get("by_query", []), "query")
    for q, crow in _index_by(newer.get("by_query", []), "query").items():
        prow = prev_q.get(q)
        if not prow:
            continue
        pp = prow.get("position")
        cp = crow.get("position")
        if not isinstance(pp, (int, float)) or not isinstance(cp, (int, float)):
            continue
        diff = round(pp - cp, 1)  # positive = improved
        if diff <= -3:
            sev = "critical" if cp > TOP_BAND else "warning"
            alerts.append(_alert(
                sev, "query_rank_drop", q, f"#{round(pp, 1)}", f"#{round(cp, 1)}", diff,
                f'"{q}" average position worsened by {abs(diff)} '
                f"(#{round(pp, 1)} -> #{round(cp, 1)}).",
            ))
        elif diff >= 3:
            alerts.append(_alert(
                "info", "query_rank_gain", q, f"#{round(pp, 1)}", f"#{round(cp, 1)}", diff,
                f'"{q}" average position improved by {diff} '
                f"(#{round(pp, 1)} -> #{round(cp, 1)}).",
            ))

    return alerts


# ── Orchestration ──────────────────────────────────────────────────────────

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def sort_alerts(alerts):
    """Sort by severity, then by absolute numeric delta where available."""
    def _abs_delta(a):
        d = a.get("delta")
        return abs(d) if isinstance(d, (int, float)) else 0
    return sorted(alerts, key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 9), -_abs_delta(a)))


def group_by_severity(alerts):
    groups = {"critical": [], "warning": [], "info": []}
    for a in alerts:
        groups.setdefault(a["severity"], []).append(a)
    return groups


# ── Output ─────────────────────────────────────────────────────────────────

def save_report(report):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def print_summary(report):
    meta = report["meta"]
    groups = report["alerts_by_severity"]
    total = report["alerts_found"]

    print()
    print("## Alerting Report")
    print(f"**Source:** {meta['source']} | **Date:** {date.today()} | "
          f"**Compared:** {meta['from_date']} -> {meta['to_date']}")
    if meta.get("domain"):
        print(f"**Domain:** {meta['domain']}")
    print()

    if total == 0:
        print("No significant changes. Nothing crossed the configured thresholds "
              f"(rank >= {meta['rank_threshold']} positions, traffic >= "
              f"{meta['drop_pct']}%, visibility >= {meta['vis_threshold']} points).")
        return

    crit = len(groups["critical"])
    warn = len(groups["warning"])
    info = len(groups["info"])
    print(f"**Alerts:** {total} (critical: {crit}, warning: {warn}, info: {info})")
    print()

    titles = {
        "critical": "Critical",
        "warning": "Warning",
        "info": "Info (gains and recoveries)",
    }
    for sev in ("critical", "warning", "info"):
        items = groups[sev]
        if not items:
            continue
        print(f"### {titles[sev]} ({len(items)})")
        print()
        print("| Entity | Change | Delta | Detail |")
        print("|--------|--------|-------|--------|")
        for a in items:
            change = f"{a['before']} -> {a['after']}"
            delta = a["delta"]
            delta_str = f"{delta:+}" if isinstance(delta, (int, float)) else str(delta)
            print(f"| {a['entity']} | {change} | {delta_str} | {a['message']} |")
        print()


# ── Demo fixtures ──────────────────────────────────────────────────────────

def demo_snapshots():
    """Two small merged snapshots showing drops and gains. No data needed."""
    older = {
        "meta": {"generatedAt": "2026-06-01"},
        "by_url": [
            {"url": "/blog/seo-guide", "clicks": 800, "impressions": 20000, "position": 4.1},
            {"url": "/pricing", "clicks": 400, "impressions": 9000, "position": 3.0},
            {"url": "/blog/old-post", "clicks": 120, "impressions": 4000, "position": 8.0},
            {"url": "/features", "clicks": 60, "impressions": 2000, "position": 12.0},
        ],
        "by_query": [
            {"query": "seo guide", "clicks": 500, "impressions": 12000, "position": 3.2},
            {"query": "best seo tool", "clicks": 300, "impressions": 8000, "position": 5.0},
            {"query": "free keyword tool", "clicks": 200, "impressions": 6000, "position": 4.0},
            {"query": "pricing plans", "clicks": 90, "impressions": 3000, "position": 9.5},
        ],
    }
    newer = {
        "meta": {"generatedAt": "2026-06-08"},
        "by_url": [
            {"url": "/blog/seo-guide", "clicks": 850, "impressions": 21000, "position": 3.9},
            {"url": "/pricing", "clicks": 250, "impressions": 8800, "position": 3.4},
            {"url": "/blog/old-post", "clicks": 0, "impressions": 3800, "position": 18.0},
            {"url": "/features", "clicks": 150, "impressions": 5200, "position": 6.0},
        ],
        "by_query": [
            {"query": "seo guide", "clicks": 520, "impressions": 12500, "position": 3.1},
            {"query": "best seo tool", "clicks": 120, "impressions": 7800, "position": 9.0},
            {"query": "free keyword tool", "clicks": 280, "impressions": 6500, "position": 2.0},
            {"query": "pricing plans", "clicks": 95, "impressions": 3100, "position": 9.2},
        ],
    }
    return older, newer


# ── CLI ────────────────────────────────────────────────────────────────────

def main():
    # Banner first (CLAUDE.md rule). Suppress under --raw so stdout is pure JSON.
    if "--raw" not in sys.argv:
        try:
            sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
            from banner import print_banner
            print_banner("Alerting")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Alert on significant changes between the two newest SEO snapshots")
    parser.add_argument("--source", choices=["rank", "visibility", "merged"],
                        help="Which snapshot family to compare (default: auto-detect, prefers merged)")
    parser.add_argument("--domain", help="Domain for domain-scoped sources (rank, visibility)")
    parser.add_argument("--rank-threshold", type=int, default=3,
                        help="Positions a keyword must move to alert (default: 3)")
    parser.add_argument("--drop-pct", type=float, default=25.0,
                        help="Percent click change to alert on merged traffic (default: 25)")
    parser.add_argument("--vis-threshold", type=float, default=5.0,
                        help="Visibility-point change to alert (default: 5)")
    parser.add_argument("--min-clicks", type=float, default=20.0,
                        help="Minimum prior clicks for a merged traffic alert (default: 20)")
    parser.add_argument("--demo", action="store_true", help="Run on bundled in-script snapshots")
    parser.add_argument("--raw", action="store_true", help="Print the raw JSON report instead of a table")
    args = parser.parse_args()

    # Resolve the two snapshots.
    if args.demo:
        source = "merged"
        older, newer = demo_snapshots()
        from_date, to_date = "2026-06-01", "2026-06-08"
        domain = None
    else:
        source = args.source or autodetect_source(args.domain)
        if source is None:
            print("Need at least two snapshots to compare, and none were found.")
            print("Generate snapshots first with one of:")
            print("  - nod-rank-tracker  -> data/rank-history/{domain}/{date}.json")
            print("  - nod-visibility-monitor -> data/visibility/{domain}/{date}.json")
            print("  - nod-merger -> data/merged/{date}.json")
            print("Then re-run, or try: python3 alert.py --demo")
            sys.exit(0)

        pair = resolve_snapshots(source, args.domain)
        if pair is None:
            scope = f" for domain '{args.domain}'" if args.domain else ""
            print(f"Need at least two '{source}' snapshots{scope} to compare. "
                  "Found fewer than two.")
            print("Run the matching skill again on another day to create a second "
                  "snapshot, then re-run alerting. (No data is fabricated.)")
            sys.exit(0)

        older_path, newer_path = pair
        older = json.loads(older_path.read_text())
        newer = json.loads(newer_path.read_text())
        from_date = older.get("date") or older.get("meta", {}).get("generatedAt") or older_path.stem
        to_date = newer.get("date") or newer.get("meta", {}).get("generatedAt") or newer_path.stem
        domain = newer.get("domain") or args.domain

    # Compute deltas for the chosen source.
    if source == "rank":
        alerts = diff_rank(older, newer, args.rank_threshold)
    elif source == "visibility":
        alerts = diff_visibility(older, newer, args.vis_threshold)
    else:
        alerts = diff_merged(older, newer, args.drop_pct, args.min_clicks)

    alerts = sort_alerts(alerts)
    groups = group_by_severity(alerts)

    report = {
        "date": str(date.today()),
        "meta": {
            "source": source,
            "domain": domain,
            "from_date": from_date,
            "to_date": to_date,
            "rank_threshold": args.rank_threshold,
            "drop_pct": args.drop_pct,
            "vis_threshold": args.vis_threshold,
            "min_clicks": args.min_clicks,
            "tokens_used": 0,
        },
        "alerts_found": len(alerts),
        "alerts_by_severity": groups,
        "alerts": alerts,
    }

    out_path = save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)
        print(f"\nReport saved to: {out_path}")
        print("Cost: 0 NodesHub tokens (reads existing snapshots only).")


if __name__ == "__main__":
    main()
