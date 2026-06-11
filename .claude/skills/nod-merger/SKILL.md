---
name: nod-merger
description: |
  Merge Google Search Console + Google Analytics 4 + Google Ads into one clean
  funnel dataset keyed by URL (and by query where available). Deterministic, no
  LLM. This is the foundation layer downstream skills (auto-detector,
  paid-vs-organic, intent-ROI) import. Use when the user says "merge gsc ga4",
  "combine search console and analytics", "unified seo data", "funnel data",
  "data merge", or "join gsc ga4 ads". No NodesHub tokens for the core merge.
compatibility: "Requires Python 3.9+. Reads GSC/GA4/Ads exports. NodesHub key only for --enrich-serp."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Data Merger

Unify GSC, GA4, and Google Ads into a single funnel dataset. The output is the
contract every downstream skill builds on, so the schema below is stable and
documented.

## Quick Start

```bash
# Run on bundled sample fixtures — works now, no real data needed
python3 .claude/skills/nod-merger/scripts/merge.py --demo

# Merge the newest fetched files automatically
python3 .claude/skills/nod-merger/scripts/merge.py

# Explicit paths, plus a by_url CSV
python3 .claude/skills/nod-merger/scripts/merge.py \
  --gsc knowledge/metrics/seo/gsc-2026-06-11.json \
  --ga4 knowledge/metrics/analytics/ga4-2026-06-11.json \
  --ads knowledge/metrics/ads/ads-2026-06-11.json \
  --csv-out
```

**Cost:** 0 NodesHub tokens for the core merge. `--enrich-serp` calls the
NodesHub intent classifier (2 tokens per query) and is strictly optional.

## Setup

The merge is API-free. It reads exports produced by the project fetchers. Each
source is optional — the merge runs on whatever is present and records what is
missing in `meta.sources_missing`.

1. **GSC** — `/connect-gsc`, then `node scripts/fetch-gsc.js`. Writes
   `knowledge/metrics/seo/gsc-*.json` (used: `topPages`, `topQueries`).
2. **GA4** — `/connect-ga4`, then `node scripts/fetch-ga4.js`. Writes
   `knowledge/metrics/analytics/ga4-*.json` (used: `topPages`).
3. **Google Ads** — two paths via `scripts/fetch-google-ads.js`:
   - **API path** (`--keywords "a,b,c"`): needs an approved Google Ads developer
     token. Approval can take days, so it fails gracefully with setup steps when
     credentials are absent.
   - **CSV fallback** (`--csv export.csv`): works today, no approval. Export a
     keyword list from Keyword Planner, DataForSEO, or Senuto with columns like
     `keyword`, `avg_monthly_searches` (or `volume`), `cpc`, `competition`. The
     ingest normalizes header aliases and emits the same shape as the API path.
     `merge.py` can also read a raw Ads CSV directly via `--ads export.csv`.

## Workflow

1. **Collect exports** — run the fetchers above (or use `--demo`).
2. **Normalize URLs and keywords** — protocol/host/query/trailing-slash stripped
   for URLs; whitespace-collapsed lowercase for keywords.
3. **Build `by_url`** — GSC `topPages` (the SEO spine) joined with GA4
   `topPages` on the normalized URL. GA4-only pages are kept and flagged.
4. **Build `by_query`** — GSC `topQueries` enriched with Ads volume/CPC/competition.
5. **Write** `data/merged/{YYYY-MM-DD}.json` (and optional CSV via `--csv-out`).
6. **Report** row counts and cross-source coverage.

## Output Schema

This is the downstream contract. Numbers are parsed to numeric types (percent
strings like `"4.29%"` become `4.29`). Missing values are `null`.

`data/merged/{YYYY-MM-DD}.json`:

```jsonc
{
  "meta": {
    "generatedAt": "2026-06-11",
    "sources_present": ["gsc", "ga4", "ads"],
    "sources_missing": [],
    "source_files": { "gsc": "...", "ga4": "...", "ads": "..." },
    "coverage": {
      "by_url_rows": 6,
      "by_url_gsc_ga4_matched": 5,
      "by_query_rows": 5,
      "by_query_ads_matched": 5
    },
    "serp_enriched": false,
    "note": "GA4 conversions are per-URL only; GA4 has no query dimension."
  },
  "by_url": [ /* rows below */ ],
  "by_query": [ /* rows below */ ]
}
```

### `by_url` row fields

| Field | Source | Meaning |
|-------|--------|---------|
| `url` | join key | Normalized path (leading slash, lowercased, no query/host) |
| `in_gsc` | flag | URL present in GSC topPages |
| `in_ga4` | flag | URL present in GA4 topPages |
| `impressions` | GSC | Search impressions (funnel head) |
| `clicks` | GSC | Organic clicks |
| `ctr` | GSC | Click-through rate as a number (e.g. `4.29`) |
| `position` | GSC | Average position |
| `sessions` | GA4 | Sessions; falls back to GA4 `users` when per-page sessions are absent |
| `pageviews` | GA4 | Page views |
| `users` | GA4 | Users |
| `conversions` | GA4 | Conversions (only if the GA4 export carries them; else `null`) |
| `engagement_rate` | GA4 | Engagement rate (only if exported) |
| `avg_session_duration` | GA4 | Average session duration string |

Funnel reads left to right: `impressions -> clicks -> sessions -> conversions`.

### `by_query` row fields

| Field | Source | Meaning |
|-------|--------|---------|
| `query` | GSC | Search query |
| `in_gsc` | flag | Always true (GSC drives the rows) |
| `in_ads` | flag | Query matched an Ads keyword |
| `clicks` | GSC | Clicks for the query |
| `impressions` | GSC | Impressions for the query |
| `ctr` | GSC | CTR as a number |
| `position` | GSC | Average position |
| `volume` | Ads | Avg monthly searches |
| `cpc` | Ads | Cost per click |
| `competition` | Ads | Competition normalized to 0-1 |
| `intent` | NodesHub | Only present with `--enrich-serp` |

## GA4 per-URL limitation (read this)

GA4 has **no query dimension**. Sessions, conversions, and engagement exist only
per landing page, so they live in `by_url` and **cannot** be attributed per
query. `by_query` therefore carries search demand and paid signal (GSC + Ads)
but no GA4 outcomes. Downstream skills that want query-level ROI must approximate
it through the URL that ranks for a query, not from GA4 directly.

## Importable helper

Downstream skills load the latest merged dataset without reparsing:

```python
import sys
sys.path.insert(0, ".claude/skills/nod-merger/scripts")
from merge import load_merged

data = load_merged()          # newest file in data/merged/
rows = data["by_url"]         # or data["by_query"]
```

## Parameters

| Param | Description |
|-------|-------------|
| `--gsc PATH` | Explicit GSC JSON (else newest in `knowledge/metrics/seo/`) |
| `--ga4 PATH` | Explicit GA4 JSON (else newest in `knowledge/metrics/analytics/`) |
| `--ads PATH` | Explicit Ads JSON or CSV (else newest in `knowledge/metrics/ads/`) |
| `--demo` | Run on bundled sample fixtures |
| `--csv-out` | Also write a `by_url` CSV |
| `--enrich-serp` | Attach live intent per query (costs NodesHub tokens) |
| `--gl` / `--hl` | Country/language for `--enrich-serp` |

## Cost

- Core merge: **0 NodesHub tokens** (deterministic, offline).
- `--enrich-serp`: 2 tokens per query (NodesHub intent classifier), optional.

## Related Skills

- **nod-rank-tracker** — position tracking that can feed query lists.
- **nod-serp-analysis** — deep SERP/intent for a single keyword.
- Downstream (planned): auto-detector, paid-vs-organic, intent-ROI — all consume
  this merged dataset via `load_merged()`.
