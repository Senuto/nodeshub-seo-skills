---
name: nod-content-gap
description: |
  Classic content/keyword gap analysis: the keywords your competitors rank for
  that you don't (or rank worse for). Builds the keyword universe as the union of
  every competitor's ranked keywords, then classifies each keyword as Missing
  (a competitor ranks, you don't), Weak (you rank but a competitor beats you by a
  margin), or Shared/strong (you hold your own), counting how many competitors
  rank each gap. Enriches with search volume and ranks gaps by a deterministic
  potential score (volume x prevalence, down-weighted by difficulty). Detection is
  pure rules, so the same ranked keywords always yield the same gap tables. Use
  when user says "content gap," "keyword gap," "competitor keywords I don't have,"
  "what are competitors ranking for," "gap analysis," or "missing keywords."
  Ranked keywords come from DataForSEO (a domain's full ranked footprint), from
  exported CSV/JSON lists, or the demo fixture. No NodesHub tokens unless you opt
  into live SERP verification.
compatibility: "Requires Python 3.9+. Ranked keywords via DataForSEO (DATAFORSEO_LOGIN/PASSWORD), exported CSV/JSON lists (--mine / --competitor), or merged by_query for your own ranks. --demo runs with no key and no data."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Content Gap

Find the keywords your competitors win and you don't. The skill takes a domain
plus its competitors, builds the keyword universe (every keyword the competitors
rank for), and sorts each keyword into a gap dimension: keywords you're entirely
Missing, keywords where you're Weak, and keywords you already share or lead. Each
gap carries its search volume, how many competitors hold it, and a potential
score so the list reads as a write-this-next roadmap. The math is deterministic —
no model judgment — so the same ranked keywords always produce the same tables.

First action (banner):

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Content Gap')"
```

## Quick Start

```bash
# Try it now on the bundled fixture (your domain + 2 competitors)
python3 .claude/skills/nod-content-gap/scripts/analyze.py --demo

# From DataForSEO (needs credentials), US English
python3 .claude/skills/nod-content-gap/scripts/analyze.py \
  --domain you.com --competitors "competitor-a.com,competitor-b.com" --source dfs --location 2840

# From exported ranked-keyword lists you already have
python3 .claude/skills/nod-content-gap/scripts/analyze.py \
  --mine you.csv --competitor competitor-a.csv --competitor competitor-b.csv

# Verify the top gaps against the live SERP (1 NodesHub token per keyword)
python3 .claude/skills/nod-content-gap/scripts/analyze.py --demo --verify-serp --gl us --hl en
```

## Setup

A gap analysis needs the full set of keywords each competitor ranks for. That is
where the data source matters:

- **Why DataForSEO and not NodesHub?** NodesHub is SERP-only. It can tell you who
  ranks for one keyword, but it cannot export every keyword a whole domain ranks
  for. The keyword universe for a gap analysis is exactly that footprint — per
  domain — so it has to come from a source that knows a domain's ranked keywords.
  DataForSEO's `dataforseo_labs/google/ranked_keywords` returns it. NodesHub is
  used only to verify the live SERP for a selected gap (`--verify-serp`), one
  token per keyword.

Ranked keywords come from one of three sources:

1. **DataForSEO** (`--source dfs`) — calls `ranked_keywords` once for
   `--domain` and once per `--competitors` entry, pulling each domain's ranked
   keywords with position and search volume. Credentials are read from
   `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` in the shell env or in
   `.claude/settings.local.json`:

   ```json
   { "env": { "DATAFORSEO_LOGIN": "you@example.com", "DATAFORSEO_PASSWORD": "your-password" } }
   ```

   If credentials are absent the script prints a clear setup message and exits —
   it never hangs or crashes. `--location` (default `2840` = US), `--language`
   (default `en`), and `--limit` (default 1000 keywords per domain) target the
   pull.

2. **CSV / JSON files** — `--mine PATH` for your domain and one or more
   `--competitor PATH` for each competitor. Columns are normalized, so
   `keyword`/`query`, `position`/`pos`/`rank`, and `volume`/`search_volume`/`sv`
   are all recognized. JSON accepts a bare list of row objects, an object
   wrapping one under `keywords`/`data`/`items`, or the raw DataForSEO shape. If
   `--mine` is omitted, your own ranked keywords fall back to the
   **/nod-merger** `by_query` view (your GSC queries and their average position).

3. **`--demo`** — a built-in fixture (your domain + two competitors with
   overlapping and non-overlapping ranked keywords) that runs with no key and no
   data file.

## Workflow

1. **Collect ranked keywords** — your domain and each competitor, from
   DataForSEO, exported files, or the demo fixture.
2. **Build the keyword universe** — the union of every competitor's ranked
   keywords (within `--rank-window`, default top 20), recording which
   competitors hold each keyword and the best competitor position.
3. **Classify each keyword** into a gap dimension (deterministic — see below).
4. **Enrich and score** — attach search volume and rank gaps by potential
   (`volume x #competitors / difficulty`, where difficulty grows with the best
   competitor position).
5. **(Optional) Verify live SERP** — `--verify-serp` confirms the top gaps
   against the live NodesHub SERP (1 token per keyword), graceful without a key.
6. **Save and print** — a gap summary, a ranked Missing table, and a ranked Weak
   table; the full report is saved as dated JSON.

## Gap dimensions

- **Missing** — at least one competitor ranks the keyword (inside the rank
  window) and you do not rank at all. The clearest opportunity: net-new topics.
  Counted with **prevalence** = how many competitors hold it (a keyword three
  competitors share is a stronger signal than one only a single competitor has).
- **Weak** — you rank, but the best competitor beats you by at least
  `--weak-margin` slots (default 5; e.g. you at #15 vs a competitor at #4). These
  are existing pages to strengthen, not new pages to write.
- **Shared/strong** — you rank at or near the best competitor (within the
  margin). Not a gap; reported as a count only so you can see how much of the
  universe you already cover.

**Potential score** (sorting both tables): `volume x prevalence`, divided by a
difficulty factor that grows with the best competitor's position. A high-volume
keyword that several competitors hold loosely (best position ~#15) outranks a
low-volume keyword one competitor locks at #2.

## Output Format

```markdown
## Content Gap Report
**Domain:** you.com | **Competitors:** competitor-a.com, competitor-b.com | **Source:** demo-fixture | **Date:** 2026-06-11

**Universe:** 6 competitor keywords | **Missing:** 4 | **Weak:** 1 | **Shared/strong:** 1

### Missing — competitors rank, you do not (top 20)
| Keyword | Your pos | Best competitor | Comp pos | Volume | #Comp | Potential |
|---------|----------|-----------------|----------|--------|-------|-----------|
| project management software | - | competitor-a.com | 3.0 | 40,500 | 2 | ... |

### Weak — you rank, but a competitor beats you by the margin (top 20)
| Keyword | Your pos | Best competitor | Comp pos | Gap | Volume | #Comp | Potential |
|---------|----------|-----------------|----------|-----|--------|-------|-----------|
| gantt chart maker | 14.0 | competitor-a.com | 3.0 | 11.0 | 9,900 | 1 | ... |
```

The same data is saved as JSON to `data/content-gap/{YYYY-MM-DD}.json` with the
meta, the summary counts, and the full Missing and Weak tables.

## Cost

- **0 NodesHub tokens** for the core analysis — it is local and deterministic.
- **DataForSEO is billed separately** when `--source dfs` is used: one
  `ranked_keywords` request per domain (you + each competitor). The CSV/JSON and
  `--demo` paths cost nothing.
- **`--verify-serp`** costs **1 NodesHub token per verified keyword**
  (`--verify-limit`, default 5). Skipped gracefully without a NodesHub key.

## Parameters

| Param | Description |
|-------|-------------|
| `--demo` | Run on the bundled domain + 2-competitor fixture |
| `--domain` | Your domain (DataForSEO path) |
| `--competitors` | Comma-separated competitor domains (DataForSEO path) |
| `--mine` | CSV/JSON of your ranked keywords (file path) |
| `--competitor` | CSV/JSON of a competitor's ranked keywords (repeatable) |
| `--source` | `dfs` (DataForSEO) or `file`. Defaults to `file` if `--mine`/`--competitor` set, else `dfs` |
| `--location` | DataForSEO location_code (default `2840` = US) |
| `--language` | DataForSEO language_code (default `en`) |
| `--limit` | Max ranked keywords per domain from DataForSEO (default 1000) |
| `--rank-window` | Top-N a keyword must be in to count as ranked (default 20) |
| `--weak-margin` | Slots a competitor must beat you by to flag Weak (default 5) |
| `--top` | Rows to print per table (default 20) |
| `--verify-serp` | Confirm top gaps via NodesHub live SERP (1 token/keyword) |
| `--verify-limit` | How many top gaps to verify (default 5) |
| `--gl` / `--hl` | Country / language for `--verify-serp` |
| `--raw` | Print the raw JSON report instead of the summary |

## Related Skills

- **nod-merger** — supplies your own ranked keywords (`by_query`) when `--mine`
  is omitted.
- **nod-keyword-research** — expand the gap keywords into a fuller topic set.
- **nod-content-brief** — turn a top Missing keyword into a content brief.
- **nod-competitor-tracker** — once you start closing gaps, track the competitors
  you're chasing.
