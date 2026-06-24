---
name: nod-demand-trajectory
description: |
  Year-over-year demand trajectory for a keyword set: decide whether each
  keyword/topic is Rising, Stable, or Declining so you know where to invest and
  where to exit. For every keyword it reads a dated monthly volume time series
  (ideally 24 months) and computes two independent signals — YoY growth (last 12
  months vs the prior 12, naturally deseasonalized by comparing full years) and a
  least-squares trend slope (percent per month, fit on a 12-month moving average
  so seasonality does not masquerade as a trend, so it still works at ~12 months).
  Classifies each topic as Rising, Declining, Stable, Emerging (short history,
  steep up) or Fading (short history, steep down), then rolls up a portfolio view
  (how much demand is growing vs fading) and concrete invest/exit
  recommendations. Detection is pure rules, so the same series always yield the
  same labels. Use when user says "demand trend," "is this keyword growing,"
  "rising topics," "declining keywords," "yoy demand," "invest or exit," or
  "trend trajectory." Series come from DataForSEO, a CSV/JSON file, or the
  merger's keyword set. No NodesHub tokens.
compatibility: "Requires Python 3.9+. Series via DataForSEO (DATAFORSEO_LOGIN/PASSWORD), a CSV/JSON file, or merged by_query. --demo runs with no key and no data."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Demand Trajectory

Turn a keyword set into a clear across-year verdict for every topic: is demand
**rising, stable, or declining**. Each keyword carries a dated monthly volume
series; the skill measures the year-over-year direction with two independent
signals and labels each topic so the client knows where to double down and where
to phase out. The analysis is deterministic — no model judgment in the math, so
the same series always produce the same labels.

This complements **/nod-seasonality**: seasonality is the within-year "when does
demand peak"; trajectory is the across-year "is the topic growing at all". A
keyword can be sharply seasonal and still be dying year over year.

## Quick Start

```bash
# Try it now on the bundled fixture (rising + declining + stable + spiky-but-flat)
python3 .claude/skills/nod-demand-trajectory/scripts/analyze.py --demo

# From DataForSEO (needs credentials), US English — returns up to ~24 months
python3 .claude/skills/nod-demand-trajectory/scripts/analyze.py \
  --keywords "ai agents,fax machine,project management software" --source dfs --location 2840

# From a CSV/JSON of dated monthly volumes you already have
python3 .claude/skills/nod-demand-trajectory/scripts/analyze.py --file keywords.txt --series series.csv

# Use the client's merged keyword set, stricter rising bar
python3 .claude/skills/nod-demand-trajectory/scripts/analyze.py --rising-threshold 25
```

## Setup

The keyword set comes from `--keywords`, `--file`, or the **/nod-merger**
`by_query` view (the client's own queries) when nothing else is given. Each
keyword needs a dated monthly volume series (ideally 24 months for a clean YoY,
12 is enough for a slope read). Series come from one of three sources, in
priority order:

1. **DataForSEO** (`--source dfs`) — calls
   `keywords_data/google_ads/search_volume`, which returns up to ~24 months of
   `monthly_searches` per keyword. Credentials are read from `DATAFORSEO_LOGIN` /
   `DATAFORSEO_PASSWORD` in the shell env or in `.claude/settings.local.json`:

   ```json
   { "env": { "DATAFORSEO_LOGIN": "you@example.com", "DATAFORSEO_PASSWORD": "your-password" } }
   ```

   If credentials are absent the script prints a clear setup message and exits —
   it never hangs or crashes. `--location` (default `2840` = US) and `--language`
   (default `en`) target the market.

2. **CSV / JSON file** (`--series PATH`) — per-keyword dated monthly volumes. CSV
   is long format: a `keyword` column, a `date` column (`2025-03`, `03-2025`,
   `Mar 2025` all parse), and a `volume` column (`volume` / `searches` /
   `search_volume` / `value`). The series is sorted chronologically. JSON accepts
   `{ "keyword": [12 numbers] }`, dated points
   `{ "keyword": [{"date": "2025-03", "volume": n}] }`, a list of
   `{ "keyword", "series": [...] }`, or the raw DataForSEO `monthly_searches`
   shape.

3. **Hub feed** (`--source hub`) — a clearly-marked stub (`load_from_hub`) for a
   future pull from the user's data.kubadzikowski.com feed. No networking is
   implemented; it returns no data today.

Always available: **`--demo`** runs a built-in fixture (a rising topic, a
declining topic, a stable one, and a spiky-but-flat one) with no key and no data
file.

## Workflow

1. **Collect keywords** — from `--keywords`, `--file`, or the merger's `by_query`.
2. **Fetch the series** — DataForSEO (up to ~24 months), `--series` file, or the
   demo fixture.
3. **Compute YoY growth** — when 24 months exist, last 12 months of volume vs the
   prior 12. Comparing two full years cancels the within-year seasonal pattern,
   so YoY is naturally deseasonalized.
4. **Compute the trend slope** — a least-squares line over the series, normalized
   as percent of the series mean per month. To stop a seasonal swing from looking
   like a trend, the slope is fit on a 12-month centered moving average when the
   series is long enough; otherwise on the raw series. This keeps the read
   meaningful at ~12 months where YoY is impossible.
5. **Classify each topic** — Rising / Declining / Stable from YoY, plus Emerging /
   Fading for short histories with a steep slope (see thresholds below).
6. **Roll up the portfolio** — how many keywords and how much latest-12m volume
   sit in each bucket, the rising-vs-declining volume share, and a one-line
   verdict on the whole set.
7. **Recommend invest vs exit** — "double down on rising X" (biggest first),
   "phase out declining Y" (nearest-to-gone first).
8. **Save and print** — a per-keyword table, the portfolio summary, and the
   recommendation list.

### How the two signals work together

- **YoY growth** is the headline when 24 months exist — it is the number a client
  intuitively trusts and it is deseasonalized by construction.
- **Trend slope** is the robust fallback at ~12 months and a tie-breaker at 24:
  a Stable YoY with a steep slope is nudged toward Emerging or Fading, surfacing
  an inflection the annual comparison alone would miss.
- The **spiky-but-flat** case is the trap both signals are built to survive: huge
  seasonal swings, zero across-year drift. The full-year YoY and the
  moving-average slope both correctly call it Stable.

## Classification thresholds

All thresholds are named constants in `analyze.py` and the YoY bounds are
overridable from the CLI.

| Label | Rule |
|-------|------|
| **Rising** | 24m history and YoY > **+15%** (`--rising-threshold`) |
| **Declining** | 24m history and YoY < **-15%** (`--declining-threshold`) |
| **Stable** | 24m history and YoY between the two bounds, slope not steep |
| **Emerging** | Short history (< 24m, no YoY) or Stable YoY, slope >= **+1.5%/month** |
| **Fading** | Short history (< 24m, no YoY) or Stable YoY, slope <= **-1.5%/month** |

Rising/Emerging count as growth; Declining/Fading count as decline in the
portfolio share.

## Output Format

```markdown
## Demand Trajectory Report
**Keywords:** 4 | **Source:** demo-fixture | **Date:** 2026-06-11

### Per-keyword trajectory
| Keyword | Latest 12m vol | YoY | Slope %/mo | Trajectory |
|---------|----------------|-----|------------|------------|
| ai agents | 4,140 | +85.7% | +2.91 | Rising |
| garden furniture | 19,355 | +0.1% | +0.00 | Stable |
| fax machine | 5,520 | -44.7% | -2.55 | Declining |

### Portfolio summary
**Rising volume share:** 13.2% | **Declining volume share:** 17.6%
**Verdict:** Mixed, tilting down — more demand is fading than growing...

### Recommendations (invest vs exit)
  - Double down on "ai agents" (rising, YoY +85.7%)...
  - Phase out "fax machine" (declining, YoY -44.7%)...
```

The same data is saved as JSON to `data/demand-trajectory/{YYYY-MM-DD}.json` with
per-keyword rows (YoY, slope, latest-12m volume, classification), the portfolio
summary, and the recommendations.

## Cost

- **0 NodesHub tokens.** The analysis is local and deterministic.
- **DataForSEO is billed separately** when `--source dfs` is used (one
  `search_volume` request per run). The CSV/JSON and `--demo` paths cost nothing.

## Parameters

| Param | Description |
|-------|-------------|
| `--demo` | Run on the bundled rising/declining/stable/spiky-flat fixture |
| `--keywords` | Comma-separated keywords |
| `--file` | Newline-delimited keyword file |
| `--series` | CSV/JSON of per-keyword dated monthly volumes (`--source file`) |
| `--source` | `dfs` (DataForSEO), `file` (`--series`), or `hub` (stub). Defaults to `file` if `--series` is set, else `dfs` |
| `--location` | DataForSEO location_code (default `2840` = US) |
| `--language` | DataForSEO language_code (default `en`) |
| `--rising-threshold` | YoY % above which a topic is Rising (default 15) |
| `--declining-threshold` | YoY % below which a topic is Declining (default -15) |
| `--raw` | Print the raw JSON report instead of the summary |

## Related Skills

- **nod-seasonality** — the within-year companion: when demand peaks, not whether
  the topic is growing across years.
- **nod-merger** — provides the `by_query` keyword set this skill reads by default.
- **nod-keyword-research** — expand seeds into the keyword set you feed in here.
- **nod-content-brief** — turn a rising topic into a brief worth investing in.
