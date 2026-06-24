#!/usr/bin/env python3
"""
Share of Search — deterministic Share of Search analyzer (Les Binet).

Share of Search is your brand's search demand expressed as a percentage of the
total brand search demand in your category. Tracked month over month it acts as
a leading indicator of market share and future sales. This is a board-level
demand metric, not an SEO mechanic — it answers "is our brand growing relative
to competitors?" rather than "how do we rank?".

For each month:

    Share of Search(brand) = brand search volume
                             / sum of search volume across all tracked brands

The analyzer computes the latest share per brand, the trend over the available
months (least-squares slope on share points), and flags both the direction of
your own share and which competitor carries the fastest upward momentum. All
logic is pure arithmetic, so the same volumes always produce the same report —
no LLM, no model judgment.

Brand search volume comes from three interchangeable sources (a brand may have
several aliases, summed together):

  1. DataForSEO adapter — keywords_data/google_ads/search_volume returns
     monthly_searches per keyword. Gated behind DATAFORSEO_LOGIN /
     DATAFORSEO_PASSWORD; skips gracefully when credentials are absent.
  2. CSV / JSON ingest (--volumes PATH) — brand -> monthly volumes.
  3. --demo fixture — your brand + 3 competitors, so it runs today.

Optionally, if a merged dataset (nod-merger) exposes your branded-query clicks,
the report adds a secondary view: search-demand share vs captured-clicks share.

Usage:
    python3 analyze.py --demo
    python3 analyze.py --brand "Acme" --competitors "Globex,Initech,Umbrella"
    python3 analyze.py --brand "Acme" --competitors "Globex,Initech" --volumes brands.csv
    python3 analyze.py --brand "Acme" --aliases "Acme:acme app,acme io" --competitors "Globex"
    python3 analyze.py --brand "Acme" --competitors "Globex,Initech,Umbrella" --gl us --hl en

Output:
    data/share-of-search/{YYYY-MM-DD}.json  -> { meta, months, brands, ... }
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_OUTPUT_DIR = _REPO_ROOT / "data" / "share-of-search"
_NODESHUB_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"
_MERGER_SCRIPTS = _REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"

_SETTINGS_CANDIDATES = [
    Path(".claude/settings.local.json"),
    _REPO_ROOT / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
]

_DATAFORSEO_URL = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"


# ── Settings / env loading ────────────────────────────────────────────────

def _setting(name):
    """Read a value from the environment, then from settings.local.json env blocks."""
    val = os.environ.get(name)
    if val:
        return val
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                data = json.loads(path.read_text())
                val = data.get("env", {}).get(name)
                if val:
                    return val
            except (json.JSONDecodeError, OSError):
                continue
    return None


# ── Number helpers ─────────────────────────────────────────────────────────

def _to_float(value, default=0.0):
    """Parse a possibly messy numeric value into a float."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").rstrip("%")
    try:
        return float(text)
    except ValueError:
        return default


def _normalize_brand(name):
    """Lowercase + collapse whitespace for brand matching."""
    return " ".join(str(name or "").lower().split())


# ── Demo fixture ────────────────────────────────────────────────────────────
# Six months of brand search volume. Your brand (Acme) climbs steadily, one
# competitor (Globex) is flat-to-soft, Initech fades, and Umbrella surges — so
# the demo exercises rising/falling direction and competitor momentum at once.

_DEMO_MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]

_DEMO_VOLUMES = {
    "Acme":     [12000, 12600, 13200, 14100, 15000, 16200],
    "Globex":   [22000, 21500, 21800, 21000, 20600, 20100],
    "Initech":  [ 9000,  8600,  8100,  7400,  6900,  6300],
    "Umbrella": [ 4000,  4600,  5400,  6500,  7800,  9400],
}


def load_demo():
    """Return (months, {brand: [volumes]}) for the bundled demo."""
    return list(_DEMO_MONTHS), {b: list(v) for b, v in _DEMO_VOLUMES.items()}


# ── CSV / JSON ingest ───────────────────────────────────────────────────────

def _parse_csv(text):
    """Minimal CSV parser (quoted fields, embedded commas). Returns list of rows."""
    rows, row, field, in_quotes = [], [], "", False
    for i, c in enumerate(text):
        if in_quotes:
            if c == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    field += '"'
                else:
                    in_quotes = False
            else:
                field += c
        elif c == '"':
            in_quotes = True
        elif c == ",":
            row.append(field)
            field = ""
        elif c == "\n":
            row.append(field)
            field = ""
            rows.append(row)
            row = []
        elif c == "\r":
            continue
        else:
            field += c
    if field or row:
        row.append(field)
        rows.append(row)
    return [r for r in rows if any(cell.strip() for cell in r)]


def _ingest_csv(path):
    """
    Ingest a brand-volume CSV. Two accepted layouts:

      A) wide  — header: brand, 2026-01, 2026-02, ...   (one row per brand)
      B) long  — header: brand, month, volume           (one row per brand-month)

    Returns (months, {brand: [volumes aligned to months]}).
    """
    rows = _parse_csv(Path(path).read_text())
    if len(rows) < 2:
        raise ValueError("CSV has no data rows.")

    header = [h.strip() for h in rows[0]]
    lower = [h.lower() for h in header]
    if "brand" not in lower:
        raise ValueError("CSV must have a 'brand' column.")
    brand_idx = lower.index("brand")

    # Long layout: brand, month, volume.
    if "month" in lower and "volume" in lower:
        m_idx, v_idx = lower.index("month"), lower.index("volume")
        series = {}
        months_seen = []
        for r in rows[1:]:
            if max(brand_idx, m_idx, v_idx) >= len(r):
                continue
            brand = r[brand_idx].strip()
            month = r[m_idx].strip()
            if not brand or not month:
                continue
            if month not in months_seen:
                months_seen.append(month)
            series.setdefault(brand, {})[month] = _to_float(r[v_idx])
        months = sorted(months_seen)
        out = {b: [vals.get(m, 0.0) for m in months] for b, vals in series.items()}
        return months, out

    # Wide layout: brand + month columns.
    month_cols = [(i, header[i]) for i in range(len(header)) if i != brand_idx]
    months = [name for _, name in month_cols]
    out = {}
    for r in rows[1:]:
        if brand_idx >= len(r) or not r[brand_idx].strip():
            continue
        brand = r[brand_idx].strip()
        out[brand] = [_to_float(r[i]) if i < len(r) else 0.0 for i, _ in month_cols]
    return months, out


def _ingest_json(path):
    """
    Ingest a brand-volume JSON. Accepted shapes:

      { "months": [...], "volumes": { "Brand": [..] } }
      { "Brand": [..], ... }                 (months inferred as 1..N)
      { "Brand": { "2026-01": 12000, ... } }  (per-month dict)

    Returns (months, {brand: [volumes]}).
    """
    data = json.loads(Path(path).read_text())

    if isinstance(data, dict) and "volumes" in data:
        months = list(data.get("months") or [])
        volumes = {b: [_to_float(x) for x in v] for b, v in data["volumes"].items()}
        if not months and volumes:
            n = max(len(v) for v in volumes.values())
            months = [f"m{i + 1}" for i in range(n)]
        return months, volumes

    if isinstance(data, dict):
        # Either {brand: [..]} or {brand: {month: vol}}.
        sample = next(iter(data.values()), None)
        if isinstance(sample, dict):
            months = sorted({m for d in data.values() for m in d})
            volumes = {b: [_to_float(d.get(m, 0.0)) for m in months] for b, d in data.items()}
            return months, volumes
        if isinstance(sample, list):
            n = max((len(v) for v in data.values()), default=0)
            months = [f"m{i + 1}" for i in range(n)]
            volumes = {b: [_to_float(x) for x in v] for b, v in data.items()}
            return months, volumes

    raise ValueError("Unrecognized JSON shape for --volumes.")


def ingest_volumes(path):
    """Dispatch to the CSV or JSON ingest based on file extension/content."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Volumes file not found: {path}")
    if p.suffix.lower() == ".json":
        return _ingest_json(p)
    return _ingest_csv(p)


# ── Alias handling ──────────────────────────────────────────────────────────

def parse_aliases(brand, competitors, alias_spec):
    """
    Build {brand: [alias keyword, ...]} for every tracked brand.

    alias_spec format (optional): "Brand:kw1,kw2;Other:kw3,kw4". A brand without
    an explicit alias entry uses its own name as the only keyword.
    """
    all_brands = [brand] + list(competitors)
    aliases = {b: [b] for b in all_brands}
    if not alias_spec:
        return aliases

    norm_lookup = {_normalize_brand(b): b for b in all_brands}
    for chunk in alias_spec.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        name, kws = chunk.split(":", 1)
        canonical = norm_lookup.get(_normalize_brand(name))
        if canonical is None:
            # Alias for an untracked brand — register it as its own brand.
            canonical = name.strip()
            aliases.setdefault(canonical, [canonical])
        kw_list = [k.strip() for k in kws.split(",") if k.strip()]
        if kw_list:
            # Include the brand name itself plus the explicit aliases.
            merged = [canonical] + [k for k in kw_list if k != canonical]
            aliases[canonical] = merged
    return aliases


# ── DataForSEO adapter ──────────────────────────────────────────────────────

def fetch_dataforseo(aliases, gl, hl):
    """
    Pull monthly search volume per alias from DataForSEO and sum per brand.

    Returns (months, {brand: [volumes]}) or None when credentials are missing or
    the call fails. Each brand's monthly volume is the sum of its aliases.
    """
    import base64
    import urllib.error
    import urllib.request

    login = _setting("DATAFORSEO_LOGIN")
    password = _setting("DATAFORSEO_PASSWORD")
    if not login or not password:
        print("  (DataForSEO skipped: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD not configured)")
        return None

    keywords = sorted({kw for kws in aliases.values() for kw in kws})
    payload = [{
        "keywords": keywords,
        "location_name": _location_for_gl(gl),
        "language_code": hl,
        "search_partners": False,
    }]
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    req = urllib.request.Request(
        _DATAFORSEO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        print(f"  (DataForSEO call failed: {exc} — falling back)")
        return None

    items = []
    for task in data.get("tasks") or []:
        items.extend(task.get("result") or [])
    if not items:
        print("  (DataForSEO returned no data — falling back)")
        return None

    # Map keyword -> {YYYY-MM: volume} from monthly_searches arrays.
    kw_months = {}
    month_keys = set()
    for it in items:
        kw = _normalize_brand(it.get("keyword"))
        by_month = {}
        for ms in it.get("monthly_searches") or []:
            year, month = ms.get("year"), ms.get("month")
            if year is None or month is None:
                continue
            key = f"{int(year):04d}-{int(month):02d}"
            by_month[key] = _to_float(ms.get("search_volume"))
            month_keys.add(key)
        kw_months[kw] = by_month

    months = sorted(month_keys)
    if not months:
        print("  (DataForSEO returned no monthly_searches — falling back)")
        return None

    volumes = {}
    for brand, kws in aliases.items():
        series = []
        for m in months:
            total = sum(kw_months.get(_normalize_brand(kw), {}).get(m, 0.0) for kw in kws)
            series.append(total)
        volumes[brand] = series
    return months, volumes


def _location_for_gl(gl):
    """Map a country code to a DataForSEO location_name. Falls back to United States."""
    mapping = {
        "us": "United States", "gb": "United Kingdom", "uk": "United Kingdom",
        "pl": "Poland", "de": "Germany", "fr": "France", "es": "Spain",
        "it": "Italy", "ca": "Canada", "au": "Australia", "nl": "Netherlands",
    }
    return mapping.get((gl or "us").lower(), "United States")


# ── Core computation ────────────────────────────────────────────────────────

def _slope(values):
    """Least-squares slope of a series against its index. Flat/empty -> 0.0."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _trend_arrow(slope, threshold=0.0015):
    """Map a per-month share slope to an arrow + word. Threshold ~0.15pp/month."""
    if slope > threshold:
        return "up", "rising"
    if slope < -threshold:
        return "down", "falling"
    return "flat", "flat"


def _sparkline(values):
    """Render a fixed-charset ASCII sparkline for a 0..1 share series."""
    ramp = " .:-=+*#%@"
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo
    out = []
    for v in values:
        if span <= 0:
            idx = len(ramp) // 2
        else:
            idx = int(round((v - lo) / span * (len(ramp) - 1)))
        out.append(ramp[idx])
    return "".join(out)


def compute(months, volumes):
    """
    Compute per-month and per-brand Share of Search.

    Returns a dict with:
      months         — the month labels
      totals         — total category volume per month
      brands         — list of brand dicts (share series, latest share, slope,
                       trend direction, latest volume), sorted by latest share desc
    """
    month_count = len(months)
    # Per-month category totals.
    totals = []
    for i in range(month_count):
        totals.append(sum(_to_float(v[i]) if i < len(v) else 0.0 for v in volumes.values()))

    brands = []
    for brand, series in volumes.items():
        shares = []
        for i in range(month_count):
            vol = _to_float(series[i]) if i < len(series) else 0.0
            total = totals[i]
            shares.append((vol / total) if total > 0 else 0.0)
        slope = _slope(shares)
        direction, word = _trend_arrow(slope)
        latest_vol = _to_float(series[-1]) if series else 0.0
        first_share = shares[0] if shares else 0.0
        latest_share = shares[-1] if shares else 0.0
        brands.append({
            "brand": brand,
            "shares": [round(s, 6) for s in shares],
            "latest_share": round(latest_share, 6),
            "first_share": round(first_share, 6),
            "share_change": round(latest_share - first_share, 6),
            "slope": round(slope, 6),
            "trend_direction": direction,
            "trend_word": word,
            "latest_volume": latest_vol,
            "sparkline": _sparkline(shares),
        })

    brands.sort(key=lambda b: -b["latest_share"])
    return {"months": months, "totals": totals, "brands": brands}


def add_flags(result, brand_name):
    """
    Attach direction/momentum flags:
      - your own share trend (rising/falling/flat)
      - the competitor with the fastest upward momentum (largest positive slope)
    """
    norm_target = _normalize_brand(brand_name)
    you = next((b for b in result["brands"] if _normalize_brand(b["brand"]) == norm_target), None)
    competitors = [b for b in result["brands"] if _normalize_brand(b["brand"]) != norm_target]

    fastest = None
    if competitors:
        fastest = max(competitors, key=lambda b: b["slope"])
        if fastest["slope"] <= 0:
            fastest = None  # nobody is genuinely gaining

    result["flags"] = {
        "your_brand": you["brand"] if you else brand_name,
        "your_share": you["latest_share"] if you else 0.0,
        "your_trend": you["trend_word"] if you else "unknown",
        "your_direction": you["trend_direction"] if you else "flat",
        "fastest_competitor": fastest["brand"] if fastest else None,
        "fastest_competitor_slope": fastest["slope"] if fastest else None,
        "fastest_competitor_trend": fastest["trend_word"] if fastest else None,
    }
    return result


# ── Optional: captured-clicks secondary view ────────────────────────────────

def captured_clicks_view(aliases):
    """
    Build a "captured-clicks share" view from a merged dataset (nod-merger), if
    one exists and exposes branded-query clicks. Compares search-demand share
    (your slice of category demand) against the clicks you actually capture on
    your own branded queries. Returns a dict or None.
    """
    sys.path.insert(0, str(_MERGER_SCRIPTS))
    try:
        from merge import load_merged
    except ImportError:
        return None

    try:
        merged = load_merged()
    except (FileNotFoundError, Exception):
        return None

    by_query = merged.get("by_query") if isinstance(merged, dict) else None
    if not by_query:
        return None

    # Sum clicks on rows whose query contains any of your brand aliases.
    your_aliases = [_normalize_brand(a) for a in next(iter(aliases.values()), [])]
    # aliases dict is keyed by brand; the first key is your brand by construction.
    branded_clicks = 0.0
    total_clicks = 0.0
    matched = 0
    for row in by_query:
        q = _normalize_brand(row.get("query"))
        clicks = _to_float(row.get("clicks"))
        total_clicks += clicks
        if any(alias and alias in q for alias in your_aliases):
            branded_clicks += clicks
            matched += 1

    # Only surface this view when at least one branded query actually matched —
    # otherwise the 0% reading is just noise from an unrelated merged dataset.
    if total_clicks <= 0 or matched == 0:
        return None

    return {
        "branded_clicks": round(branded_clicks, 1),
        "total_clicks": round(total_clicks, 1),
        "captured_clicks_share": round(branded_clicks / total_clicks, 6),
        "matched_queries": matched,
    }


# ── Output ──────────────────────────────────────────────────────────────────

def save_report(result, meta, captured):
    """Write the structured report to data/share-of-search/{date}.json."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "date": str(date.today()),
        "meta": meta,
        "months": result["months"],
        "totals": result["totals"],
        "brands": result["brands"],
        "flags": result.get("flags", {}),
        "captured_clicks_view": captured,
    }
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _pct(x):
    return f"{x * 100:.1f}%"


def print_summary(result, meta, captured):
    """Print a readable table, trend arrows, a sparkline, and flags."""
    arrows = {"up": "^", "down": "v", "flat": "-"}
    months = result["months"]
    flags = result.get("flags", {})

    print()
    print("## Share of Search")
    print(f"**Source:** {meta.get('source')} | **Date:** {date.today()} | "
          f"**Months:** {len(months)} ({months[0]} -> {months[-1]})" if months else "")
    print()

    print("| Brand | Current share | Trend | Change | Latest volume | History |")
    print("|-------|---------------|-------|--------|---------------|---------|")
    for b in result["brands"]:
        arrow = arrows.get(b["trend_direction"], "-")
        chg = b["share_change"]
        chg_str = f"{'+' if chg >= 0 else ''}{chg * 100:.1f}pp"
        vol = f"{b['latest_volume']:,.0f}"
        print(f"| {b['brand']} | {_pct(b['latest_share'])} | {arrow} {b['trend_word']} | "
              f"{chg_str} | {vol} | `{b['sparkline']}` |")
    print()

    # Your-brand sparkline, spelled out.
    you = next((b for b in result["brands"]
                if _normalize_brand(b["brand"]) == _normalize_brand(flags.get("your_brand", ""))), None)
    if you:
        print(f"Your share over {len(months)} months ({flags['your_brand']}): "
              f"`{you['sparkline']}`  {_pct(you['first_share'])} -> {_pct(you['latest_share'])}")
        print()

    # Flags.
    print("### Direction")
    print(f"- Your share ({flags.get('your_brand')}): **{flags.get('your_trend')}** "
          f"at {_pct(flags.get('your_share', 0.0))}.")
    if flags.get("fastest_competitor"):
        print(f"- Fastest competitor momentum: **{flags['fastest_competitor']}** "
              f"(share {flags.get('fastest_competitor_trend')}, slope "
              f"{flags['fastest_competitor_slope'] * 100:+.2f}pp/month).")
    else:
        print("- No competitor is gaining share; your category position is stable or improving.")
    print()

    # Optional captured-clicks secondary view.
    if captured:
        print("### Search-demand share vs captured-clicks share")
        print(f"- Search-demand share (Share of Search): "
              f"{_pct(flags.get('your_share', 0.0))}.")
        print(f"- Captured-clicks share (your branded clicks / all clicks): "
              f"{_pct(captured['captured_clicks_share'])} "
              f"({captured['branded_clicks']:.0f} of {captured['total_clicks']:.0f} clicks, "
              f"{captured['matched_queries']} branded queries).")
        print()

    print("Cost: 0 NodesHub tokens.")


# ── Source resolution ───────────────────────────────────────────────────────

def resolve_source(args, aliases):
    """
    Decide where brand volumes come from and return (months, volumes, source_label).

    Priority: --demo -> --volumes file -> DataForSEO adapter. DataForSEO skips
    gracefully (returns None) when credentials are missing or the call fails;
    in that case we error with guidance toward --volumes / --demo.
    """
    if args.demo:
        months, volumes = load_demo()
        return months, volumes, "demo fixture"

    if args.volumes:
        months, volumes = ingest_volumes(args.volumes)
        return months, volumes, f"volumes file ({Path(args.volumes).name})"

    fetched = fetch_dataforseo(aliases, args.gl, args.hl)
    if fetched is not None:
        return fetched[0], fetched[1], "DataForSEO google_ads/search_volume"

    print("\nError: no volume source available.", file=sys.stderr)
    print("Provide one of:", file=sys.stderr)
    print("  --demo                         run on the bundled fixture", file=sys.stderr)
    print("  --volumes brands.csv           brand -> monthly volumes (CSV or JSON)", file=sys.stderr)
    print("  DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD in settings.local.json for the API path",
          file=sys.stderr)
    sys.exit(1)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_NODESHUB_SCRIPTS))
        from banner import print_banner
        print_banner("Share of Search")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Share of Search — your brand's search demand as a share of category demand")
    parser.add_argument("--brand", help="Your brand name")
    parser.add_argument("--competitors", default="",
                        help="Comma-separated competitor brand names")
    parser.add_argument("--aliases", default="",
                        help='Optional aliases per brand: "Brand:kw1,kw2;Other:kw3"')
    parser.add_argument("--volumes",
                        help="Path to a brand-volume CSV or JSON (brand -> monthly volumes)")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the bundled demo fixture (you + 3 competitors)")
    parser.add_argument("--gl", default="us", help="Country code for DataForSEO (default: us)")
    parser.add_argument("--hl", default="en", help="Language code for DataForSEO (default: en)")
    parser.add_argument("--raw", action="store_true",
                        help="Print the raw JSON report instead of a table")
    args = parser.parse_args()

    # Resolve brand identity.
    if args.demo and not args.brand:
        brand = "Acme"
        competitors = ["Globex", "Initech", "Umbrella"]
    else:
        if not args.brand:
            print("Error: --brand is required (or use --demo).", file=sys.stderr)
            sys.exit(1)
        brand = args.brand
        competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]

    aliases = parse_aliases(brand, competitors, args.aliases)

    months, volumes, source = resolve_source(args, aliases)

    if len(volumes) < 2:
        print("Error: need at least two brands (you + one competitor) to compute share.",
              file=sys.stderr)
        sys.exit(1)
    if not months:
        print("Error: no months found in the volume source.", file=sys.stderr)
        sys.exit(1)

    result = compute(months, volumes)
    result = add_flags(result, brand)

    captured = captured_clicks_view(aliases)

    meta = {
        "source": source,
        "your_brand": brand,
        "competitors": competitors,
        "months": months,
        "gl": args.gl,
        "hl": args.hl,
        "tokens_used": 0,
    }
    out_path = save_report(result, meta, captured)

    if args.raw:
        print(json.dumps({
            "date": str(date.today()),
            "meta": meta,
            "months": result["months"],
            "totals": result["totals"],
            "brands": result["brands"],
            "flags": result.get("flags", {}),
            "captured_clicks_view": captured,
        }, indent=2, ensure_ascii=False))
    else:
        print_summary(result, meta, captured)

    print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
