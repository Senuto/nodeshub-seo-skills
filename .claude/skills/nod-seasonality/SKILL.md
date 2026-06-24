---
name: nod-seasonality
description: |
  Build ONE site-level seasonality curve from your keyword set so you can see
  when demand peaks, when to publish, and how to diversify away from a single
  annual spike. Aggregates each keyword's 12 monthly search volumes (weighted by
  the keyword's annual volume) into a normalized index (mean month = 100),
  identifies peak and trough months and the peak/trough ratio, recommends a
  publishing window with lead time before each peak, and lists counter-seasonal
  keywords that fill the off-season valley. Detection is pure rules, so the same
  volumes always yield the same curve. Use when user says "seasonality," "when do
  my keywords peak," "best time to publish," "seasonal demand," "site
  seasonality," "off-season," or "demand calendar." Volumes come from DataForSEO,
  a CSV/JSON file, or the merger's keyword set. No NodesHub tokens.
compatibility: "Requires Python 3.9+. Volumes via DataForSEO (DATAFORSEO_LOGIN/PASSWORD), a CSV/JSON file, or merged by_query. --demo runs with no key and no data."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Seasonality

Turn a keyword set into a single site seasonality curve. Each keyword carries 12
monthly search volumes; the skill sums them across keywords (weighted by each
keyword's own annual volume) and normalizes to an index where the mean month =
100. From that one curve it derives the peak and trough months, how spiky the
site is, when to publish before each peak, and which topics sell in the
off-season. The analysis is deterministic — no model judgment in the math, so the
same volumes always produce the same calendar.

## Quick Start

```bash
# Try it now on the bundled fixture (summer-peaking + counter-seasonal winter set)
python3 .claude/skills/nod-seasonality/scripts/analyze.py --demo

# From DataForSEO (needs credentials), US English
python3 .claude/skills/nod-seasonality/scripts/analyze.py \
  --keywords "garden furniture,patio umbrella,snow boots" --source dfs --location 2840

# From a CSV/JSON of monthly volumes you already have
python3 .claude/skills/nod-seasonality/scripts/analyze.py --file keywords.txt --volumes volumes.csv

# Use the client's merged keyword set, with a longer publishing lead time
python3 .claude/skills/nod-seasonality/scripts/analyze.py --lead-weeks 8
```

## Setup

The keyword set comes from `--keywords`, `--file`, or the **/nod-merger**
`by_query` view (the client's own queries) when nothing else is given. Monthly
volumes come from one of three sources, in priority order:

1. **DataForSEO** (`--source dfs`) — calls
   `keywords_data/google_ads/search_volume`, which returns `monthly_searches`
   per keyword. Credentials are read from `DATAFORSEO_LOGIN` /
   `DATAFORSEO_PASSWORD` in the shell env or in `.claude/settings.local.json`:

   ```json
   { "env": { "DATAFORSEO_LOGIN": "you@example.com", "DATAFORSEO_PASSWORD": "your-password" } }
   ```

   If credentials are absent the script prints a clear setup message and exits —
   it never hangs or crashes. `--location` (default `2840` = US) and `--language`
   (default `en`) target the market.

2. **CSV / JSON file** (`--volumes PATH`) — per-keyword monthly volumes. CSV is
   wide format: a keyword column plus 12 month columns. Column names are
   normalized, so `jan` / `january` / `m1` / `month_1` / `1` all map to January.
   JSON accepts `{ "keyword": [12 numbers] }`, a list of
   `{ "keyword", "monthly": [...] }`, or the raw DataForSEO `monthly_searches`
   shape.

3. **Hub feed** (`--source hub`) — a clearly-marked stub (`load_from_hub`) for a
   future pull from the user's data.kubadzikowski.com feed. No networking is
   implemented; it returns no data today.

Always available: **`--demo`** runs a built-in fixture (a summer-peaking set plus
a counter-seasonal winter set) with no key and no data file.

## Workflow

1. **Collect keywords** — from `--keywords`, `--file`, or the merger's `by_query`.
2. **Fetch monthly volumes** — DataForSEO, `--volumes` file, or the demo fixture.
3. **Build the site curve** — sum each keyword's 12 monthly volumes (a big
   keyword moves the curve more), normalize to an index where the mean month = 100.
4. **Find peaks and troughs** — the highest and lowest months (ties included),
   plus the peak/trough ratio that says how spiky the site is.
5. **Build the publishing calendar** — for each peak, subtract `--lead-weeks`
   (default 6, converted to whole months) and recommend the month to publish so
   content matures before demand arrives: "publish in X -> pays off in Y."
6. **List diversification topics** — keywords whose own peak month sits at least
   four months away from the site peak (counter-seasonal). These fill the
   off-season valley; each is listed with its own peak month and annual volume.
7. **Save and print** — a 12-month ASCII heatmap of the site index, the
   peak/trough summary, the publishing calendar, and the diversification list.

### How the curve is built

- **Aggregation** — the site monthly total is the sum of every keyword's volume
  in that month. This is inherently weighted by annual volume: a 50k/yr head term
  contributes more absolute volume every month than a 500/yr tail term.
- **Normalization** — divide each month by the mean month and multiply by 100. An
  index of 200 means twice the average month; 50 means half.
- **Spikiness** — peak/trough ratio. >= 4.0 very spiky, >= 2.0 spiky, >= 1.4
  moderate, below that flat. A spiky site is fragile (one season carries it);
  diversification topics are the fix.

## Output Format

```markdown
## Seasonality Report
**Keywords:** 4 | **Source:** demo-fixture | **Date:** 2026-06-11

### Site seasonality curve (index, mean month = 100)
  Jun   172.1  |####################################
  Jul   193.7  |########################################  <- PEAK
  ...
  Mar    41.8  |#########  <- trough

**Peak:** Jul (index 193.7) | **Trough:** Mar (index 41.8)
**Peak/trough ratio:** 4.63 (very spiky)

### Publishing calendar (lead time before each peak)
  Publish in Jun -> pays off in Jul  (6w lead)

### Diversification — topics that fill the off-season valley
  | Keyword | Peaks in | Months from site peak | Annual volume |
  |---------|----------|-----------------------|---------------|
  | snow boots | Dec | 5 | 16,330 |
```

The same data is saved as JSON to `data/seasonality/{YYYY-MM-DD}.json` with the
raw monthly totals, the index, peaks/troughs, the publishing calendar, and the
diversification list.

## Cost

- **0 NodesHub tokens.** The analysis is local and deterministic.
- **DataForSEO is billed separately** when `--source dfs` is used (one
  `search_volume` request per run). The CSV/JSON and `--demo` paths cost nothing.

## Parameters

| Param | Description |
|-------|-------------|
| `--demo` | Run on the bundled summer + counter-seasonal winter fixture |
| `--keywords` | Comma-separated keywords |
| `--file` | Newline-delimited keyword file |
| `--volumes` | CSV/JSON of per-keyword monthly volumes (`--source file`) |
| `--source` | `dfs` (DataForSEO), `file` (`--volumes`), or `hub` (stub). Defaults to `file` if `--volumes` is set, else `dfs` |
| `--location` | DataForSEO location_code (default `2840` = US) |
| `--language` | DataForSEO language_code (default `en`) |
| `--lead-weeks` | Lead time before a peak to publish (default 6) |
| `--raw` | Print the raw JSON report instead of the summary |

## Related Skills

- **nod-merger** — provides the `by_query` keyword set this skill reads by default.
- **nod-keyword-research** — expand seeds into the keyword set you feed in here.
- **nod-content-brief** — turn a recommended publish-month topic into a brief.
- **nod-opportunity-detector** — pair seasonal timing with ranking opportunity.
