#!/usr/bin/env python3
"""
Seasonality — build ONE site-level seasonality curve from a keyword set so you
can see when demand peaks, when to publish, and which topics fill the off-season
valley.

Each keyword carries 12 monthly search volumes (Jan..Dec). The site curve is the
sum of those monthly volumes across keywords, weighted by each keyword's own
annual volume (so a 50k/yr head term moves the curve more than a 500/yr tail
term). The curve is normalized to an index where the mean month = 100, which
makes "how spiky is the site" readable at a glance.

Detection is fully deterministic — no LLM, no model judgment. The same volumes
always produce the same curve, the same peak/trough, and the same diversification
list. The only network path is the optional DataForSEO volume fetch, which is
billed by DataForSEO, not by NodesHub.

Data sources (priority order):
  1. DataForSEO   keywords_data/google_ads/search_volume  (--source dfs).
                  Gated behind DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD read from
                  .claude/settings.local.json env. Fails with a clear setup
                  message if absent.
  2. CSV / JSON   --volumes PATH. Per-keyword monthly volumes; columns are
                  normalized (jan/january/m1/month_1 ... all accepted).
  3. Hub feed     load_from_hub() — commented stub for a future pull from the
                  user's data.kubadzikowski.com feed. No networking implemented.

Keywords come from --file, --keywords, or the merger's by_query view. The --demo
fixture (a summer-peaking set + a counter-seasonal winter set) lets the whole
thing run with no key and no data file.

Usage:
    python3 analyze.py --demo
    python3 analyze.py --keywords "garden furniture,patio set" --source dfs --location 2840
    python3 analyze.py --file keywords.txt --volumes volumes.csv
    python3 analyze.py --lead-weeks 8 --raw

Output:
    data/seasonality/{YYYY-MM-DD}.json  ->  { meta, site_curve, peaks, troughs,
                                              publishing_calendar, diversification }
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# --- paths -------------------------------------------------------------------
_SKILL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MERGED_DIR = _REPO_ROOT / "data" / "merged"
_OUTPUT_DIR = _REPO_ROOT / "data" / "seasonality"

_SETTINGS_CANDIDATES = [
    _REPO_ROOT / ".claude" / "settings.local.json",
    _REPO_ROOT / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# DataForSEO returns month_index as a calendar month number (1=Jan..12=Dec).
DFS_ENDPOINT = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"


# --- parsing helpers ---------------------------------------------------------

def _to_float(value, default=0.0):
    """Parse '1.2k', '12,345', '4.5%', numbers -> float. default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if not text or text in ("-", "."):
        return default
    mult = 1.0
    if text.endswith("k"):
        mult, text = 1000.0, text[:-1]
    elif text.endswith("m"):
        mult, text = 1_000_000.0, text[:-1]
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in ("", "-", "."):
        return default
    try:
        return float(cleaned) * mult
    except ValueError:
        return default


def normalize_keyword(raw):
    """Lowercase + collapse whitespace for keyword joins."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().lower())


# --- month-column normalization (CSV/JSON ingest) ----------------------------

# Map a normalized header label onto a 0-based month index.
_MONTH_ALIASES = {}
_FULL = ["january", "february", "march", "april", "may", "june",
         "july", "august", "september", "october", "november", "december"]
for _i, (_abbr, _full) in enumerate(zip(MONTHS, _FULL)):
    for _label in (_abbr.lower(), _full, f"m{_i + 1}", f"month{_i + 1}",
                   f"month {_i + 1}", str(_i + 1)):
        _MONTH_ALIASES[_label] = _i


def _normalize_header(label):
    return re.sub(r"[._\-]+", " ", str(label).strip().lower()).strip()


def _month_columns(header):
    """Return {column_index: month_index} for every recognized month column."""
    mapping = {}
    for col, label in enumerate(header):
        norm = _normalize_header(label)
        if norm in _MONTH_ALIASES:
            mapping[col] = _MONTH_ALIASES[norm]
    return mapping


def _keyword_column(header):
    aliases = {"keyword", "query", "term", "phrase", "keywords", "kw"}
    for col, label in enumerate(header):
        if _normalize_header(label) in aliases:
            return col
    return 0  # default to first column


# --- volume ingest -----------------------------------------------------------

def load_volumes_csv(path):
    """Per-keyword monthly volumes from CSV -> {keyword: [12 floats]}.

    Wide format only: one row per keyword, one column per month (any of the
    accepted month aliases). Missing months default to 0.
    """
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return {}
    header = rows[0]
    kw_col = _keyword_column(header)
    month_cols = _month_columns(header)
    if not month_cols:
        return {}

    out = {}
    for r in rows[1:]:
        if not r or kw_col >= len(r):
            continue
        kw = r[kw_col].strip()
        if not kw:
            continue
        months = [0.0] * 12
        for col, mi in month_cols.items():
            if col < len(r):
                months[mi] = _to_float(r[col])
        out[normalize_keyword(kw)] = months
    return out


def load_volumes_json(path):
    """Per-keyword monthly volumes from JSON.

    Accepts either:
      { "keyword": [12 numbers], ... }
      [ {"keyword": "x", "monthly": [12]}, ... ]
      [ {"keyword": "x", "monthly_searches": [{"month": 1, "search_volume": n}]} ]
    """
    data = json.loads(Path(path).read_text())
    out = {}

    if isinstance(data, dict):
        for kw, months in data.items():
            out[normalize_keyword(kw)] = _coerce_month_list(months)
        return out

    for row in data:
        kw = row.get("keyword") or row.get("query")
        if not kw:
            continue
        months = (row.get("monthly") or row.get("monthly_volumes")
                  or row.get("monthly_searches") or row.get("volumes"))
        out[normalize_keyword(kw)] = _coerce_month_list(months)
    return out


def _coerce_month_list(months):
    """Coerce various month encodings into a list of 12 floats (Jan..Dec)."""
    result = [0.0] * 12
    if months is None:
        return result
    if isinstance(months, dict):
        # {"1": n, ...} or {"jan": n, ...}
        for key, val in months.items():
            mi = _MONTH_ALIASES.get(_normalize_header(key))
            if mi is not None:
                result[mi] = _to_float(val)
        return result
    if isinstance(months, list):
        if months and isinstance(months[0], dict):
            # DataForSEO shape: [{"month": 1, "search_volume": n}, ...]
            for entry in months:
                m = entry.get("month")
                if m is None:
                    continue
                mi = int(m) - 1
                if 0 <= mi < 12:
                    result[mi] = _to_float(entry.get("search_volume",
                                                      entry.get("value")))
            return result
        # Plain list of up to 12 numbers.
        for i, val in enumerate(months[:12]):
            result[i] = _to_float(val)
    return result


def load_from_hub(keywords):
    """STUB — future pull from the user's data.kubadzikowski.com feed.

    Intentionally NOT implemented. When wired up, this would call the hub's
    seasonality endpoint (e.g. GET /api/seasonality?kw=...) and return a
    {keyword: [12 monthly volumes]} dict, same shape as load_volumes_csv. Kept
    as a clearly-marked seam so the rest of the pipeline never assumes a single
    data source. No networking is performed here.
    """
    return {}


# --- DataForSEO adapter ------------------------------------------------------

def _load_dfs_credentials():
    """Read DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD from env or settings.local.json."""
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if login and password:
        return login, password
    for path in _SETTINGS_CANDIDATES:
        if path.is_file():
            try:
                env = json.loads(path.read_text()).get("env", {})
            except (json.JSONDecodeError, OSError):
                continue
            login = login or env.get("DATAFORSEO_LOGIN")
            password = password or env.get("DATAFORSEO_PASSWORD")
            if login and password:
                return login, password
    return login, password


def _dfs_setup_message():
    settings_path = _SETTINGS_CANDIDATES[0]
    return (
        "DataForSEO credentials not found.\n\n"
        "Add them to your settings env, then re-run with --source dfs:\n"
        f"  File: {settings_path}\n"
        '  Add:  { "env": { "DATAFORSEO_LOGIN": "you@example.com", '
        '"DATAFORSEO_PASSWORD": "your-password" } }\n\n'
        "Or export them in the shell:\n"
        "  export DATAFORSEO_LOGIN=you@example.com\n"
        "  export DATAFORSEO_PASSWORD=your-password\n\n"
        "No key? Use --volumes PATH for a CSV/JSON of monthly volumes, "
        "or --demo to see the format."
    )


def fetch_volumes_dfs(keywords, location_code, language_code):
    """Fetch monthly volumes from DataForSEO google_ads/search_volume (live).

    Returns {keyword: [12 floats]}. Raises RuntimeError with a setup message if
    credentials are missing, so the caller can fail gracefully.
    """
    login, password = _load_dfs_credentials()
    if not (login and password):
        raise RuntimeError(_dfs_setup_message())

    import base64
    import urllib.request
    import urllib.error

    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    payload = json.dumps([{
        "keywords": list(keywords),
        "location_code": int(location_code),
        "language_code": language_code,
    }]).encode()

    req = urllib.request.Request(
        DFS_ENDPOINT, data=payload,
        headers={"Authorization": f"Basic {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DataForSEO HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DataForSEO request failed: {exc.reason}")

    out = {}
    for task in body.get("tasks", []):
        for item in (task.get("result") or []):
            kw = item.get("keyword")
            if not kw:
                continue
            out[normalize_keyword(kw)] = _coerce_month_list(item.get("monthly_searches"))
    return out


# --- keyword ingest ----------------------------------------------------------

def load_keywords_file(path):
    text = Path(path).read_text()
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_keywords_from_merger():
    """Pull the client's queries from the newest merged dataset (by_query)."""
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"))
    try:
        from merge import load_merged
    except ImportError:
        return []
    try:
        merged = load_merged()
    except FileNotFoundError:
        return []
    return [row.get("query") for row in merged.get("by_query", []) if row.get("query")]


# --- core analysis (deterministic) -------------------------------------------

def annual_volume(months):
    return sum(months)


def build_site_curve(keyword_volumes):
    """Aggregate per-keyword monthly volumes into a site curve.

    The site monthly total is the sum of every keyword's volume in that month,
    which is inherently weighted by each keyword's annual volume (a big keyword
    contributes more absolute volume in every month). Then normalize to an index
    where the mean month = 100.

    Returns (raw_monthly_totals[12], index[12]).
    """
    raw = [0.0] * 12
    for months in keyword_volumes.values():
        for i in range(12):
            raw[i] += months[i]

    total = sum(raw)
    if total <= 0:
        return raw, [100.0] * 12  # flat — no demand signal
    mean_month = total / 12.0
    index = [round((raw[i] / mean_month) * 100.0, 1) for i in range(12)]
    return raw, index


def find_peaks_troughs(index):
    """Identify peak month(s) and trough month(s) plus the peak/trough ratio.

    Peaks/troughs include ties (months within 1 index point of the extreme).
    """
    hi = max(index)
    lo = min(index)
    peaks = [i for i, v in enumerate(index) if hi - v <= 1.0]
    troughs = [i for i, v in enumerate(index) if v - lo <= 1.0]
    ratio = round(hi / lo, 2) if lo > 0 else None
    return {
        "peak_months": [MONTHS[i] for i in peaks],
        "peak_index": round(hi, 1),
        "trough_months": [MONTHS[i] for i in troughs],
        "trough_index": round(lo, 1),
        "peak_trough_ratio": ratio,
        "spikiness": _spikiness_label(ratio),
        "_peak_indices": peaks,
        "_trough_indices": troughs,
    }


def _spikiness_label(ratio):
    if ratio is None:
        return "unknown"
    if ratio >= 4.0:
        return "very spiky"
    if ratio >= 2.0:
        return "spiky"
    if ratio >= 1.4:
        return "moderate"
    return "flat"


def publishing_calendar(peak_indices, lead_weeks):
    """For each peak month, recommend the month to publish BEFORE it.

    Lead time in weeks is converted to whole months (rounded), so content has
    time to mature/index before demand arrives. Returns concrete pairs.
    """
    lead_months = max(1, round(lead_weeks / 4.345))  # avg weeks per month
    calendar = []
    seen = set()
    for pi in peak_indices:
        publish_idx = (pi - lead_months) % 12
        key = (publish_idx, pi)
        if key in seen:
            continue
        seen.add(key)
        calendar.append({
            "publish_month": MONTHS[publish_idx],
            "pays_off_month": MONTHS[pi],
            "lead_weeks": lead_weeks,
            "lead_months": lead_months,
            "note": (f"Publish in {MONTHS[publish_idx]} so it matures before the "
                     f"{MONTHS[pi]} demand peak."),
        })
    return calendar


def _keyword_peak_month(months):
    """Index of a single keyword's own peak month (Jan..Dec)."""
    if annual_volume(months) <= 0:
        return None
    return max(range(12), key=lambda i: months[i])


def _months_apart(a, b):
    """Circular distance between two month indices (0..6)."""
    d = abs(a - b) % 12
    return min(d, 12 - d)


def find_diversification(keyword_volumes, peak_indices, min_volume=1.0):
    """Counter-seasonal keywords: those whose own peak is OPPOSITE the site peak.

    A keyword fills the off-season valley when its peak month is at least 4
    months away from every site peak (i.e. it sells when the site is quiet).
    Returns rows sorted by how far their peak sits from the site peak, then by
    annual volume — the strongest valley-fillers first.
    """
    if not peak_indices:
        return []
    rows = []
    for kw, months in keyword_volumes.items():
        vol = annual_volume(months)
        if vol < min_volume:
            continue
        kw_peak = _keyword_peak_month(months)
        if kw_peak is None:
            continue
        distance = min(_months_apart(kw_peak, pi) for pi in peak_indices)
        if distance >= 4:  # counter-seasonal: opposite half of the year
            rows.append({
                "keyword": kw,
                "peak_month": MONTHS[kw_peak],
                "months_from_site_peak": distance,
                "annual_volume": int(round(vol)),
            })
    rows.sort(key=lambda r: (-r["months_from_site_peak"], -r["annual_volume"]))
    return rows


# --- output ------------------------------------------------------------------

def render_heatmap(index, peak_indices, trough_indices, width=40):
    """12-month ASCII bar chart of the site index (mean month = 100)."""
    hi = max(index) or 1.0
    lines = []
    for i, val in enumerate(index):
        bar = "#" * int(round((val / hi) * width))
        mark = ""
        if i in peak_indices:
            mark = "  <- PEAK"
        elif i in trough_indices:
            mark = "  <- trough"
        lines.append(f"  {MONTHS[i]}  {val:6.1f}  |{bar}{mark}")
    return "\n".join(lines)


def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def print_summary(report):
    pt = report["peaks_troughs"]
    print()
    print("## Seasonality Report")
    print(f"**Keywords:** {report['meta']['keyword_count']} | "
          f"**Source:** {report['meta']['volume_source']} | "
          f"**Date:** {report['meta']['date']}")
    print()
    print("### Site seasonality curve (index, mean month = 100)")
    print(render_heatmap(report["site_index"],
                         pt["_peak_indices"], pt["_trough_indices"]))
    print()
    print(f"**Peak:** {', '.join(pt['peak_months'])} "
          f"(index {pt['peak_index']}) | "
          f"**Trough:** {', '.join(pt['trough_months'])} "
          f"(index {pt['trough_index']})")
    print(f"**Peak/trough ratio:** {pt['peak_trough_ratio']} "
          f"({pt['spikiness']}) — how spiky the site is.")
    print()

    print("### Publishing calendar (lead time before each peak)")
    if not report["publishing_calendar"]:
        print("  (no peaks identified)")
    for row in report["publishing_calendar"]:
        print(f"  Publish in {row['publish_month']} -> pays off in "
              f"{row['pays_off_month']}  ({row['lead_weeks']}w lead)")
    print()

    print("### Diversification — topics that fill the off-season valley")
    div = report["diversification"]
    if not div:
        print("  None. Every keyword peaks with the site — demand is concentrated "
              "in one window. Consider sourcing counter-seasonal topics.")
    else:
        print("  These keywords peak OPPOSITE the site peak. Cover them to earn "
              "traffic when the main season is quiet.")
        print()
        print("  | Keyword | Peaks in | Months from site peak | Annual volume |")
        print("  |---------|----------|-----------------------|---------------|")
        for r in div:
            print(f"  | {r['keyword']} | {r['peak_month']} | "
                  f"{r['months_from_site_peak']} | {r['annual_volume']:,} |")
    print()
    print(f"Report saved to: {report['meta']['output_path']}")
    print("Cost: 0 NodesHub tokens (DataForSEO billed separately if --source dfs).")


# --- demo fixture ------------------------------------------------------------

def _demo_volumes():
    """A summer-peaking set + a counter-seasonal winter set.

    Summer keywords peak Jun-Aug; winter keywords peak Dec-Jan. The site curve
    leans summer (more/bigger summer keywords), so the winter set surfaces as
    the off-season diversification list.
    """
    summer = [200, 240, 600, 1400, 3200, 6000, 6800, 5200, 2400, 900, 400, 220]
    summer2 = [120, 150, 380, 900, 2100, 3900, 4400, 3300, 1500, 600, 260, 140]
    winter = [3800, 2600, 900, 400, 220, 180, 170, 200, 360, 900, 2400, 4200]
    winter2 = [2100, 1500, 600, 280, 160, 130, 120, 150, 240, 560, 1400, 2300]
    return {
        "garden furniture": [float(v) for v in summer],
        "patio umbrella": [float(v) for v in summer2],
        "snow boots": [float(v) for v in winter],
        "christmas lights": [float(v) for v in winter2],
    }


# --- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Seasonality")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Build a site-level seasonality curve from a keyword set.")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the bundled summer+winter fixture (no key, no data)")
    parser.add_argument("--keywords", help="Comma-separated keywords")
    parser.add_argument("--file", help="Path to a newline-delimited keyword file")
    parser.add_argument("--volumes", help="CSV/JSON of per-keyword monthly volumes")
    parser.add_argument("--source", choices=["dfs", "file", "hub"], default=None,
                        help="Volume source: dfs (DataForSEO), file (--volumes), hub (stub)")
    parser.add_argument("--location", default="2840",
                        help="DataForSEO location_code (default 2840 = US)")
    parser.add_argument("--language", default="en",
                        help="DataForSEO language_code (default en)")
    parser.add_argument("--lead-weeks", type=int, default=6,
                        help="Lead time before a peak to publish (default 6)")
    parser.add_argument("--raw", action="store_true",
                        help="Print the raw JSON report instead of the summary")
    args = parser.parse_args()

    # --- resolve keywords + volumes ---
    if args.demo:
        keyword_volumes = _demo_volumes()
        volume_source = "demo-fixture"
    else:
        # 1. keywords
        if args.keywords:
            keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]
        elif args.file:
            keywords = load_keywords_file(args.file)
        else:
            keywords = load_keywords_from_merger()
        if not keywords:
            print("No keywords provided. Use --keywords, --file, the merger's "
                  "by_query view, or --demo.", file=sys.stderr)
            sys.exit(1)
        norm_keywords = [normalize_keyword(k) for k in keywords]

        # 2. volumes — pick source
        source = args.source or ("file" if args.volumes else "dfs")
        if source == "file":
            if not args.volumes:
                print("--source file needs --volumes PATH.", file=sys.stderr)
                sys.exit(1)
            path = Path(args.volumes)
            loaded = (load_volumes_json(path) if path.suffix.lower() == ".json"
                      else load_volumes_csv(path))
            volume_source = f"file:{path.name}"
        elif source == "hub":
            loaded = load_from_hub(norm_keywords)
            volume_source = "hub-stub"
            if not loaded:
                print("Hub source is a stub and returns no data. Use --source dfs "
                      "or --volumes PATH.", file=sys.stderr)
                sys.exit(1)
        else:  # dfs
            try:
                loaded = fetch_volumes_dfs(keywords, args.location, args.language)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(1)
            volume_source = "dataforseo"

        # Keep only keywords we have volumes for; warn about gaps.
        keyword_volumes = {k: loaded[k] for k in norm_keywords if k in loaded}
        missing = [k for k in norm_keywords if k not in loaded]
        if missing:
            print(f"Note: no volume data for {len(missing)} keyword(s): "
                  f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                  file=sys.stderr)
        if not keyword_volumes:
            print("No monthly volumes resolved for any keyword. Check the source.",
                  file=sys.stderr)
            sys.exit(1)

    # --- deterministic analysis ---
    raw_curve, site_index = build_site_curve(keyword_volumes)
    pt = find_peaks_troughs(site_index)
    calendar = publishing_calendar(pt["_peak_indices"], args.lead_weeks)
    diversification = find_diversification(keyword_volumes, pt["_peak_indices"])

    output_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "date": str(date.today()),
            "keyword_count": len(keyword_volumes),
            "volume_source": volume_source,
            "lead_weeks": args.lead_weeks,
            "output_path": str(output_path),
            "note": ("Site curve = sum of per-keyword monthly volumes (weighted "
                     "by each keyword's annual volume), normalized to mean month "
                     "= 100. Deterministic; no LLM."),
        },
        "site_raw_monthly": [round(v, 1) for v in raw_curve],
        "site_index": site_index,
        "months": MONTHS,
        "peaks_troughs": pt,
        "publishing_calendar": calendar,
        "diversification": diversification,
    }

    save_report(report)

    if args.raw:
        # Drop private helper keys from the raw dump.
        clean_pt = {k: v for k, v in pt.items() if not k.startswith("_")}
        report["peaks_troughs"] = clean_pt
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)


if __name__ == "__main__":
    main()
