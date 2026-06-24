#!/usr/bin/env python3
"""
Demand Trajectory — year-over-year topic trend. For each keyword/topic, decide
whether demand is rising, stable, or declining, so the client knows where to
invest and where to exit.

Where seasonality answers "when within the year does demand peak", trajectory
answers the orthogonal question: "is the topic growing at all across years?" A
keyword can be wildly seasonal and still be dying year over year, or perfectly
flat within the year and quietly doubling. This skill measures the across-year
direction, not the within-year shape.

Each keyword carries a dated monthly volume time series (ideally 24 months for a
clean YoY comparison, but 12 is enough for a slope read). For every keyword the
analysis computes two independent signals:

  1. YoY growth — the last 12 months of volume versus the prior 12 months. This
     is the headline number a client cares about and it is naturally
     deseasonalized: comparing a full year to a full year cancels the within-year
     pattern. Only available when at least ~24 months exist.
  2. Trend slope — a least-squares line fit over the whole series, expressed as
     percent change per month relative to the series mean. This works even with a
     short (~12-month) history, where YoY is impossible. To keep the slope from
     being thrown off by seasonal swings, we fit it on a 12-month centered moving
     average of the series when the series is long enough to support one.

Classification is fully deterministic — no LLM, no model judgment. The same
series always produce the same YoY, slope, and label. The only network path is
the optional DataForSEO volume fetch, billed by DataForSEO, not by NodesHub.

Data sources (priority order):
  1. DataForSEO   keywords_data/google_ads/search_volume  (--source dfs).
                  Returns up to ~24 months of monthly_searches per keyword. Gated
                  behind DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD from env or
                  .claude/settings.local.json. Fails with a clear setup message
                  if absent.
  2. CSV / JSON   --series PATH. Per-keyword dated monthly volumes (long format
                  keyword,date,volume — or a JSON map). 12-24+ points per keyword.
  3. Hub feed     load_from_hub() — commented stub for a future pull from the
                  user's data.kubadzikowski.com feed. No networking implemented.

Keywords come from --file, --keywords, or the merger's by_query view. The --demo
fixture (a rising topic, a declining topic, a stable one, and a spiky-but-flat
one) lets the whole thing run with no key and no data file.

Usage:
    python3 analyze.py --demo
    python3 analyze.py --keywords "ai agents,fax machine" --source dfs --location 2840
    python3 analyze.py --file keywords.txt --series series.csv
    python3 analyze.py --rising-threshold 20

Output:
    data/demand-trajectory/{YYYY-MM-DD}.json  ->  { meta, keywords, portfolio,
                                                    recommendations }
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
_OUTPUT_DIR = _REPO_ROOT / "data" / "demand-trajectory"

_SETTINGS_CANDIDATES = [
    _REPO_ROOT / ".claude" / "settings.local.json",
    _REPO_ROOT / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]

# DataForSEO returns up to ~24 monthly_searches rows per keyword (year + month).
DFS_ENDPOINT = "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"

# --- classification thresholds (named constants) -----------------------------
# YoY percent change boundaries for the headline label.
RISING_YOY_THRESHOLD = 15.0      # YoY > +15% -> Rising
DECLINING_YOY_THRESHOLD = -15.0  # YoY < -15% -> Declining
# Slope (percent of mean per month) boundaries, used when YoY is unavailable
# (short history) or to flag Emerging / Fading on steep short series.
EMERGING_SLOPE_THRESHOLD = 1.5    # +1.5%/month on a short series -> Emerging
FADING_SLOPE_THRESHOLD = -1.5     # -1.5%/month on a short series -> Fading
# A "short" history (no full 24 months for a clean YoY).
SHORT_HISTORY_MONTHS = 24


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


def _parse_year_month(value):
    """Parse a date-ish label into (year, month). Returns None if unparseable.

    Accepts '2025-03', '2025/03', '2025-03-01', 'Mar 2025', '03-2025', etc.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # ISO-ish: 2025-03 or 2025-03-01 or 2025/03
    m = re.match(r"^(\d{4})[-/.](\d{1,2})", text)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return (y, mo)
    # 03-2025 / 03/2025
    m = re.match(r"^(\d{1,2})[-/.](\d{4})$", text)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return (y, mo)
    # 'Mar 2025' / 'March 2025' / '2025 Mar'
    months = {n: i + 1 for i, n in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"])}
    low = text.lower()
    name = next((n for n in months if n in low), None)
    yr = re.search(r"(\d{4})", text)
    if name and yr:
        return (int(yr.group(1)), months[name])
    return None


# --- series ingest (CSV / JSON) ----------------------------------------------

def _ordered_series(points):
    """Sort (year, month, volume) points chronologically -> list of floats.

    Duplicate (year, month) entries are summed defensively.
    """
    bucket = {}
    for (y, mo, vol) in points:
        bucket[(y, mo)] = bucket.get((y, mo), 0.0) + vol
    return [bucket[k] for k in sorted(bucket.keys())]


def load_series_csv(path):
    """Per-keyword dated monthly volumes from CSV -> {keyword: [floats]}.

    Long format expected: a keyword column, a date column, and a volume column.
    Date and volume column names are flexible (date/month/period, volume/searches/
    search_volume/value). The series is returned in chronological order.
    """
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return {}
    header = [_normalize_header(h) for h in rows[0]]

    def _col(names):
        for i, h in enumerate(header):
            if h in names:
                return i
        return None

    kw_col = _col({"keyword", "query", "term", "phrase", "kw"})
    date_col = _col({"date", "month", "period", "year_month", "yearmonth"})
    vol_col = _col({"volume", "search_volume", "searches", "value", "search volume"})
    if kw_col is None or date_col is None or vol_col is None:
        return {}

    per_kw = {}
    for r in rows[1:]:
        if max(kw_col, date_col, vol_col) >= len(r):
            continue
        kw = normalize_keyword(r[kw_col])
        if not kw:
            continue
        ym = _parse_year_month(r[date_col])
        if ym is None:
            continue
        per_kw.setdefault(kw, []).append((ym[0], ym[1], _to_float(r[vol_col])))
    return {kw: _ordered_series(pts) for kw, pts in per_kw.items()}


def _normalize_header(label):
    return re.sub(r"[._\-]+", " ", str(label).strip().lower()).strip()


def load_series_json(path):
    """Per-keyword dated monthly volumes from JSON -> {keyword: [floats]}.

    Accepts:
      { "keyword": [n, n, n, ...] }                       (already chronological)
      { "keyword": [{"date": "2025-03", "volume": n}] }   (dated points)
      [ {"keyword": "x", "series": [...]}, ... ]
      [ {"keyword": "x", "monthly_searches": [{"year":2025,"month":3,
                                               "search_volume": n}]} ]
    """
    data = json.loads(Path(path).read_text())
    out = {}

    if isinstance(data, dict):
        for kw, series in data.items():
            out[normalize_keyword(kw)] = _coerce_series(series)
        return out

    for row in data:
        kw = row.get("keyword") or row.get("query")
        if not kw:
            continue
        series = (row.get("series") or row.get("monthly") or row.get("volumes")
                  or row.get("monthly_searches"))
        out[normalize_keyword(kw)] = _coerce_series(series)
    return out


def _coerce_series(series):
    """Coerce various series encodings into a chronological list of floats."""
    if series is None:
        return []
    if isinstance(series, list):
        if series and isinstance(series[0], dict):
            # Dated points; sort by (year, month) when available, else by 'date'.
            points = []
            for entry in series:
                vol = _to_float(entry.get("search_volume",
                                          entry.get("volume", entry.get("value"))))
                year = entry.get("year")
                month = entry.get("month")
                if year is not None and month is not None:
                    points.append((int(year), int(month), vol))
                    continue
                ym = _parse_year_month(entry.get("date") or entry.get("period"))
                if ym is not None:
                    points.append((ym[0], ym[1], vol))
            return _ordered_series(points)
        # Plain chronological list of numbers.
        return [_to_float(v) for v in series]
    return []


def load_from_hub(keywords):
    """STUB — future pull from the user's data.kubadzikowski.com feed.

    Intentionally NOT implemented. When wired up, this would call the hub's
    trajectory endpoint (e.g. GET /api/trajectory?kw=...) and return a
    {keyword: [chronological monthly volumes]} dict, same shape as
    load_series_csv. Kept as a clearly-marked seam so the rest of the pipeline
    never assumes a single data source. No networking is performed here.
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
        "No key? Use --series PATH for a CSV/JSON of dated monthly volumes, "
        "or --demo to see the format."
    )


def fetch_series_dfs(keywords, location_code, language_code):
    """Fetch dated monthly volume series from DataForSEO search_volume (live).

    Returns {keyword: [chronological floats]}. The endpoint returns up to ~24
    months of monthly_searches per keyword. Raises RuntimeError with a setup
    message if credentials are missing, so the caller can fail gracefully.
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
            # monthly_searches is a list of {year, month, search_volume}.
            out[normalize_keyword(kw)] = _coerce_series(item.get("monthly_searches"))
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

def _moving_average(series, window):
    """Centered moving average. Returns a list the same length as the window
    coverage allows (len(series) - window + 1 points). Empty if too short.
    """
    if window <= 1 or len(series) < window:
        return list(series)
    out = []
    for i in range(len(series) - window + 1):
        chunk = series[i:i + window]
        out.append(sum(chunk) / window)
    return out


def least_squares_slope(series):
    """Least-squares slope of y over x = 0..n-1. Returns slope in volume/month."""
    n = len(series)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(series) / n
    num = sum((xs[i] - mean_x) * (series[i] - mean_y) for i in range(n))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def slope_pct_per_month(series):
    """Trend slope normalized as percent of the series mean per month.

    Deseasonalized lightly: when the series is at least 12 long, fit the slope on
    a 12-month centered moving average so a within-year spike does not masquerade
    as a trend. Otherwise fit on the raw series.
    """
    if len(series) < 2:
        return 0.0
    basis = _moving_average(series, 12) if len(series) >= 12 else series
    if len(basis) < 2:
        basis = series
    mean = sum(series) / len(series)
    if mean <= 0:
        return 0.0
    slope = least_squares_slope(basis)
    return round((slope / mean) * 100.0, 2)


def yoy_growth(series):
    """YoY percent change: last 12 months vs the prior 12. None if < 24 months.

    Comparing two full years cancels the within-year seasonal pattern, so this is
    naturally deseasonalized.
    """
    if len(series) < 24:
        return None
    last12 = sum(series[-12:])
    prior12 = sum(series[-24:-12])
    if prior12 <= 0:
        return None
    return round(((last12 - prior12) / prior12) * 100.0, 1)


def classify(yoy, slope, n_months,
             rising_threshold=RISING_YOY_THRESHOLD,
             declining_threshold=DECLINING_YOY_THRESHOLD):
    """Deterministic trajectory label from YoY growth and trend slope.

    Logic:
      - Long history (>= 24m, YoY available): YoY is the headline. > +15% Rising,
        < -15% Declining, otherwise Stable. The slope refines the edges: a Stable
        YoY with a steep slope is nudged toward Emerging/Fading.
      - Short history (< 24m, no YoY): fall back to the slope. Steep positive ->
        Emerging, steep negative -> Fading, otherwise Stable.
    """
    short = n_months < SHORT_HISTORY_MONTHS or yoy is None

    if not short:
        if yoy > rising_threshold:
            return "Rising"
        if yoy < declining_threshold:
            return "Declining"
        # Stable band by YoY, but let a steep slope reveal an inflection.
        if slope >= EMERGING_SLOPE_THRESHOLD:
            return "Emerging"
        if slope <= FADING_SLOPE_THRESHOLD:
            return "Fading"
        return "Stable"

    # Short history: slope-only read.
    if slope >= EMERGING_SLOPE_THRESHOLD:
        return "Emerging"
    if slope <= FADING_SLOPE_THRESHOLD:
        return "Fading"
    return "Stable"


def analyze_keyword(keyword, series,
                    rising_threshold=RISING_YOY_THRESHOLD,
                    declining_threshold=DECLINING_YOY_THRESHOLD):
    """Compute YoY, slope, latest-12m volume, and trajectory label for one kw."""
    n = len(series)
    last12 = round(sum(series[-12:]), 1) if n >= 1 else 0.0
    yoy = yoy_growth(series)
    slope = slope_pct_per_month(series)
    label = classify(yoy, slope, n, rising_threshold, declining_threshold)
    return {
        "keyword": keyword,
        "months_of_history": n,
        "latest_12m_volume": int(round(last12)),
        "yoy_pct": yoy,
        "slope_pct_per_month": slope,
        "classification": label,
    }


# --- portfolio + recommendations ---------------------------------------------

_RISING_LABELS = ("Rising", "Emerging")
_DECLINING_LABELS = ("Declining", "Fading")


def build_portfolio(rows):
    """Summarize the set: how much volume and how many keywords sit in each
    trajectory bucket. Volume share answers 'where is my demand actually going'.
    """
    counts = {}
    volumes = {}
    total_vol = 0.0
    for r in rows:
        label = r["classification"]
        counts[label] = counts.get(label, 0) + 1
        volumes[label] = volumes.get(label, 0.0) + r["latest_12m_volume"]
        total_vol += r["latest_12m_volume"]

    def _share(group):
        v = sum(volumes.get(lbl, 0.0) for lbl in group)
        return round((v / total_vol) * 100.0, 1) if total_vol > 0 else 0.0

    return {
        "keyword_count": len(rows),
        "total_latest_12m_volume": int(round(total_vol)),
        "counts_by_class": counts,
        "volume_by_class": {k: int(round(v)) for k, v in volumes.items()},
        "rising_volume_share_pct": _share(_RISING_LABELS),
        "declining_volume_share_pct": _share(_DECLINING_LABELS),
        "verdict": _portfolio_verdict(_share(_RISING_LABELS), _share(_DECLINING_LABELS)),
    }


def _portfolio_verdict(rising_share, declining_share):
    if rising_share >= 60:
        return "Growing — most demand sits on rising topics. Invest into the leaders."
    if declining_share >= 60:
        return "Shrinking — most demand sits on declining topics. Replace them before the floor drops out."
    if rising_share >= declining_share:
        return "Mixed, tilting up — more demand is growing than fading, but rebalance toward the rising side."
    return "Mixed, tilting down — more demand is fading than growing. Source new rising topics now."


def build_recommendations(rows):
    """Concrete invest/exit calls. Rising/Emerging -> double down (biggest first);
    Declining/Fading -> phase out (biggest bleeders first).
    """
    rising = sorted(
        [r for r in rows if r["classification"] in _RISING_LABELS],
        key=lambda r: (-r["latest_12m_volume"]),
    )
    declining = sorted(
        [r for r in rows if r["classification"] in _DECLINING_LABELS],
        key=lambda r: (r["latest_12m_volume"]),  # smallest survivors are nearest to gone
        reverse=False,
    )
    recs = []
    for r in rising:
        signal = (f"YoY +{r['yoy_pct']}%" if r["yoy_pct"] is not None
                  else f"slope +{r['slope_pct_per_month']}%/mo")
        recs.append({
            "action": "double_down",
            "keyword": r["keyword"],
            "reason": (f"Double down on \"{r['keyword']}\" ({r['classification'].lower()}, "
                       f"{signal}). Demand is climbing — expand and refresh this topic."),
        })
    for r in declining:
        signal = (f"YoY {r['yoy_pct']}%" if r["yoy_pct"] is not None
                  else f"slope {r['slope_pct_per_month']}%/mo")
        recs.append({
            "action": "phase_out",
            "keyword": r["keyword"],
            "reason": (f"Phase out \"{r['keyword']}\" ({r['classification'].lower()}, "
                       f"{signal}). Demand is draining — stop investing and redirect effort."),
        })
    return recs


# --- output ------------------------------------------------------------------

def _fmt_pct(value, sign=True):
    if value is None:
        return "n/a"
    s = f"{value:+.1f}" if sign else f"{value:.1f}"
    return f"{s}%"


def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def print_summary(report):
    meta = report["meta"]
    print()
    print("## Demand Trajectory Report")
    print(f"**Keywords:** {meta['keyword_count']} | "
          f"**Source:** {meta['volume_source']} | "
          f"**Date:** {meta['date']}")
    print()
    print("### Per-keyword trajectory")
    print("| Keyword | Latest 12m vol | YoY | Slope %/mo | Trajectory |")
    print("|---------|----------------|-----|------------|------------|")
    for r in report["keywords"]:
        print(f"| {r['keyword']} | {r['latest_12m_volume']:,} | "
              f"{_fmt_pct(r['yoy_pct'])} | "
              f"{r['slope_pct_per_month']:+.2f} | {r['classification']} |")
    print()

    pf = report["portfolio"]
    print("### Portfolio summary")
    counts = ", ".join(f"{k}: {v}" for k, v in sorted(pf["counts_by_class"].items()))
    print(f"**By class:** {counts}")
    print(f"**Rising volume share:** {pf['rising_volume_share_pct']}% | "
          f"**Declining volume share:** {pf['declining_volume_share_pct']}%")
    print(f"**Verdict:** {pf['verdict']}")
    print()

    print("### Recommendations (invest vs exit)")
    if not report["recommendations"]:
        print("  (no clear rising or declining topics — the set is steady)")
    for rec in report["recommendations"]:
        print(f"  - {rec['reason']}")
    print()
    print(f"Report saved to: {meta['output_path']}")
    print("Cost: 0 NodesHub tokens (DataForSEO billed separately if --source dfs).")


# --- demo fixture ------------------------------------------------------------

def _demo_series():
    """Four 24-month series (chronological), each a distinct trajectory archetype.

    - Rising: trends up year over year (clear positive YoY + slope).
    - Declining: trends down year over year.
    - Stable: flat with mild noise (YoY near zero).
    - Spiky-but-flat: large seasonal swings but no across-year drift — the case
      that fools a naive slope; the 12-month moving-average deseasonalization and
      the full-year YoY both correctly call it Stable.
    """
    # 24 months. Index 0 = two years ago Jan ... index 23 = last Dec.
    rising = [
        100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200, 210,   # year 1
        230, 250, 270, 290, 310, 330, 350, 370, 390, 410, 430, 450,   # year 2 (~+90% YoY)
    ]
    declining = [
        900, 880, 860, 840, 820, 800, 780, 760, 740, 720, 700, 680,   # year 1
        560, 540, 520, 500, 480, 460, 440, 420, 400, 380, 360, 340,   # year 2 (~-44% YoY)
    ]
    stable = [
        500, 510, 495, 505, 500, 498, 502, 497, 503, 499, 501, 500,   # year 1
        503, 498, 501, 499, 502, 500, 497, 504, 499, 501, 498, 502,   # year 2 (~flat)
    ]
    # Big summer swing every year, identical across years -> flat trajectory.
    spiky_flat = [
        200, 260, 520, 1200, 2600, 4200, 4400, 3200, 1400, 600, 300, 220,
        205, 255, 525, 1205, 2605, 4205, 4405, 3205, 1405, 605, 305, 225,
    ]
    return {
        "ai agents": [float(v) for v in rising],
        "fax machine": [float(v) for v in declining],
        "project management software": [float(v) for v in stable],
        "garden furniture": [float(v) for v in spiky_flat],
    }


# --- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Demand Trajectory")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Year-over-year demand trajectory: is each topic rising, stable, or declining.")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the bundled rising/declining/stable/spiky-flat fixture (no key, no data)")
    parser.add_argument("--keywords", help="Comma-separated keywords")
    parser.add_argument("--file", help="Path to a newline-delimited keyword file")
    parser.add_argument("--series", help="CSV/JSON of per-keyword dated monthly volumes")
    parser.add_argument("--source", choices=["dfs", "file", "hub"], default=None,
                        help="Series source: dfs (DataForSEO), file (--series), hub (stub)")
    parser.add_argument("--location", default="2840",
                        help="DataForSEO location_code (default 2840 = US)")
    parser.add_argument("--language", default="en",
                        help="DataForSEO language_code (default en)")
    parser.add_argument("--rising-threshold", type=float, default=RISING_YOY_THRESHOLD,
                        help=f"YoY %% above which a topic is Rising (default {RISING_YOY_THRESHOLD})")
    parser.add_argument("--declining-threshold", type=float, default=DECLINING_YOY_THRESHOLD,
                        help=f"YoY %% below which a topic is Declining (default {DECLINING_YOY_THRESHOLD})")
    parser.add_argument("--raw", action="store_true",
                        help="Print the raw JSON report instead of the summary")
    args = parser.parse_args()

    # Threshold overrides flow into the deterministic classifier as arguments.
    rising_threshold = args.rising_threshold
    declining_threshold = args.declining_threshold

    # --- resolve keywords + series ---
    if args.demo:
        keyword_series = _demo_series()
        volume_source = "demo-fixture"
    else:
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

        source = args.source or ("file" if args.series else "dfs")
        if source == "file":
            if not args.series:
                print("--source file needs --series PATH.", file=sys.stderr)
                sys.exit(1)
            path = Path(args.series)
            loaded = (load_series_json(path) if path.suffix.lower() == ".json"
                      else load_series_csv(path))
            volume_source = f"file:{path.name}"
        elif source == "hub":
            loaded = load_from_hub(norm_keywords)
            volume_source = "hub-stub"
            if not loaded:
                print("Hub source is a stub and returns no data. Use --source dfs "
                      "or --series PATH.", file=sys.stderr)
                sys.exit(1)
        else:  # dfs
            try:
                loaded = fetch_series_dfs(keywords, args.location, args.language)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(1)
            volume_source = "dataforseo"

        keyword_series = {k: loaded[k] for k in norm_keywords
                          if k in loaded and loaded[k]}
        missing = [k for k in norm_keywords if k not in keyword_series]
        if missing:
            print(f"Note: no series data for {len(missing)} keyword(s): "
                  f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                  file=sys.stderr)
        if not keyword_series:
            print("No monthly series resolved for any keyword. Check the source.",
                  file=sys.stderr)
            sys.exit(1)

    # --- deterministic analysis ---
    rows = [analyze_keyword(kw, series, rising_threshold, declining_threshold)
            for kw, series in keyword_series.items()]
    # Sort: rising first (by latest volume), then stable, then declining.
    _order = {"Rising": 0, "Emerging": 1, "Stable": 2, "Fading": 3, "Declining": 4}
    rows.sort(key=lambda r: (_order.get(r["classification"], 9), -r["latest_12m_volume"]))

    portfolio = build_portfolio(rows)
    recommendations = build_recommendations(rows)

    output_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "date": str(date.today()),
            "keyword_count": len(rows),
            "volume_source": volume_source,
            "rising_threshold": rising_threshold,
            "declining_threshold": declining_threshold,
            "output_path": str(output_path),
            "note": ("Per keyword: YoY = last 12 months vs prior 12 (deseasonalized "
                     "by full-year comparison, needs 24 months); slope = least-squares "
                     "%/month on a 12-month moving average (works at 12 months). "
                     "Deterministic; no LLM."),
        },
        "keywords": rows,
        "portfolio": portfolio,
        "recommendations": recommendations,
    }

    save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)


if __name__ == "__main__":
    main()
