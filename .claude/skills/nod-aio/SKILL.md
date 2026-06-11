---
name: nod-aio
description: |
  AI Overview (GEO/AEO) visibility for a keyword set, plus a brief-under-AIO
  recommendation. For each keyword it records whether Google shows an AI Overview,
  which domains the AIO cites, and whether your domain is cited or at least ranks
  organically in the top 10. From that it reports the AIO presence rate, your
  citation rate, the competitors cited most often, and a deterministic per-keyword
  classification: Cited (defend), AIO opportunity (rank but not cited — closest
  win), AIO gap (neither), and No AIO (classic SEO). For AIO-opportunity keywords
  it emits a fixed structural checklist to make the page citable. Use when user
  says "ai overview," "aio visibility," "am I cited in ai overview," "geo," "aeo,"
  "ai search visibility," or "brief for ai overview." AIO data comes from
  DataForSEO, a CSV/JSON file, or the merger's keyword set. No NodesHub tokens.
compatibility: "Requires Python 3.9+. AIO data via DataForSEO (DATAFORSEO_LOGIN/PASSWORD), a CSV/JSON file, or merged by_query. --demo runs with no key and no data."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# AIO Visibility

Answer the question every client asks in 2026: when someone searches my keywords,
does Google show an AI Overview, who does it cite, and am I one of them. For each
keyword the skill records AIO presence, the cited source domains, and whether your
domain is cited or ranks organically in the top 10. From those signals it derives
the AIO presence rate across the set, your citation rate, the competitors cited
most often, and a per-keyword class. The classification is deterministic — no
model judgment in the logic, so the same AIO data always produces the same
classes and the same numbers.

This is the GEO / AEO (Generative / Answer Engine Optimization) differentiator:
classic rank tracking tells you where the blue links sit; this tells you whether
the AI answer above them cites you at all.

## Quick Start

```bash
# Try it now on the bundled fixture (mixed AIO presence + citations)
python3 .claude/skills/nod-aio/scripts/analyze.py --demo --domain example.com

# From DataForSEO (needs credentials), US English
python3 .claude/skills/nod-aio/scripts/analyze.py \
  --domain example.com --keywords "what is technical seo,best seo tools 2026" \
  --source dfs --location 2840

# From a CSV/JSON of AIO data you already have
python3 .claude/skills/nod-aio/scripts/analyze.py \
  --domain example.com --file keywords.txt --serp aio.csv

# Use the client's merged keyword set
python3 .claude/skills/nod-aio/scripts/analyze.py --domain example.com
```

## Setup

The keyword set comes from `--keywords`, `--file`, or the **/nod-merger**
`by_query` view (the client's own queries) when nothing else is given. Per-keyword
AIO data comes from one of three sources, in priority order:

1. **DataForSEO** (`--source dfs`) — calls
   `serp/google/organic/live/advanced` per keyword, detects the `ai_overview`
   item, and reads its `references` (cited sources) plus the organic top 10.
   Credentials are read from `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` in the
   shell env or in `.claude/settings.local.json`:

   ```json
   { "env": { "DATAFORSEO_LOGIN": "you@example.com", "DATAFORSEO_PASSWORD": "your-password" } }
   ```

   If credentials are absent the script prints a clear setup message and exits —
   it never hangs or crashes. `--location` (default `2840` = US) and `--language`
   (default `en`) target the market. One request per keyword, billed by DataForSEO.

2. **CSV / JSON file** (`--serp PATH`) — pre-fetched per-keyword AIO data. CSV
   columns (any alias): `keyword`; `aio_present` (true/false/1/0); `cited_domains`
   (delimited list of domains or URLs); optional `organic_domains` (your top-10
   ranking check). JSON accepts a list of objects or a `{ keyword: object }` dict
   with `aio_present`, `cited_domains`, and `organic_domains` fields.

3. **Hub feed** (`--source hub`) — a clearly-marked stub (`load_from_hub`) for a
   future native NodesHub AIO-eligibility feed. No networking is implemented; it
   returns no data today (see the NodesHub roadmap note below).

Always available: **`--demo`** runs a built-in fixture with mixed AIO presence and
citations (your domain cited on some, competitors on others, plus a no-AIO classic
query) with no key and no data file.

## Workflow

1. **Collect keywords** — from `--keywords`, `--file`, or the merger's `by_query`.
2. **Fetch AIO data** — DataForSEO advanced SERP, a `--serp` file, or the demo
   fixture. For each keyword: AIO present?, cited domains, organic top-10 domains.
3. **Classify each keyword** — match your `--domain` against the cited sources and
   the organic top 10 to assign one of the four classes (below).
4. **Aggregate the set** — AIO presence rate, your citation rate (of AIO queries),
   and the competitor domains cited most often across AIO queries.
5. **Recommend structure** — for AIO-opportunity keywords, emit the fixed
   brief-under-AIO checklist so the page becomes citable.
6. **Save and print** — the summary, the four classified lists, the top cited
   competitor domains, and the brief checklist.

## The four classes

A keyword lands in exactly one class, decided by rules (no LLM):

- **Cited** — AIO present and your domain is among the cited sources. You are
  winning the answer; **defend** it (keep the page fresh, keep the cited passage
  intact).
- **AIO opportunity** — AIO present, you are *not* cited, but you rank organically
  in the top 10. This is the **closest win**: Google already trusts your page for
  the query, so restructuring it for extractability is the cheapest path into the
  AI Overview.
- **AIO gap** — AIO present, you are neither cited nor ranking top 10. You must
  **earn relevance first** (classic ranking work) before citability is realistic.
- **No AIO** — no AI Overview on this query. **Classic SEO** applies; the blue
  links are the whole game here.

## Brief-under-AIO template

For every AIO-opportunity keyword the skill prints the same fixed, rule-based
checklist (not generated prose — identical lines every run):

- Lead with a concise 1-2 sentence definition or direct answer near the top.
- Add a standalone direct-answer paragraph (40-60 words) that resolves the query.
- Break supporting detail into scannable lists or a comparison table.
- Add an FAQ block using the literal question phrasings people search.
- Make each claim self-contained and citable (one fact per sentence).

These mirror what AI Overviews reliably extract: concise definitions, direct
answers, structured passages, and self-contained claims.

## Output Format

```markdown
## AIO Visibility Report
**Domain:** example.com | **Keywords:** 5 | **Source:** demo-fixture

### Summary
- AI Overview present on 4/5 queries (80% of the set).
- You are cited on 1/4 AIO queries (25% citation rate).

### Cited (defend) — 1
  - what is technical seo  cited: example.com, moz.com, ahrefs.com

### AIO opportunity (closest win) — 2
  - best seo tools 2026  (ranks top 10, not cited)  cited: ahrefs.com, semrush.com
  - how to do keyword research  (ranks top 10, not cited)  cited: backlinko.com

### AIO gap (earn relevance first) — 1
  - enterprise seo platform  cited: conductor.com, brightedge.com

### No AIO (classic SEO) — 1
  - seo agency near me

### Top cited competitor domains (across AIO queries)
  | Domain | AIO citations |
  | ahrefs.com | 3 |
```

The same data is saved as JSON to `data/aio/{YYYY-MM-DD}.json` with the summary,
the four classified lists, the top cited competitors, the brief template, and the
full per-keyword records.

## Cost

- **0 NodesHub tokens.** The classification is local and deterministic.
- **DataForSEO is billed separately** when `--source dfs` is used (one advanced
  SERP request per keyword). The CSV/JSON and `--demo` paths cost nothing.

## NodesHub roadmap

NodesHub already carries AI Overview content inside its raw SERP data, but it does
not yet expose a clean, queryable signal for **"is this query AIO-eligible"** plus
the **list of cited sources**. Today this skill reads that from DataForSEO. If
NodesHub surfaced a native `aio_present` flag and the AIO citations on its SERP
response, this skill would drop the DataForSEO dependency entirely — becoming
NodesHub-native, cheaper to run, and consistent with the rest of the `nod-` suite
(1 token per keyword instead of a separate DataForSEO bill). This is the highest-
leverage addition to the NodesHub SERP API for 2026.

## Parameters

| Param | Description |
|-------|-------------|
| `--demo` | Run on the bundled mixed-AIO fixture |
| `--domain` | Your domain — checked against cited sources and top 10 |
| `--keywords` | Comma-separated keywords |
| `--file` | Newline-delimited keyword file |
| `--serp` | CSV/JSON of per-keyword AIO data (`--source file`) |
| `--source` | `dfs` (DataForSEO), `file` (`--serp`), or `hub` (stub). Defaults to `file` if `--serp` is set, else `dfs` |
| `--location` | DataForSEO location_code (default `2840` = US) |
| `--language` | DataForSEO language_code (default `en`) |
| `--raw` | Print the raw JSON report instead of the summary |

## Related Skills

- **nod-serp-analysis** — full SERP feature breakdown for a single keyword (PAA,
  AI Overview, Knowledge Panel) when you want depth on one query.
- **nod-merger** — provides the `by_query` keyword set this skill reads by default.
- **nod-content-brief** — turn an AIO-opportunity keyword into a full content brief.
- **nod-featured-snippet-hunter** — the pre-AIO sibling: win the answer box on
  queries that do not (yet) show an AI Overview.
