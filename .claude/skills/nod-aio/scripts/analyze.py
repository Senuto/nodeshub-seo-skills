#!/usr/bin/env python3
"""
AIO Visibility — answer the 2026 question every client now asks: when someone
searches my keywords, does Google show an AI Overview, who does it cite, and am I
one of them. Then say what to do about the queries you are closest to winning.

For each keyword the skill records three things: whether an AI Overview (AIO) is
present, which domains/URLs the AIO cites, and whether your --domain is among the
cited sources or at least ranks organically in the top 10. From those it derives
the AIO presence rate, your citation rate, the competitors cited most often, and
a per-keyword classification:

  Cited           AIO present and you are cited            -> defend the position
  AIO opportunity AIO present, not cited, but you rank top 10 -> closest win
  AIO gap         AIO present, not cited, not ranking      -> earn relevance first
  No AIO          no AI Overview                           -> classic SEO applies

For each "AIO opportunity" keyword it emits a fixed, rule-based structural
checklist (a brief-under-AIO template) — not generated prose, the same lines
every time — so content can be shaped for citability.

The classification is fully deterministic. The same per-keyword AIO data always
yields the same classes and the same numbers — no LLM, no model judgment. The
only network path is the optional DataForSEO SERP fetch, which is billed by
DataForSEO, not by NodesHub.

Data sources (priority order):
  1. DataForSEO   serp/google/organic/live/advanced  (--source dfs). Detects the
                  ai_overview item and reads its references/citations and the
                  organic top 10. Gated behind DATAFORSEO_LOGIN / PASSWORD read
                  from env or .claude/settings.local.json. Clear setup message if
                  absent; never hangs.
  2. CSV / JSON   --serp PATH. Pre-fetched per-keyword AIO data (keyword,
                  aio_present, cited_domains, optional organic_domains).
  3. --demo       a built-in keyword set with mixed AIO presence and citations
                  (your domain cited on some, competitors on others, plus a
                  no-AIO classic query) — runs with no key and no data file.

Keywords come from --file, --keywords, or the merger's by_query view.

NodesHub roadmap: NodesHub already carries AIO inside raw SERP data but does not
yet expose a clean "is this query AIO-eligible" flag plus its citations. Today we
read that from DataForSEO. If NodesHub surfaced a native aio_present flag and the
cited sources, this skill would become NodesHub-native and cheaper.

Usage:
    python3 analyze.py --demo
    python3 analyze.py --domain example.com --keywords "what is seo,best crm" --source dfs --location 2840
    python3 analyze.py --domain example.com --file keywords.txt --serp aio.csv
    python3 analyze.py --domain example.com --raw

Output:
    data/aio/{YYYY-MM-DD}.json  ->  { meta, summary, classes, top_cited_competitors,
                                      keywords, brief_template }
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
_OUTPUT_DIR = _REPO_ROOT / "data" / "aio"

_SETTINGS_CANDIDATES = [
    _REPO_ROOT / ".claude" / "settings.local.json",
    _REPO_ROOT / "settings.local.json",
    Path.home() / ".claude" / "settings.local.json",
    Path.home() / ".claude" / "settings.json",
]

# DataForSEO advanced SERP returns an `ai_overview` item carrying `references`.
DFS_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"

# The four mutually exclusive per-keyword classes.
CLASS_CITED = "cited"
CLASS_OPPORTUNITY = "aio_opportunity"
CLASS_GAP = "aio_gap"
CLASS_NO_AIO = "no_aio"

# Fixed brief-under-AIO checklist. Rule-based template, NOT generated prose: the
# same lines render for every AIO-opportunity keyword. Edits here change the
# template for everyone, deterministically.
BRIEF_TEMPLATE = [
    "Lead with a concise 1-2 sentence definition or direct answer near the top, "
    "before any preamble.",
    "Add a standalone direct-answer paragraph (40-60 words) that resolves the "
    "query in plain language.",
    "Break supporting detail into scannable lists or a comparison table — AI "
    "Overviews lift structured, extractable passages.",
    "Add an FAQ block with the literal question phrasings people search, each "
    "answered in 1-2 sentences.",
    "Make each claim self-contained and citable (one fact per sentence, no "
    "pronoun chains that need earlier context).",
]


# --- parsing helpers ---------------------------------------------------------

def normalize_keyword(raw):
    """Lowercase + collapse whitespace for keyword joins."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", str(raw).strip().lower())


def _to_bool(value, default=False):
    """Parse common truthy/falsy encodings into a bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "y", "t", "present"):
        return True
    if text in ("0", "false", "no", "n", "f", "absent", ""):
        return False
    return default


def normalize_domain(raw):
    """Reduce a URL or host to a bare registrable host (drop scheme/path/www)."""
    if not raw:
        return ""
    text = str(raw).strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.split("/", 1)[0]
    text = text.split("?", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text.strip()


def _split_list(value):
    """Split a delimited string (or pass through a list) into clean items."""
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[;,|]", str(value))
    return [s.strip() for s in items if s and str(s).strip()]


def _domain_matches(target, candidate):
    """True when candidate host equals target or is a subdomain of it."""
    if not target or not candidate:
        return False
    return candidate == target or candidate.endswith("." + target)


# --- per-keyword AIO record --------------------------------------------------

def make_record(keyword, aio_present, cited_domains, organic_domains):
    """Build a normalized per-keyword AIO record (no classification yet)."""
    cited = []
    seen = set()
    for d in cited_domains:
        nd = normalize_domain(d)
        if nd and nd not in seen:
            seen.add(nd)
            cited.append(nd)
    organic = []
    seen_o = set()
    for d in organic_domains:
        nd = normalize_domain(d)
        if nd and nd not in seen_o:
            seen_o.add(nd)
            organic.append(nd)
    return {
        "keyword": keyword,
        "aio_present": bool(aio_present),
        "cited_domains": cited,
        "organic_domains": organic,
    }


# --- CSV / JSON ingest -------------------------------------------------------

def _normalize_header(label):
    return re.sub(r"[._\-]+", " ", str(label).strip().lower()).strip()


def _find_col(header, aliases):
    for col, label in enumerate(header):
        if _normalize_header(label) in aliases:
            return col
    return None


def load_serp_csv(path):
    """Per-keyword AIO data from CSV -> {keyword: record}.

    Columns (any alias): keyword; aio_present (bool); cited_domains
    (delimited list); organic_domains (delimited list, optional).
    """
    rows = list(csv.reader(Path(path).open(newline="", encoding="utf-8")))
    if len(rows) < 2:
        return {}
    header = rows[0]
    kw_col = _find_col(header, {"keyword", "query", "term", "phrase", "kw"})
    if kw_col is None:
        kw_col = 0
    aio_col = _find_col(header, {"aio present", "aio", "aio present bool",
                                 "ai overview", "has aio", "aio eligible"})
    cited_col = _find_col(header, {"cited domains", "cited", "citations",
                                   "aio sources", "references", "sources"})
    organic_col = _find_col(header, {"organic domains", "organic", "ranking domains",
                                     "top 10", "organic top 10"})

    out = {}
    for r in rows[1:]:
        if not r or kw_col >= len(r):
            continue
        kw = r[kw_col].strip()
        if not kw:
            continue
        aio = _to_bool(r[aio_col]) if (aio_col is not None and aio_col < len(r)) else False
        cited = _split_list(r[cited_col]) if (cited_col is not None and cited_col < len(r)) else []
        organic = _split_list(r[organic_col]) if (organic_col is not None and organic_col < len(r)) else []
        norm = normalize_keyword(kw)
        out[norm] = make_record(norm, aio, cited, organic)
    return out


def load_serp_json(path):
    """Per-keyword AIO data from JSON.

    Accepts a list of objects or a {keyword: object} dict. Each object may carry
    aio_present, cited_domains, organic_domains (lists or delimited strings).
    """
    data = json.loads(Path(path).read_text())
    out = {}

    def ingest(kw, obj):
        if not kw:
            return
        if not isinstance(obj, dict):
            obj = {}
        aio = _to_bool(obj.get("aio_present", obj.get("aio", obj.get("ai_overview"))))
        cited = _split_list(obj.get("cited_domains")
                            or obj.get("cited")
                            or obj.get("citations")
                            or obj.get("references")
                            or obj.get("sources"))
        organic = _split_list(obj.get("organic_domains")
                              or obj.get("organic")
                              or obj.get("ranking_domains")
                              or obj.get("organic_top_10"))
        norm = normalize_keyword(kw)
        out[norm] = make_record(norm, aio, cited, organic)

    if isinstance(data, dict):
        for kw, obj in data.items():
            ingest(kw, obj)
    else:
        for row in data:
            ingest(row.get("keyword") or row.get("query"), row)
    return out


def load_from_hub(keywords):
    """STUB — future native pull from a NodesHub AIO-eligibility feed.

    Intentionally NOT implemented. NodesHub already has AIO inside raw SERP data;
    when it exposes a clean aio_present flag plus citations, this seam would call
    it and return {keyword: record} in the same shape as load_serp_csv. No
    networking is performed here.
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
        "No key? Use --serp PATH for a CSV/JSON of per-keyword AIO data, "
        "or --demo to see the format."
    )


def _extract_aio_references(item):
    """Pull cited domains from a DataForSEO ai_overview item.

    The ai_overview item carries `references` (and/or per-item `links`) holding
    the cited source URLs/domains. We harvest any url/domain field we can find.
    """
    domains = []

    def harvest(refs):
        for ref in refs or []:
            if not isinstance(ref, dict):
                continue
            url = ref.get("url") or ref.get("link") or ""
            host = ref.get("domain") or normalize_domain(url)
            if host:
                domains.append(host)

    harvest(item.get("references"))
    # Some AIO payloads nest references inside expandable items.
    for sub in (item.get("items") or []):
        if isinstance(sub, dict):
            harvest(sub.get("references"))
    return domains


def fetch_serp_dfs(keywords, location_code, language_code):
    """Fetch per-keyword AIO + organic top 10 from DataForSEO advanced SERP.

    Returns {keyword: record}. Raises RuntimeError with a setup message if
    credentials are missing, so the caller can fail gracefully. One request per
    keyword (DataForSEO bills these, not NodesHub).
    """
    login, password = _load_dfs_credentials()
    if not (login and password):
        raise RuntimeError(_dfs_setup_message())

    import base64
    import urllib.request
    import urllib.error

    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    out = {}

    for kw in keywords:
        payload = json.dumps([{
            "keyword": kw,
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
            raise RuntimeError(
                f"DataForSEO HTTP {exc.code}: "
                f"{exc.read().decode('utf-8', 'replace')[:300]}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DataForSEO request failed: {exc.reason}")

        aio_present = False
        cited = []
        organic = []
        for task in body.get("tasks", []):
            for result in (task.get("result") or []):
                for item in (result.get("items") or []):
                    itype = item.get("type")
                    if itype == "ai_overview":
                        aio_present = True
                        cited.extend(_extract_aio_references(item))
                    elif itype == "organic":
                        host = item.get("domain") or normalize_domain(item.get("url"))
                        if host:
                            organic.append(host)
        norm = normalize_keyword(kw)
        out[norm] = make_record(norm, aio_present, cited, organic[:10])
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

def classify(record, domain):
    """Assign one of the four AIO classes to a record, given your domain.

    Pure rule-based:
      no AIO                            -> CLASS_NO_AIO
      AIO present, you cited            -> CLASS_CITED
      AIO present, not cited, you rank  -> CLASS_OPPORTUNITY
      AIO present, not cited, no rank   -> CLASS_GAP
    """
    if not record["aio_present"]:
        return CLASS_NO_AIO, False, False
    cited = any(_domain_matches(domain, d) for d in record["cited_domains"]) if domain else False
    ranks = any(_domain_matches(domain, d) for d in record["organic_domains"]) if domain else False
    if cited:
        return CLASS_CITED, True, ranks
    if ranks:
        return CLASS_OPPORTUNITY, False, True
    return CLASS_GAP, False, False


def analyze(records, domain):
    """Classify every record and aggregate the set-level signals.

    Returns (classified_records, summary, top_cited_competitors).
    Deterministic: identical input always yields identical output.
    """
    norm_domain = normalize_domain(domain) if domain else ""
    classified = []
    for rec in records:
        cls, you_cited, you_rank = classify(rec, norm_domain)
        out = dict(rec)
        out["class"] = cls
        out["you_cited"] = you_cited
        out["you_rank_top10"] = you_rank
        classified.append(out)

    total = len(classified)
    aio_records = [r for r in classified if r["aio_present"]]
    cited_records = [r for r in aio_records if r["class"] == CLASS_CITED]

    aio_presence_rate = round(len(aio_records) / total, 3) if total else 0.0
    citation_rate = round(len(cited_records) / len(aio_records), 3) if aio_records else 0.0

    # Competitor citation frequency across AIO queries, excluding your own domain.
    freq = {}
    for r in aio_records:
        for d in r["cited_domains"]:
            if norm_domain and _domain_matches(norm_domain, d):
                continue
            freq[d] = freq.get(d, 0) + 1
    top_cited = [{"domain": d, "aio_citations": c}
                 for d, c in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))]

    summary = {
        "domain": norm_domain or None,
        "keyword_count": total,
        "aio_present_count": len(aio_records),
        "aio_presence_rate": aio_presence_rate,
        "you_cited_count": len(cited_records),
        "citation_rate_of_aio": citation_rate,
        "class_counts": {
            CLASS_CITED: sum(1 for r in classified if r["class"] == CLASS_CITED),
            CLASS_OPPORTUNITY: sum(1 for r in classified if r["class"] == CLASS_OPPORTUNITY),
            CLASS_GAP: sum(1 for r in classified if r["class"] == CLASS_GAP),
            CLASS_NO_AIO: sum(1 for r in classified if r["class"] == CLASS_NO_AIO),
        },
    }
    return classified, summary, top_cited


def split_classes(classified):
    """Group classified records into the four named lists, keyword-sorted."""
    buckets = {CLASS_CITED: [], CLASS_OPPORTUNITY: [], CLASS_GAP: [], CLASS_NO_AIO: []}
    for r in classified:
        buckets[r["class"]].append(r)
    for key in buckets:
        buckets[key].sort(key=lambda r: r["keyword"])
    return buckets


# --- output ------------------------------------------------------------------

def save_report(report):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / f"{date.today()}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return out_path


def _pct(rate):
    return f"{round(rate * 100):.0f}%"


def print_summary(report):
    s = report["summary"]
    classes = report["classes"]
    print()
    print("## AIO Visibility Report")
    print(f"**Domain:** {s['domain'] or '(none given)'} | "
          f"**Keywords:** {s['keyword_count']} | "
          f"**Source:** {report['meta']['source']} | "
          f"**Date:** {report['meta']['date']}")
    print()
    print("### Summary")
    print(f"- AI Overview present on **{s['aio_present_count']}/{s['keyword_count']}** "
          f"queries ({_pct(s['aio_presence_rate'])} of the set).")
    if s["aio_present_count"]:
        print(f"- You are cited on **{s['you_cited_count']}/{s['aio_present_count']}** "
              f"AIO queries ({_pct(s['citation_rate_of_aio'])} citation rate).")
    else:
        print("- No AI Overviews in this set — classic SEO applies throughout.")
    print()

    labels = [
        (CLASS_CITED, "Cited (defend)"),
        (CLASS_OPPORTUNITY, "AIO opportunity (closest win)"),
        (CLASS_GAP, "AIO gap (earn relevance first)"),
        (CLASS_NO_AIO, "No AIO (classic SEO)"),
    ]
    for key, label in labels:
        rows = classes[key]
        print(f"### {label} — {len(rows)}")
        if not rows:
            print("  (none)")
            print()
            continue
        for r in rows:
            extra = ""
            if key == CLASS_CITED:
                extra = ""  # already winning
            elif key == CLASS_OPPORTUNITY:
                extra = "  (ranks top 10, not cited)"
            cited_preview = ", ".join(r["cited_domains"][:3])
            if cited_preview:
                extra += f"  cited: {cited_preview}"
            print(f"  - {r['keyword']}{extra}")
        print()

    top = report["top_cited_competitors"]
    print("### Top cited competitor domains (across AIO queries)")
    if not top:
        print("  (none — no competitor citations recorded)")
    else:
        print("  | Domain | AIO citations |")
        print("  |--------|---------------|")
        for row in top[:10]:
            print(f"  | {row['domain']} | {row['aio_citations']} |")
    print()

    opp = classes[CLASS_OPPORTUNITY]
    if opp:
        print("### Brief-under-AIO checklist (apply to each AIO-opportunity keyword)")
        print("  You already rank top 10 — structure the page so the AI Overview "
              "can extract and cite it:")
        for line in report["brief_template"]:
            print(f"  -> {line}")
        print()

    print(f"Report saved to: {report['meta']['output_path']}")
    print("Cost: 0 NodesHub tokens (DataForSEO billed separately if --source dfs).")


# --- demo fixture ------------------------------------------------------------

def _demo_records(domain):
    """Mixed AIO presence + citations against your --domain.

    With --domain example.com:
      - "what is technical seo": AIO, you cited        -> Cited
      - "best seo tools 2026":   AIO, not cited, rank  -> AIO opportunity
      - "how to do keyword research": AIO, not cited, rank -> AIO opportunity
      - "enterprise seo platform": AIO, not cited, no rank -> AIO gap
      - "seo agency near me":     no AIO               -> No AIO (classic)
    """
    you = normalize_domain(domain) or "example.com"
    rows = [
        make_record(
            "what is technical seo", True,
            [you, "moz.com", "ahrefs.com"],
            [you, "moz.com", "searchengineland.com"]),
        make_record(
            "best seo tools 2026", True,
            ["ahrefs.com", "semrush.com", "moz.com"],
            ["semrush.com", you, "ahrefs.com"]),
        make_record(
            "how to do keyword research", True,
            ["backlinko.com", "ahrefs.com"],
            ["backlinko.com", you, "hubspot.com"]),
        make_record(
            "enterprise seo platform", True,
            ["conductor.com", "brightedge.com", "semrush.com"],
            ["conductor.com", "brightedge.com", "g2.com"]),
        make_record(
            "seo agency near me", False,
            [],
            ["yelp.com", "clutch.co", you]),
    ]
    return {r["keyword"]: r for r in rows}


# --- main --------------------------------------------------------------------

def main():
    # Banner first (CLAUDE.md rule).
    try:
        sys.path.insert(0, str(_REPO_ROOT / ".claude" / "skills" / "nod-nodeshub-api" / "scripts"))
        from banner import print_banner
        print_banner("AIO Visibility")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="AI Overview (GEO/AEO) visibility + brief-under-AIO guidance.")
    parser.add_argument("--demo", action="store_true",
                        help="Run on the bundled mixed-AIO fixture (no key, no data)")
    parser.add_argument("--domain", help="Your domain — are you cited / ranking?")
    parser.add_argument("--keywords", help="Comma-separated keywords")
    parser.add_argument("--file", help="Path to a newline-delimited keyword file")
    parser.add_argument("--serp", help="CSV/JSON of per-keyword AIO data")
    parser.add_argument("--source", choices=["dfs", "file", "hub"], default=None,
                        help="AIO data source: dfs (DataForSEO), file (--serp), hub (stub)")
    parser.add_argument("--location", default="2840",
                        help="DataForSEO location_code (default 2840 = US)")
    parser.add_argument("--language", default="en",
                        help="DataForSEO language_code (default en)")
    parser.add_argument("--raw", action="store_true",
                        help="Print the raw JSON report instead of the summary")
    args = parser.parse_args()

    # --- resolve keywords + AIO data ---
    if args.demo:
        records_by_kw = _demo_records(args.domain)
        source = "demo-fixture"
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

        src = args.source or ("file" if args.serp else "dfs")
        if src == "file":
            if not args.serp:
                print("--source file needs --serp PATH.", file=sys.stderr)
                sys.exit(1)
            path = Path(args.serp)
            loaded = (load_serp_json(path) if path.suffix.lower() == ".json"
                      else load_serp_csv(path))
            source = f"file:{path.name}"
        elif src == "hub":
            loaded = load_from_hub(norm_keywords)
            source = "hub-stub"
            if not loaded:
                print("Hub source is a stub and returns no data. Use --source dfs "
                      "or --serp PATH.", file=sys.stderr)
                sys.exit(1)
        else:  # dfs
            try:
                loaded = fetch_serp_dfs(keywords, args.location, args.language)
            except RuntimeError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(1)
            source = "dataforseo"

        # Keep keyword order; warn about any without AIO data.
        records_by_kw = {}
        missing = []
        for k in norm_keywords:
            if k in loaded:
                records_by_kw[k] = loaded[k]
            else:
                missing.append(k)
        if missing:
            print(f"Note: no AIO data for {len(missing)} keyword(s): "
                  f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}",
                  file=sys.stderr)
        if not records_by_kw:
            print("No AIO data resolved for any keyword. Check the source.",
                  file=sys.stderr)
            sys.exit(1)

    records = list(records_by_kw.values())

    # --- deterministic analysis ---
    classified, summary, top_cited = analyze(records, args.domain)
    classes = split_classes(classified)

    output_path = _OUTPUT_DIR / f"{date.today()}.json"
    report = {
        "meta": {
            "date": str(date.today()),
            "source": source,
            "domain": summary["domain"],
            "output_path": str(output_path),
            "note": ("Per-keyword AIO presence + citations classified into four "
                     "classes against your domain. Deterministic; no LLM. The "
                     "brief template is a fixed rule-based checklist."),
        },
        "summary": summary,
        "classes": classes,
        "top_cited_competitors": top_cited,
        "brief_template": BRIEF_TEMPLATE,
        "keywords": classified,
    }

    save_report(report)

    if args.raw:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)


if __name__ == "__main__":
    main()
