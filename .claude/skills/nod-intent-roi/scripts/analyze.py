#!/usr/bin/env python3
"""
Intent ROI — tie search intent to actual conversions so content is prioritized
by ROI, not by traffic volume.

Answers one question: which intent types (informational / commercial /
transactional / navigational) actually convert for us, and where should the
next content investment go?

The aggregation is fully deterministic — no LLM, no model judgment. The same
merged dataset always yields the same intent table. The only optional network
call is `--classify`, which fills in missing intents via the NodesHub intent
classifier (2 tokens per keyword) and skips gracefully without a key.

Attribution chain (documented, with a stated approximation):
    query  ->  landing page  ->  conversions / sessions  ->  intent bucket

GA4 has no query dimension, so conversions and sessions are measured per URL
only. We attribute them to a query by associating the query with the page it
ranks for (GSC query x page pairs when present, otherwise a best-effort URL
match), then roll the URL's GA4 outcomes up into that query's intent bucket.
Because a single URL can rank for several queries of different intents, the
URL-level conversions are an approximation of per-intent conversions, not an
exact split. This is stated in every report.

Usage:
    python3 analyze.py                      # newest data/merged/{date}.json
    python3 analyze.py --merged PATH        # specific merged dataset
    python3 analyze.py --gsc PATH           # GSC export for query x page association
    python3 analyze.py --classify --gl us   # classify missing intents (2 tokens/kw)
    python3 analyze.py --demo               # bundled fixture, no key/data needed

Output:
    data/intent-roi/{YYYY-MM-DD}.json
"""

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGER_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"
_API_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_OUTPUT_DIR = _REPO_ROOT / "data" / "intent-roi"
_GSC_DIR = _REPO_ROOT / "knowledge" / "metrics" / "seo"
_SAMPLE = _SKILL_DIR / "sample_intent_roi.json"

# Canonical intent buckets. Anything we cannot map lands in "unknown".
_KNOWN_INTENTS = ("informational", "commercial", "transactional", "navigational")
_UNKNOWN = "unknown"


# ── Small parsing helpers ─────────────────────────────────────────────────

def _to_float(value, default=0.0):
    """Parse '4.29%', 3.45, '5' into a float; default on failure."""
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


def normalize_url(raw):
    """Match the merger's URL normalization so joins line up."""
    if not raw:
        return ""
    u = str(raw).strip()
    u = re.sub(r"^https?://", "", u, flags=re.IGNORECASE)
    if "/" in u and ("." in u.split("/")[0]):
        u = "/" + u.split("/", 1)[1]
    u = u.split("?")[0].split("#")[0]
    if not u.startswith("/"):
        u = "/" + u
    if len(u) > 1 and u.endswith("/"):
        u = u.rstrip("/")
    return u.lower()


def normalize_keyword(raw):
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().lower())


def canonical_intent(raw):
    """Map a raw intent label onto one of the four canonical buckets.

    Accepts common aliases (e.g. 'transaction', 'buy', 'info', 'brand') so SERP
    classifiers and hand-tagged data both line up. Unrecognized -> 'unknown'.
    """
    if not raw:
        return _UNKNOWN
    text = str(raw).strip().lower()
    if text in _KNOWN_INTENTS:
        return text
    aliases = {
        "info": "informational", "information": "informational",
        "informative": "informational", "know": "informational",
        "research": "informational",
        "commercial investigation": "commercial", "investigation": "commercial",
        "compare": "commercial", "comparison": "commercial",
        "consideration": "commercial",
        "transaction": "transactional", "buy": "transactional",
        "purchase": "transactional", "do": "transactional",
        "conversion": "transactional",
        "navigation": "navigational", "navigate": "navigational",
        "brand": "navigational", "branded": "navigational",
        "website": "navigational",
    }
    return aliases.get(text, _UNKNOWN)


# ── Loading ───────────────────────────────────────────────────────────────

def _newest(directory, pattern):
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    return files[0] if files else None


def load_json(path):
    return json.loads(Path(path).read_text())


def load_merged_dataset(path):
    """Load a merged dataset via the merger's load_merged helper, else directly."""
    sys.path.insert(0, str(_MERGER_SCRIPTS))
    try:
        from merge import load_merged  # type: ignore
        return load_merged(str(path)) if path else load_merged(None)
    except ImportError:
        target = path or _newest(_MERGED_DIR, "*.json")
        if target is None:
            raise FileNotFoundError(
                f"No merged dataset in {_MERGED_DIR}. Run nod-merger first."
            )
        return load_json(target)


def load_query_pages(path):
    """Return the GSC `queryPages` array (query x page pairs), or None."""
    if not path:
        return None
    try:
        data = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return data.get("queryPages")


# ── Query -> landing page association ──────────────────────────────────────

def build_query_page_map(by_query, by_url, query_pages):
    """Associate each query with the landing page it ranks for.

    Priority, strongest signal first:
      1. An explicit `page`/`landing_page` field already on the by_query row.
      2. GSC `queryPages` — the page with the most clicks for that exact query.
      3. Best-effort URL token match against by_url (coarse fallback).

    Returns {normalized_query: normalized_url}. Queries with no usable page
    association are left out (their outcomes simply do not get attributed).
    """
    url_keys = [normalize_url(r.get("url")) for r in by_url if r.get("url")]
    url_key_set = set(url_keys)

    # queryPages: pick the strongest page (most clicks) per query.
    qp_best = {}
    for row in query_pages or []:
        q = normalize_keyword(row.get("query"))
        page = normalize_url(row.get("page"))
        if not q or not page:
            continue
        clicks = _to_float(row.get("clicks"))
        prev = qp_best.get(q)
        if prev is None or clicks > prev[1]:
            qp_best[q] = (page, clicks)

    mapping = {}
    for row in by_query:
        q = normalize_keyword(row.get("query"))
        if not q:
            continue
        # 1. explicit association on the row.
        explicit = row.get("page") or row.get("landing_page")
        if explicit:
            mapping[q] = normalize_url(explicit)
            continue
        # 2. GSC query x page pairs.
        if q in qp_best and qp_best[q][0] in url_key_set:
            mapping[q] = qp_best[q][0]
            continue
        if q in qp_best:
            mapping[q] = qp_best[q][0]
            continue
        # 3. coarse token match against known URLs.
        match = _best_url_match(q, url_keys)
        if match:
            mapping[q] = match
    return mapping


def _best_url_match(query, url_keys):
    """Coarse fallback: the URL whose path shares the most word tokens with the
    query. Returns None when there is no overlap (so we never guess blindly)."""
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not q_tokens:
        return None
    best, best_score = None, 0
    for url in url_keys:
        u_tokens = set(re.findall(r"[a-z0-9]+", url.lower()))
        score = len(q_tokens & u_tokens)
        if score > best_score:
            best, best_score = url, score
    return best if best_score > 0 else None


# ── Intent resolution ─────────────────────────────────────────────────────

def resolve_intents(by_query, classify, gl, hl):
    """Return {normalized_query: canonical_intent}.

    Uses by_query.intent when present (SERP-enriched). Otherwise, when
    --classify is passed, calls the NodesHub intent classifier (2 tokens/kw).
    Without a key (or without --classify) the query stays 'unknown'.
    """
    intents = {}
    needs_classify = []
    for row in by_query:
        q = normalize_keyword(row.get("query"))
        if not q:
            continue
        raw = row.get("intent")
        if raw:
            intents[q] = canonical_intent(raw)
        else:
            intents[q] = _UNKNOWN
            needs_classify.append((q, row.get("query")))

    if classify and needs_classify:
        classified = _classify_missing(needs_classify, gl, hl)
        intents.update(classified)
    return intents


def _classify_missing(pairs, gl, hl):
    """Call NodesHub intent classifier for queries lacking an intent.

    Cost: 2 tokens per keyword. Skips quietly when the client or key is absent
    so the deterministic core is never blocked.
    """
    out = {}
    sys.path.insert(0, str(_API_SCRIPTS))
    try:
        from client import NodeshubClient, NodeshubError  # type: ignore
    except ImportError:
        print("  (--classify skipped: NodesHub client not found)", file=sys.stderr)
        return out
    try:
        client = NodeshubClient()
    except (Exception, SystemExit):
        # The client calls sys.exit() when no key is configured; treat that as a
        # graceful skip so the deterministic core still produces a report.
        print("  (--classify skipped: no NodesHub API key configured)", file=sys.stderr)
        return out

    print(f"\nClassifying {len(pairs)} queries via NodesHub "
          f"(cost: {2 * len(pairs)} tokens)...", file=sys.stderr)
    for norm_q, raw_q in pairs:
        try:
            res = client.classify_intent(raw_q, gl=gl, hl=hl)
            data = res.get("data", {})
            data = data.get("results", data) if isinstance(data, dict) else {}
            label = data.get("intent") or data.get("label")
            out[norm_q] = canonical_intent(label)
        except NodeshubError as exc:
            print(f"  (intent failed for '{raw_q}': {exc})", file=sys.stderr)
            out[norm_q] = _UNKNOWN
    return out


# ── Aggregation ───────────────────────────────────────────────────────────

def aggregate(by_query, by_url, query_page_map, intents):
    """Roll URL-level GA4 outcomes up into each query's intent bucket.

    Returns (buckets, attribution_stats). Each bucket carries clicks, sessions,
    conversions, conversion rate, ROI proxy, and the queries it covers.
    """
    url_index = {normalize_url(r.get("url")): r for r in by_url if r.get("url")}

    buckets = {
        name: {
            "intent": name,
            "clicks": 0.0,
            "sessions": 0.0,
            "conversions": 0.0,
            "queries": 0,
            "queries_attributed": 0,
        }
        for name in (_KNOWN_INTENTS + (_UNKNOWN,))
    }

    attributed_urls = set()
    attributed = 0
    for row in by_query:
        q = normalize_keyword(row.get("query"))
        if not q:
            continue
        intent = intents.get(q, _UNKNOWN)
        b = buckets[intent]
        b["queries"] += 1
        b["clicks"] += _to_float(row.get("clicks"))

        url_key = query_page_map.get(q)
        url_row = url_index.get(url_key) if url_key else None
        if url_row is not None:
            b["queries_attributed"] += 1
            attributed += 1
            # Avoid double-counting a URL's GA4 outcomes across many queries:
            # count each URL's conversions/sessions once, into the bucket of
            # the first query that claims it. This keeps totals honest.
            if url_key not in attributed_urls:
                attributed_urls.add(url_key)
                b["conversions"] += _to_float(url_row.get("conversions"))
                b["sessions"] += _to_float(url_row.get("sessions"))

    for b in buckets.values():
        clicks = b["clicks"]
        sessions = b["sessions"]
        conv = b["conversions"]
        # Conversion rate against sessions when available, else against clicks.
        denom = sessions if sessions > 0 else clicks
        b["conversion_rate"] = round(conv / denom, 4) if denom > 0 else 0.0
        # ROI proxy: conversions per 100 clicks (volume-normalized efficiency).
        b["roi_per_100_clicks"] = round((conv / clicks) * 100, 2) if clicks > 0 else 0.0
        b["clicks"] = round(clicks, 1)
        b["sessions"] = round(sessions, 1)
        b["conversions"] = round(conv, 1)

    stats = {
        "queries_total": sum(b["queries"] for b in buckets.values()),
        "queries_attributed": attributed,
        "urls_attributed": len(attributed_urls),
    }
    return buckets, stats


def rank_and_recommend(buckets):
    """Compute shares, rank intents by efficiency, pick best/worst, recommend.

    Ranking is by ROI proxy (conversions per 100 clicks), the volume-normalized
    efficiency measure — this is the whole point: prioritize by ROI, not volume.
    Only known intents with conversions are eligible to be 'best'/'worst' so we
    never recommend shifting toward an empty or unknown bucket.
    """
    total_conv = sum(b["conversions"] for b in buckets.values())
    for b in buckets.values():
        b["share_of_conversions"] = (
            round(b["conversions"] / total_conv, 4) if total_conv > 0 else 0.0
        )

    ranked = sorted(
        buckets.values(),
        key=lambda b: (-b["roi_per_100_clicks"], -b["conversions"]),
    )

    eligible = [
        b for b in buckets.values()
        if b["intent"] in _KNOWN_INTENTS and b["clicks"] > 0
    ]
    converters = [b for b in eligible if b["conversions"] > 0]

    best = max(converters, key=lambda b: b["roi_per_100_clicks"]) if converters else None
    worst = min(eligible, key=lambda b: b["roi_per_100_clicks"]) if eligible else None

    recommendation = _build_recommendation(best, worst, total_conv)
    return ranked, best, worst, recommendation, total_conv


def _build_recommendation(best, worst, total_conv):
    if best is None:
        return ("No intent bucket has attributed conversions yet. Confirm GA4 "
                "conversions are present in the merged dataset, then re-run.")
    parts = [
        f"Shift content investment toward {best['intent']} intent — it converts "
        f"at {best['roi_per_100_clicks']} conversions per 100 clicks "
        f"({best['conversion_rate']:.1%} CvR) and already drives "
        f"{best['share_of_conversions']:.0%} of conversions."
    ]
    if worst is not None and worst["intent"] != best["intent"]:
        if worst["conversions"] == 0:
            parts.append(
                f"{worst['intent'].capitalize()} intent earns clicks but no "
                f"attributed conversions — stop expanding it and audit whether "
                f"those pages match buyer intent."
            )
        else:
            parts.append(
                f"{worst['intent'].capitalize()} intent is the least efficient "
                f"({worst['roi_per_100_clicks']} per 100 clicks) — keep it lean."
            )
    return " ".join(parts)


# ── Output ────────────────────────────────────────────────────────────────

def build_report(buckets, ranked, best, worst, recommendation, total_conv,
                 attribution_stats, meta):
    return {
        "date": str(date.today()),
        "source": meta.get("source"),
        "classify_used": meta.get("classify_used", False),
        "attribution": {
            "method": "query -> landing page -> URL-level GA4 outcomes -> intent bucket",
            "caveat": (
                "GA4 has no query dimension. Conversions and sessions are "
                "measured per URL and rolled up to the query's intent bucket. "
                "Each URL's outcomes are counted once to keep totals honest. "
                "This is an approximation of per-intent conversions, not an "
                "exact split, because one URL can rank for several intents."
            ),
            **attribution_stats,
        },
        "total_conversions": round(total_conv, 1),
        "intents": [dict(b) for b in ranked],
        "best_converting_intent": best["intent"] if best else None,
        "worst_converting_intent": worst["intent"] if worst else None,
        "recommendation": recommendation,
    }


def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def print_summary(report):
    print()
    print("## Intent ROI")
    print(f"**Source:** {report.get('source')} | **Date:** {report['date']} | "
          f"**Classify:** {'yes' if report['classify_used'] else 'no'}")
    print()

    att = report["attribution"]
    print(f"Attributed {att['queries_attributed']} / {att['queries_total']} queries "
          f"to {att['urls_attributed']} landing page(s).")
    print(f"_Caveat:_ {att['caveat']}")
    print()

    print("| Intent | Clicks | Conversions | CvR | ROI /100 clicks | Share of conv. |")
    print("|--------|--------|-------------|-----|-----------------|----------------|")
    for b in report["intents"]:
        print(f"| {b['intent']} | {b['clicks']:.0f} | {b['conversions']:.0f} | "
              f"{b['conversion_rate']:.1%} | {b['roi_per_100_clicks']:.2f} | "
              f"{b['share_of_conversions']:.0%} |")
    print()

    best = report["best_converting_intent"]
    worst = report["worst_converting_intent"]
    print(f"**Best-converting intent:** {best or 'n/a'}")
    print(f"**Worst-converting intent:** {worst or 'n/a'}")
    print()
    print(f"**Recommendation:** {report['recommendation']}")


# ── CLI ───────────────────────────────────────────────────────────────────

def _print_banner():
    try:
        sys.path.insert(0, str(_API_SCRIPTS))
        from banner import print_banner  # type: ignore
        print_banner("Intent ROI")
    except Exception:
        pass


def _load_demo():
    """Bundled fixture: a merged-like structure with intents, conversions, and a
    query x page association so the skill runs with no key and no real data."""
    fixture = load_json(_SAMPLE)
    merged = fixture["merged"]
    query_pages = fixture.get("queryPages")
    return merged, query_pages


def main():
    _print_banner()

    parser = argparse.ArgumentParser(
        description="Tie search intent to conversions and prioritize content by ROI")
    parser.add_argument("--merged", help="Path to a merged dataset (default: newest in data/merged)")
    parser.add_argument("--gsc", help="GSC export for query x page association (queryPages)")
    parser.add_argument("--demo", action="store_true", help="Run on the bundled fixture (no key/data needed)")
    parser.add_argument("--classify", action="store_true",
                        help="Classify queries missing an intent via NodesHub (2 tokens/keyword)")
    parser.add_argument("--gl", default="us", help="Country code for --classify (default: us)")
    parser.add_argument("--hl", default="en", help="Language code for --classify (default: en)")
    parser.add_argument("--raw", action="store_true", help="Print raw JSON instead of the table")
    args = parser.parse_args()

    if args.demo:
        merged, query_pages = _load_demo()
        source = str(_SAMPLE)
    else:
        try:
            merged = load_merged_dataset(args.merged)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            print("Run nod-merger first, or try: python3 analyze.py --demo", file=sys.stderr)
            sys.exit(1)
        source = args.merged or "newest data/merged/*.json"
        gsc_path = Path(args.gsc) if args.gsc else _newest(_GSC_DIR, "gsc-*.json")
        query_pages = load_query_pages(gsc_path) if gsc_path else None

    by_query = merged.get("by_query", []) or []
    by_url = merged.get("by_url", []) or []

    if not by_query:
        print("Error: merged dataset has no by_query rows — nothing to attribute.",
              file=sys.stderr)
        sys.exit(1)

    intents = resolve_intents(by_query, args.classify, args.gl, args.hl)
    query_page_map = build_query_page_map(by_query, by_url, query_pages)
    buckets, attribution_stats = aggregate(by_query, by_url, query_page_map, intents)
    ranked, best, worst, recommendation, total_conv = rank_and_recommend(buckets)

    report = build_report(
        buckets, ranked, best, worst, recommendation, total_conv,
        attribution_stats,
        {"source": source, "classify_used": bool(args.classify)},
    )
    out_path = save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
