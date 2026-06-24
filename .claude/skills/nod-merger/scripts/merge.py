#!/usr/bin/env python3
"""
Data Merger — deterministically unify GSC + GA4 + Google Ads into one funnel
dataset keyed by URL (and by query where available).

No LLM, no API calls in the core path. This is the foundation layer that
downstream skills (auto-detector, paid-vs-organic, intent-ROI) import.

Two views are produced:
  by_url   — GSC topPages joined with GA4 topPages on a normalized URL.
             Full funnel: impressions -> clicks -> sessions -> conversions.
  by_query — GSC topQueries enriched with Ads metrics (volume, cpc,
             competition) joined on the normalized keyword.

LIMITATION (important, documented): GA4 has no query dimension, so GA4 metrics
(sessions, conversions, engagement) live ONLY in by_url. They cannot be
attributed per query. by_query carries search + Ads signal, not GA4 outcomes.

Usage:
    python3 merge.py                       # newest files in knowledge/metrics/
    python3 merge.py --gsc a.json --ga4 b.json --ads c.json
    python3 merge.py --demo                # run on bundled sample fixtures
    python3 merge.py --csv-out             # also write a by_url CSV
    python3 merge.py --enrich-serp --gl us # attach live intent per top query (costs tokens)

Output:
    data/merged/{YYYY-MM-DD}.json  -> { meta, by_url: [...], by_query: [...] }
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
_GSC_DIR = _REPO_ROOT / "knowledge" / "metrics" / "seo"
_GA4_DIR = _REPO_ROOT / "knowledge" / "metrics" / "analytics"
_ADS_DIR = _REPO_ROOT / "knowledge" / "metrics" / "ads"
_MERGED_DIR = _REPO_ROOT / "data" / "merged"

_SAMPLE_GSC = _SKILL_DIR / "sample_gsc.json"
_SAMPLE_GA4 = _SKILL_DIR / "sample_ga4.json"
_SAMPLE_ADS = _SKILL_DIR / "sample_ads.csv"


# ── Normalization helpers ─────────────────────────────────────────────────

def normalize_url(raw):
    """Normalize a URL/path for joining across sources.

    Strips protocol, host, query string, fragment, and trailing slash so that
    GSC pages (often already site-relative like ``/blog/x``) line up with GA4
    pagePath values (``/blog/x``). Returns a leading-slash path, lowercased.
    """
    if not raw:
        return ""
    u = str(raw).strip()
    u = re.sub(r"^https?://", "", u, flags=re.IGNORECASE)   # drop protocol
    if "/" in u and ("." in u.split("/")[0]):               # drop host if present
        u = "/" + u.split("/", 1)[1]
    u = u.split("?")[0].split("#")[0]                        # drop query/fragment
    if not u.startswith("/"):
        u = "/" + u
    if len(u) > 1 and u.endswith("/"):                      # drop trailing slash
        u = u.rstrip("/")
    return u.lower()


def normalize_keyword(raw):
    """Lowercase + collapse whitespace for keyword joins."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().lower())


def _to_float(value):
    """Parse '4.29%', '$3.45', '5.1', 92 into a float; None on failure."""
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


# ── Loading ───────────────────────────────────────────────────────────────

def _newest(directory, pattern):
    """Return the most recently named matching file, or None."""
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), reverse=True)
    return files[0] if files else None


def load_json(path):
    return json.loads(Path(path).read_text())


def load_ads(path):
    """Load Ads data from JSON (array of rows) or a CSV export."""
    p = Path(path)
    if p.suffix.lower() == ".csv":
        return _load_ads_csv(p)
    data = load_json(p)
    # Accept either a bare array or an object wrapping one.
    if isinstance(data, dict):
        data = data.get("keywords") or data.get("data") or []
    return [
        {
            "keyword": r.get("keyword", ""),
            "volume": _to_int(r.get("volume")),
            "cpc": _to_float(r.get("cpc")),
            "competition": _to_float(r.get("competition")),
        }
        for r in data
        if r.get("keyword")
    ]


_ADS_CSV_ALIASES = {
    "keyword": ["keyword", "query", "term", "phrase", "keywords"],
    "volume": ["volume", "avg_monthly_searches", "avg monthly searches",
               "search volume", "searches", "sv"],
    "cpc": ["cpc", "avg_cpc", "avg cpc", "cost per click"],
    "competition": ["competition", "comp", "competition_index", "difficulty"],
}


def _load_ads_csv(path):
    """Generic keyword-CSV ingest (Ads/DataForSEO/Senuto) -> normalized rows."""
    rows = list(csv.reader(path.open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return []
    header = [re.sub(r"[._-]", " ", h.lower()).strip() for h in rows[0]]
    col = {}
    for field, aliases in _ADS_CSV_ALIASES.items():
        for i, h in enumerate(header):
            if h in aliases:
                col[field] = i
                break
    if "keyword" not in col:
        return []

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
            "competition": _competition_value(r[col["competition"]]) if "competition" in col and col["competition"] < len(r) else None,
        })
    return out


def _competition_value(raw):
    """Map low/medium/high or 0-100 index to a 0-1 float."""
    text = str(raw).strip().lower()
    labels = {"low": 0.2, "medium": 0.5, "high": 0.8}
    if text in labels:
        return labels[text]
    n = _to_float(raw)
    if n is None:
        return None
    return min(n / 100, 1.0) if n > 1 else n


# ── Merge logic ───────────────────────────────────────────────────────────

def build_by_url(gsc, ga4):
    """Join GSC topPages with GA4 topPages on a normalized URL.

    GSC drives the spine (it is the SEO source of truth). GA4 metrics enrich.
    GA4 pages with no GSC match are appended (GSC-less rows) so nothing is lost.
    """
    ga4_pages = (ga4 or {}).get("topPages", [])
    ga4_by_url = {}
    for p in ga4_pages:
        key = normalize_url(p.get("page"))
        if key:
            ga4_by_url[key] = p

    rows = []
    matched_keys = set()

    for p in (gsc or {}).get("topPages", []):
        key = normalize_url(p.get("page"))
        impressions = _to_int(p.get("impressions"))
        clicks = _to_int(p.get("clicks"))
        ga = ga4_by_url.get(key)
        if ga:
            matched_keys.add(key)

        # GA4 (fetch-ga4.js) ships pageviews/users/avgSessionDuration per page.
        # Richer exports may add sessions/conversions/engagementRate — honor them.
        sessions = _to_int(ga.get("sessions")) if ga and ga.get("sessions") is not None else None
        if sessions is None and ga is not None:
            sessions = _to_int(ga.get("users"))  # users as a session proxy
        conversions = _to_int(ga.get("conversions")) if ga and ga.get("conversions") is not None else None
        engagement = _to_float(ga.get("engagementRate")) if ga and ga.get("engagementRate") is not None else None

        rows.append({
            "url": key,
            "in_gsc": True,
            "in_ga4": ga is not None,
            # GSC funnel head
            "impressions": impressions,
            "clicks": clicks,
            "ctr": _to_float(p.get("ctr")),
            "position": _to_float(p.get("position")),
            # GA4 funnel body/tail
            "sessions": sessions,
            "pageviews": _to_int(ga.get("pageviews")) if ga else None,
            "users": _to_int(ga.get("users")) if ga else None,
            "conversions": conversions,
            "engagement_rate": engagement,
            "avg_session_duration": ga.get("avgSessionDuration") if ga else None,
        })

    # GA4-only pages (no GSC clicks/impressions) — keep them, flag the gap.
    for key, ga in ga4_by_url.items():
        if key in matched_keys:
            continue
        rows.append({
            "url": key,
            "in_gsc": False,
            "in_ga4": True,
            "impressions": None,
            "clicks": None,
            "ctr": None,
            "position": None,
            "sessions": _to_int(ga.get("sessions")) if ga.get("sessions") is not None else _to_int(ga.get("users")),
            "pageviews": _to_int(ga.get("pageviews")),
            "users": _to_int(ga.get("users")),
            "conversions": _to_int(ga.get("conversions")) if ga.get("conversions") is not None else None,
            "engagement_rate": _to_float(ga.get("engagementRate")) if ga.get("engagementRate") is not None else None,
            "avg_session_duration": ga.get("avgSessionDuration"),
        })

    return rows


def build_by_query(gsc, ads):
    """Enrich GSC topQueries with Ads metrics joined on the normalized keyword.

    GA4 is intentionally absent here: GA4 has no query dimension, so per-query
    conversions cannot exist. by_query = search demand + paid signal only.
    """
    ads_by_kw = {normalize_keyword(a.get("keyword")): a for a in (ads or [])}

    rows = []
    for q in (gsc or {}).get("topQueries", []):
        key = normalize_keyword(q.get("query"))
        ad = ads_by_kw.get(key)
        rows.append({
            "query": q.get("query"),
            "in_gsc": True,
            "in_ads": ad is not None,
            # GSC signal
            "clicks": _to_int(q.get("clicks")),
            "impressions": _to_int(q.get("impressions")),
            "ctr": _to_float(q.get("ctr")),
            "position": _to_float(q.get("position")),
            # Ads signal
            "volume": ad.get("volume") if ad else None,
            "cpc": ad.get("cpc") if ad else None,
            "competition": ad.get("competition") if ad else None,
        })
    return rows


def enrich_serp(by_query, gl, hl):
    """Optional: attach live intent per query via the NodesHub client.

    Costs tokens. Only runs when --enrich-serp is passed. Failures are
    non-fatal so the deterministic merge is never blocked by the API.
    """
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
    try:
        from client import NodeshubClient, NodeshubError
    except ImportError as exc:
        print(f"  [enrich-serp skipped — client unavailable: {exc}]", file=sys.stderr)
        return by_query

    client = NodeshubClient()
    for row in by_query:
        try:
            res = client.classify_intent(row["query"], gl=gl, hl=hl)
            data = res.get("data", {}).get("results", res.get("data", {}))
            row["intent"] = data.get("intent") or data.get("label")
        except NodeshubError as exc:
            print(f"  [intent failed for '{row['query']}': {exc}]", file=sys.stderr)
            row["intent"] = None
    return by_query


# ── Coverage / summary ────────────────────────────────────────────────────

def coverage_stats(by_url, by_query):
    url_matched = sum(1 for r in by_url if r["in_gsc"] and r["in_ga4"])
    query_matched = sum(1 for r in by_query if r["in_ads"])
    return {
        "by_url_rows": len(by_url),
        "by_url_gsc_ga4_matched": url_matched,
        "by_query_rows": len(by_query),
        "by_query_ads_matched": query_matched,
    }


# ── Output ────────────────────────────────────────────────────────────────

def write_csv(by_url, path):
    fields = ["url", "in_gsc", "in_ga4", "impressions", "clicks", "ctr",
              "position", "sessions", "pageviews", "users", "conversions",
              "engagement_rate", "avg_session_duration"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in by_url:
            writer.writerow({k: row.get(k) for k in fields})


def load_merged(path=None):
    """Importable helper for downstream skills.

    Returns the parsed merged dataset (dict with meta/by_url/by_query). With no
    path, loads the newest file in data/merged/. Raises FileNotFoundError if no
    merged dataset exists yet.
    """
    if path is None:
        path = _newest(_MERGED_DIR, "*.json")
        if path is None:
            raise FileNotFoundError(
                f"No merged dataset in {_MERGED_DIR}. Run merge.py first."
            )
    return load_json(path)


# ── CLI ───────────────────────────────────────────────────────────────────

def resolve_sources(args):
    """Decide which GSC/GA4/Ads files to use. Each source is optional."""
    if args.demo:
        return _SAMPLE_GSC, _SAMPLE_GA4, _SAMPLE_ADS

    gsc = Path(args.gsc) if args.gsc else _newest(_GSC_DIR, "gsc-*.json")
    ga4 = Path(args.ga4) if args.ga4 else _newest(_GA4_DIR, "ga4-*.json")
    ads = Path(args.ads) if args.ads else _newest(_ADS_DIR, "ads-*.json")
    return gsc, ga4, ads


def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Data Merger")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Merge GSC + GA4 + Google Ads into one funnel dataset")
    parser.add_argument("--gsc", help="Explicit GSC JSON path")
    parser.add_argument("--ga4", help="Explicit GA4 JSON path")
    parser.add_argument("--ads", help="Explicit Ads JSON or CSV path")
    parser.add_argument("--demo", action="store_true", help="Run on bundled sample fixtures")
    parser.add_argument("--csv-out", action="store_true", help="Also write a by_url CSV")
    parser.add_argument("--enrich-serp", action="store_true", help="Attach live intent per query (costs NodesHub tokens)")
    parser.add_argument("--gl", default="us", help="Country code for --enrich-serp")
    parser.add_argument("--hl", default="en", help="Language code for --enrich-serp")
    args = parser.parse_args()

    gsc_path, ga4_path, ads_path = resolve_sources(args)

    # Load whatever is present; note what is missing.
    sources_present, sources_missing = [], []

    gsc = None
    if gsc_path and Path(gsc_path).exists():
        gsc = load_json(gsc_path)
        sources_present.append("gsc")
    else:
        sources_missing.append("gsc")

    ga4 = None
    if ga4_path and Path(ga4_path).exists():
        ga4 = load_json(ga4_path)
        sources_present.append("ga4")
    else:
        sources_missing.append("ga4")

    ads = None
    if ads_path and Path(ads_path).exists():
        ads = load_ads(ads_path)
        sources_present.append("ads")
    else:
        sources_missing.append("ads")

    if gsc is None and ga4 is None and ads is None:
        print("No source data found. Run fetch-gsc.js / fetch-ga4.js / fetch-google-ads.js,")
        print("or try: python3 merge.py --demo")
        sys.exit(1)

    by_url = build_by_url(gsc, ga4)
    by_query = build_by_query(gsc, ads)

    if args.enrich_serp and by_query:
        by_query = enrich_serp(by_query, args.gl, args.hl)

    stats = coverage_stats(by_url, by_query)

    merged = {
        "meta": {
            "generatedAt": date.today().isoformat(),
            "sources_present": sources_present,
            "sources_missing": sources_missing,
            "source_files": {
                "gsc": str(gsc_path) if gsc is not None else None,
                "ga4": str(ga4_path) if ga4 is not None else None,
                "ads": str(ads_path) if ads is not None else None,
            },
            "coverage": stats,
            "serp_enriched": bool(args.enrich_serp),
            "note": "GA4 conversions are per-URL only; GA4 has no query dimension, so by_query carries no GA4 metrics.",
        },
        "by_url": by_url,
        "by_query": by_query,
    }

    _MERGED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _MERGED_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n")

    if args.csv_out:
        csv_path = _MERGED_DIR / f"{date.today()}-by_url.csv"
        write_csv(by_url, csv_path)

    # Readable summary.
    print()
    print("## Data Merger")
    print(f"**Sources present:** {', '.join(sources_present) or 'none'}"
          + (f" | **Missing:** {', '.join(sources_missing)}" if sources_missing else ""))
    print()
    print(f"- by_url rows:           {stats['by_url_rows']}")
    print(f"- by_url GSC+GA4 matched: {stats['by_url_gsc_ga4_matched']}")
    print(f"- by_query rows:          {stats['by_query_rows']}")
    print(f"- by_query Ads matched:   {stats['by_query_ads_matched']}")
    print()
    print(f"Saved: {out_path}")
    if args.csv_out:
        print(f"Saved: {csv_path}")


if __name__ == "__main__":
    main()
