#!/usr/bin/env python3
"""
Content Gap — the classic content/keyword gap: keywords your competitors rank
for that you don't (or rank worse for). The output is a prioritized list of
topics to write, ranked by how much traffic they could realistically win.

Why DataForSEO is needed here: NodesHub is SERP-only. It can tell you who ranks
for ONE keyword, but it cannot export the full set of keywords a whole domain
ranks for. The keyword universe for a gap analysis is exactly that — every
keyword each competitor ranks for — so it has to come from a source that knows a
domain's ranked-keyword footprint. DataForSEO's
`dataforseo_labs/google/ranked_keywords` returns that footprint per domain.
NodesHub is then used only to verify the live SERP for a selected gap keyword
(`--verify-serp`, 1 token per keyword).

Detection is fully deterministic — no LLM, no model judgment. The same ranked
keywords always produce the same gap classification, the same tables, and the
same potential ranking. The only network paths are the optional DataForSEO fetch
(billed by DataForSEO) and the optional NodesHub SERP verification.

Data sources (pluggable):
  1. DataForSEO   dataforseo_labs/google/ranked_keywords for --domain and each
                  --competitors entry. Gated behind DATAFORSEO_LOGIN /
                  DATAFORSEO_PASSWORD (env or .claude/settings.local.json).
                  Fails with a clear setup message if absent.
  2. CSV / JSON   --mine PATH (your domain) and --competitor PATH (repeatable).
                  Exported ranked-keyword lists; columns normalized to
                  (keyword, position, volume). Your own ranked keywords can also
                  come from GSC by_query via the merger when --mine is omitted.
  3. --demo       your domain + 2 competitors with overlapping and
                  non-overlapping ranked keywords. Runs with no key, no data.

Usage:
    python3 analyze.py --demo
    python3 analyze.py --domain you.com --competitors "a.com,b.com" --source dfs --location 2840
    python3 analyze.py --mine you.csv --competitor a.csv --competitor b.csv
    python3 analyze.py --demo --verify-serp --gl us --hl en

Output:
    data/content-gap/{YYYY-MM-DD}.json  ->  { meta, summary, missing, weak,
                                              shared_count }
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
_OUTPUT_DIR = _REPO_ROOT / "data" / "content-gap"

_SETTINGS_CANDIDATES = [
    _REPO_ROOT / ".claude" / "settings.local.json",
    _REPO_ROOT / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]

# A keyword is "ranked" for gap purposes if its position is within this window.
DEFAULT_RANK_WINDOW = 20
# You count as "weak" only if a competitor beats you by at least this many slots.
DEFAULT_WEAK_MARGIN = 5

DFS_ENDPOINT = ("https://api.dataforseo.com/v3/dataforseo_labs/google/"
                "ranked_keywords/live")


# --- parsing helpers ---------------------------------------------------------

def _to_float(value, default=None):
    """Parse '1.2k', '12,345', '4.5%', numbers -> float. default on failure."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace(",", "")
    if not text or text in ("-", ".", "n/a"):
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


def _normalize_header(label):
    return re.sub(r"[._\-]+", " ", str(label).strip().lower()).strip()


# --- CSV / JSON ingest -------------------------------------------------------

_KEYWORD_ALIASES = {"keyword", "query", "term", "phrase", "keywords", "kw"}
_POSITION_ALIASES = {"position", "pos", "rank", "ranking", "rank absolute",
                     "rank_absolute", "serp position", "rank group"}
_VOLUME_ALIASES = {"volume", "search volume", "searches", "sv", "avg monthly searches",
                   "search_volume", "monthly searches", "vol"}


def _resolve_columns(header):
    """Map a header row onto keyword / position / volume column indices."""
    kw_col, pos_col, vol_col = None, None, None
    for col, label in enumerate(header):
        norm = _normalize_header(label)
        if kw_col is None and norm in _KEYWORD_ALIASES:
            kw_col = col
        elif pos_col is None and norm in _POSITION_ALIASES:
            pos_col = col
        elif vol_col is None and norm in _VOLUME_ALIASES:
            vol_col = col
    if kw_col is None:
        kw_col = 0  # default to the first column
    return kw_col, pos_col, vol_col


def load_ranked_csv(path):
    """Ranked keywords from a CSV -> {keyword: {position, volume}}.

    One row per keyword: a keyword column plus position and volume columns
    (any of the accepted aliases). When a keyword appears more than once the
    best (lowest) position wins, so a deduplicated export and a raw one agree.
    """
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return {}
    kw_col, pos_col, vol_col = _resolve_columns(rows[0])
    return _rows_to_ranked(rows[1:], kw_col, pos_col, vol_col)


def _rows_to_ranked(data_rows, kw_col, pos_col, vol_col):
    out = {}
    for r in data_rows:
        if not r or kw_col >= len(r):
            continue
        kw = normalize_keyword(r[kw_col])
        if not kw:
            continue
        position = _to_float(r[pos_col]) if pos_col is not None and pos_col < len(r) else None
        volume = _to_float(r[vol_col]) if vol_col is not None and vol_col < len(r) else None
        _merge_ranked(out, kw, position, volume)
    return out


def load_ranked_json(path):
    """Ranked keywords from JSON -> {keyword: {position, volume}}.

    Accepts a bare list of row objects or an object wrapping one under
    `keywords` / `data` / `items`. Each row carries a keyword plus position and
    volume under any of the common field names (including the DataForSEO shape).
    """
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get("keywords") or data.get("data") or data.get("items") or []
    out = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        kw = normalize_keyword(row.get("keyword") or row.get("query") or row.get("term"))
        if not kw:
            continue
        position = _to_float(row.get("position", row.get("pos",
                             row.get("rank", row.get("rank_absolute")))))
        volume = _to_float(row.get("volume", row.get("search_volume",
                           row.get("searches", row.get("sv")))))
        _merge_ranked(out, kw, position, volume)
    return out


def _merge_ranked(store, keyword, position, volume):
    """Insert/merge a ranked keyword, keeping the best position seen."""
    existing = store.get(keyword)
    if existing is None:
        store[keyword] = {"position": position, "volume": volume}
        return
    # Keep the better (lower) position; fill volume if it was missing.
    if position is not None and (existing["position"] is None
                                 or position < existing["position"]):
        existing["position"] = position
    if existing["volume"] is None and volume is not None:
        existing["volume"] = volume


def load_ranked_file(path):
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_ranked_json(p)
    return load_ranked_csv(p)


def load_mine_from_merger():
    """Your own ranked keywords from the merger's by_query view (GSC).

    Returns {keyword: {position, volume}}. GSC supplies the average position;
    volume comes from the Ads join when present. Empty if no merged data exists.
    """
    sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-merger" / "scripts"))
    try:
        from merge import load_merged
    except ImportError:
        return {}
    try:
        merged = load_merged()
    except Exception:
        return {}
    out = {}
    for row in merged.get("by_query", []):
        kw = normalize_keyword(row.get("query"))
        if not kw:
            continue
        _merge_ranked(out, kw, _to_float(row.get("position")), _to_float(row.get("volume")))
    return out


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
        "A content gap needs every keyword each competitor ranks for. NodesHub is\n"
        "SERP-only and cannot export a domain's full ranked-keyword set, so that\n"
        "footprint comes from DataForSEO's ranked_keywords endpoint.\n\n"
        "Add credentials to your settings env, then re-run with --source dfs:\n"
        f"  File: {settings_path}\n"
        '  Add:  { "env": { "DATAFORSEO_LOGIN": "you@example.com", '
        '"DATAFORSEO_PASSWORD": "your-password" } }\n\n'
        "Or export them in the shell:\n"
        "  export DATAFORSEO_LOGIN=you@example.com\n"
        "  export DATAFORSEO_PASSWORD=your-password\n\n"
        "No key? Provide exported ranked-keyword lists with --mine PATH and one or\n"
        "more --competitor PATH, or run --demo to see the format."
    )


def _dfs_request(target, login, password, location_code, language_code, limit):
    """One ranked_keywords call -> {keyword: {position, volume}} for a domain."""
    import base64
    import urllib.request
    import urllib.error

    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    payload = json.dumps([{
        "target": target,
        "location_code": int(location_code),
        "language_code": language_code,
        "limit": int(limit),
        "order_by": ["keyword_data.keyword_info.search_volume,desc"],
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
        raise RuntimeError(
            f"DataForSEO HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"DataForSEO request failed: {exc.reason}")

    out = {}
    for task in body.get("tasks", []):
        for result in (task.get("result") or []):
            for item in (result.get("items") or []):
                kw_data = item.get("keyword_data", {}) or {}
                kw = normalize_keyword(kw_data.get("keyword"))
                if not kw:
                    continue
                kw_info = kw_data.get("keyword_info", {}) or {}
                volume = _to_float(kw_info.get("search_volume"))
                serp = item.get("ranked_serp_element", {}) or {}
                serp_el = serp.get("serp_item", {}) or {}
                position = _to_float(serp_el.get("rank_absolute", serp_el.get("rank_group")))
                _merge_ranked(out, kw, position, volume)
    return out


def fetch_ranked_dfs(domain, competitors, location_code, language_code, limit):
    """Fetch ranked keywords for the domain + every competitor from DataForSEO.

    Returns (mine, {competitor: ranked}). Raises RuntimeError with a setup
    message if credentials are missing, so the caller fails gracefully.
    """
    login, password = _load_dfs_credentials()
    if not (login and password):
        raise RuntimeError(_dfs_setup_message())
    mine = _dfs_request(domain, login, password, location_code, language_code, limit)
    competitor_ranked = {}
    for comp in competitors:
        competitor_ranked[comp] = _dfs_request(
            comp, login, password, location_code, language_code, limit)
    return mine, competitor_ranked


# --- core analysis (deterministic) -------------------------------------------

def build_universe(competitor_ranked, rank_window):
    """Keyword universe = union of every competitor's ranked keywords.

    For each keyword, record which competitors rank it (within the rank window),
    the best competitor + its position, and the keyword's volume. Only keywords
    at least one competitor ranks inside the window enter the universe.

    Returns {keyword: {volume, prevalence, best_competitor, best_position,
                       competitor_positions}}.
    """
    universe = {}
    for comp, ranked in competitor_ranked.items():
        for kw, rec in ranked.items():
            pos = rec.get("position")
            if pos is None or pos > rank_window:
                continue
            entry = universe.setdefault(kw, {
                "volume": None,
                "competitor_positions": {},
            })
            entry["competitor_positions"][comp] = pos
            vol = rec.get("volume")
            if entry["volume"] is None and vol is not None:
                entry["volume"] = vol

    for kw, entry in universe.items():
        positions = entry["competitor_positions"]
        best_comp = min(positions, key=lambda c: positions[c])
        entry["prevalence"] = len(positions)
        entry["best_competitor"] = best_comp
        entry["best_position"] = positions[best_comp]
        if entry["volume"] is None:
            entry["volume"] = 0.0
    return universe


def potential_score(volume, prevalence, best_position):
    """Deterministic priority: volume x prevalence, down-weighted by difficulty.

    Difficulty proxy = the best competitor's position. A keyword someone already
    holds at #2 is harder to take than one held at #18, so difficulty grows as the
    best competitor sits closer to the top (a smaller position number). A gap whose
    strongest competitor only reaches, say, #18 is an easier, higher-potential bet
    than one locked down at #2. Higher score = better bet.
    """
    vol = max(volume or 0.0, 0.0)
    capped = min(max(best_position or 20.0, 1.0), 20.0)
    difficulty = 1.0 + ((21.0 - capped) / 10.0)
    return round((vol * prevalence) / difficulty, 2)


def classify_gaps(mine, universe, rank_window, weak_margin):
    """Split the universe into Missing, Weak, and Shared/strong (deterministic).

    - Missing: a competitor ranks (within the window) and you do not rank at all.
    - Weak: you rank, but the best competitor beats you by >= weak_margin slots.
    - Shared/strong: you rank at or near the best competitor (not a gap).

    Returns (missing_rows, weak_rows, shared_count).
    """
    missing, weak, shared = [], [], 0

    for kw, entry in universe.items():
        my_rec = mine.get(kw)
        my_pos = my_rec.get("position") if my_rec else None
        my_ranks = my_pos is not None and my_pos <= rank_window
        best_pos = entry["best_position"]
        score = potential_score(entry["volume"], entry["prevalence"], best_pos)

        row = {
            "keyword": kw,
            "your_position": round(my_pos, 1) if my_pos is not None else None,
            "best_competitor": entry["best_competitor"],
            "best_competitor_position": round(best_pos, 1),
            "volume": int(round(entry["volume"])),
            "competitors_ranking": entry["prevalence"],
            "potential": score,
        }

        if not my_ranks:
            missing.append(row)
        elif my_pos - best_pos >= weak_margin:
            row["gap_to_best"] = round(my_pos - best_pos, 1)
            weak.append(row)
        else:
            shared += 1

    missing.sort(key=lambda r: (-r["potential"], -r["volume"], r["keyword"]))
    weak.sort(key=lambda r: (-r["potential"], -r["volume"], r["keyword"]))
    return missing, weak, shared


# --- optional live SERP verification ----------------------------------------

def verify_serp(rows, gl, hl, limit):
    """Confirm the top gap keywords against the live SERP via NodesHub.

    Costs 1 NodesHub token per keyword. Skips gracefully without an API key.
    Annotates each checked row with the best competitor's live position (if the
    competitor domain appears in the organic results).
    """
    sys.path.insert(0, str(_SKILL_DIR.resolve().parents[1] / "nod-nodeshub-api" / "scripts"))
    try:
        from client import NodeshubClient, NodeshubError
    except ImportError:
        print("  (verify-serp skipped: NodesHub client not found)")
        return
    try:
        client = NodeshubClient()
    except Exception:
        print("  (verify-serp skipped: no NodesHub API key configured)")
        return

    targets = rows[:limit]
    print(f"\nVerifying {len(targets)} top gap keyword(s) against live SERP "
          f"(cost: {len(targets)} tokens)...")
    for row in targets:
        try:
            serp = client.search(row["keyword"], gl=gl, hl=hl)
            organic = serp.get("data", {}).get("results", {}).get("organic_results", [])
            comp = row["best_competitor"]
            live_pos = None
            for r in organic:
                url = (r.get("url") or r.get("link") or "")
                if comp and comp in url:
                    live_pos = r.get("pos", r.get("global_pos"))
                    break
            row["serp_verified_competitor"] = comp
            row["serp_competitor_position"] = live_pos
            print(f"  {row['keyword']}: {comp} live position = "
                  f"{live_pos if live_pos is not None else 'not in top results'}")
        except NodeshubError as exc:
            row["serp_error"] = str(exc)
            print(f"  {row['keyword']}: SERP check failed ({exc})")


# --- output ------------------------------------------------------------------

def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _print_table(rows, weak):
    if weak:
        print("| Keyword | Your pos | Best competitor | Comp pos | Gap | Volume | #Comp | Potential |")
        print("|---------|----------|-----------------|----------|-----|--------|-------|-----------|")
        for r in rows:
            print(f"| {r['keyword']} | {r['your_position']} | {r['best_competitor']} | "
                  f"{r['best_competitor_position']} | {r.get('gap_to_best')} | "
                  f"{r['volume']:,} | {r['competitors_ranking']} | {r['potential']:,} |")
    else:
        print("| Keyword | Your pos | Best competitor | Comp pos | Volume | #Comp | Potential |")
        print("|---------|----------|-----------------|----------|--------|-------|-----------|")
        for r in rows:
            you = r["your_position"] if r["your_position"] is not None else "-"
            print(f"| {r['keyword']} | {you} | {r['best_competitor']} | "
                  f"{r['best_competitor_position']} | {r['volume']:,} | "
                  f"{r['competitors_ranking']} | {r['potential']:,} |")


def print_summary(report, top):
    meta = report["meta"]
    summary = report["summary"]
    print()
    print("## Content Gap Report")
    print(f"**Domain:** {meta['domain']} | "
          f"**Competitors:** {', '.join(meta['competitors'])} | "
          f"**Source:** {meta['source']} | **Date:** {meta['date']}")
    print()
    print(f"**Universe:** {summary['universe_size']} competitor keywords | "
          f"**Missing:** {summary['missing']} | "
          f"**Weak:** {summary['weak']} | "
          f"**Shared/strong:** {summary['shared_strong']}")
    print()

    print(f"### Missing — competitors rank, you do not (top {top})")
    if report["missing"]:
        _print_table(report["missing"][:top], weak=False)
    else:
        print("  None. You already rank for every keyword a competitor holds in the window.")
    print()

    print(f"### Weak — you rank, but a competitor beats you by the margin (top {top})")
    if report["weak"]:
        _print_table(report["weak"][:top], weak=True)
    else:
        print("  None. Where you rank, no competitor beats you by the configured margin.")
    print()
    print(f"Report saved to: {meta['output_path']}")
    print("Cost: 0 NodesHub tokens (DataForSEO billed separately; "
          "1 token/keyword only with --verify-serp).")


# --- demo fixture ------------------------------------------------------------

def _demo_data():
    """Your domain + 2 competitors with overlapping / non-overlapping keywords.

    - Both competitors rank "project management software" and "kanban board"
      strongly; you do not rank -> Missing, high prevalence.
    - Competitor A ranks "gantt chart maker" #3; you rank #14 -> Weak.
    - You already beat everyone on "free task tracker" -> Shared/strong.
    - "time tracking app" is competitor-only -> Missing.
    """
    mine = {
        "gantt chart maker": {"position": 14.0, "volume": 9900.0},
        "free task tracker": {"position": 2.0, "volume": 4400.0},
        "team collaboration tool": {"position": 8.0, "volume": 6600.0},
    }
    comp_a = {
        "project management software": {"position": 3.0, "volume": 40500.0},
        "kanban board": {"position": 5.0, "volume": 18100.0},
        "gantt chart maker": {"position": 3.0, "volume": 9900.0},
        "time tracking app": {"position": 6.0, "volume": 12100.0},
        "team collaboration tool": {"position": 7.0, "volume": 6600.0},
    }
    comp_b = {
        "project management software": {"position": 8.0, "volume": 40500.0},
        "kanban board": {"position": 2.0, "volume": 18100.0},
        "resource planning software": {"position": 4.0, "volume": 3600.0},
        "time tracking app": {"position": 11.0, "volume": 12100.0},
    }
    return "you.com", {"competitor-a.com": comp_a, "competitor-b.com": comp_b}, mine


# --- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("Content Gap")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Classic content/keyword gap: keywords competitors rank for that you don't.")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the bundled fixture (no key, no data)")
    parser.add_argument("--domain", help="Your domain (DataForSEO path)")
    parser.add_argument("--competitors", help="Comma-separated competitor domains (DataForSEO path)")
    parser.add_argument("--mine", help="CSV/JSON of your ranked keywords (file ingest)")
    parser.add_argument("--competitor", action="append", default=[],
                        help="CSV/JSON of a competitor's ranked keywords (repeatable)")
    parser.add_argument("--source", choices=["dfs", "file"], default=None,
                        help="Keyword source: dfs (DataForSEO) or file (--mine/--competitor)")
    parser.add_argument("--location", default="2840",
                        help="DataForSEO location_code (default 2840 = US)")
    parser.add_argument("--language", default="en",
                        help="DataForSEO language_code (default en)")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Max ranked keywords to pull per domain from DataForSEO (default 1000)")
    parser.add_argument("--rank-window", type=int, default=DEFAULT_RANK_WINDOW,
                        help=f"Top-N a keyword must be in to count as ranked (default {DEFAULT_RANK_WINDOW})")
    parser.add_argument("--weak-margin", type=int, default=DEFAULT_WEAK_MARGIN,
                        help=f"Slots a competitor must beat you by to flag Weak (default {DEFAULT_WEAK_MARGIN})")
    parser.add_argument("--top", type=int, default=20,
                        help="How many rows to print per table (default 20)")
    parser.add_argument("--verify-serp", action="store_true",
                        help="Confirm top gaps via NodesHub live SERP (1 token/keyword)")
    parser.add_argument("--verify-limit", type=int, default=5,
                        help="How many top gaps to verify when --verify-serp (default 5)")
    parser.add_argument("--gl", default="us", help="Country code for --verify-serp (default us)")
    parser.add_argument("--hl", default="en", help="Language code for --verify-serp (default en)")
    parser.add_argument("--raw", action="store_true",
                        help="Print the raw JSON report instead of the summary")
    args = parser.parse_args()

    # --- resolve domain + ranked keywords ---
    if args.demo:
        domain, competitor_ranked, mine = _demo_data()
        source = "demo-fixture"
    else:
        source_mode = args.source or ("file" if (args.mine or args.competitor) else "dfs")
        if source_mode == "file":
            if not args.competitor:
                print("--source file needs at least one --competitor PATH.", file=sys.stderr)
                sys.exit(1)
            competitor_ranked = {}
            for i, path in enumerate(args.competitor):
                name = Path(path).stem or f"competitor-{i + 1}"
                competitor_ranked[name] = load_ranked_file(path)
            if args.mine:
                mine = load_ranked_file(args.mine)
            else:
                mine = load_mine_from_merger()
                if not mine:
                    print("Note: no --mine file and no merged by_query data; treating "
                          "your domain as ranking for nothing (everything is Missing).",
                          file=sys.stderr)
            domain = args.domain or (Path(args.mine).stem if args.mine else "your-domain")
            source = "file"
        else:  # dfs
            if not args.domain or not args.competitors:
                print("--source dfs needs --domain and --competitors \"a.com,b.com\".",
                      file=sys.stderr)
                sys.exit(1)
            competitors = [c.strip() for c in args.competitors.split(",") if c.strip()]
            try:
                mine, competitor_ranked = fetch_ranked_dfs(
                    args.domain, competitors, args.location, args.language, args.limit)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(1)
            domain = args.domain
            source = "dataforseo"

    if not competitor_ranked or not any(competitor_ranked.values()):
        print("No competitor ranked keywords resolved. Check the source.", file=sys.stderr)
        sys.exit(1)

    # --- deterministic analysis ---
    universe = build_universe(competitor_ranked, args.rank_window)
    if not universe:
        print(f"No competitor keyword ranks within the top {args.rank_window}. "
              "Try a wider --rank-window.", file=sys.stderr)
        sys.exit(1)
    missing, weak, shared = classify_gaps(mine, universe, args.rank_window, args.weak_margin)

    output_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "date": str(date.today()),
            "domain": domain,
            "competitors": list(competitor_ranked.keys()),
            "source": source,
            "rank_window": args.rank_window,
            "weak_margin": args.weak_margin,
            "output_path": str(output_path),
            "note": ("Universe = union of competitor ranked keywords. Missing = a "
                     "competitor ranks and you do not; Weak = you rank but a "
                     "competitor beats you by the margin; Shared/strong = you hold "
                     "your own. Potential = volume x #competitors / difficulty "
                     "(best competitor position). Deterministic; no LLM."),
        },
        "summary": {
            "universe_size": len(universe),
            "missing": len(missing),
            "weak": len(weak),
            "shared_strong": shared,
        },
        "missing": missing,
        "weak": weak,
    }

    # Optional live SERP verification of the highest-potential missing gaps.
    if args.verify_serp:
        verify_serp(missing or weak, args.gl, args.hl, args.verify_limit)

    save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report, args.top)


if __name__ == "__main__":
    main()
