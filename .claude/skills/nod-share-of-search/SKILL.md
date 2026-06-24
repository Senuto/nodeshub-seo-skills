---
name: nod-share-of-search
description: |
  Track Share of Search (Les Binet): your brand's search demand as a percentage
  of the total brand search demand in your category, measured month over month.
  Share of Search is a leading indicator of market share and future sales — a
  board-level demand metric, not an SEO ranking tactic. The analyzer pulls
  monthly search volume for every brand (yours plus competitors'), computes each
  brand's share per month, the trend over time, and flags whether your share is
  rising or falling and which competitor has the fastest upward momentum. Logic
  is pure arithmetic, so the same volumes always yield the same report. Use when
  the user says "share of search", "brand demand", "market share indicator",
  "brand vs competitors search", or "category demand share". Volume comes from
  DataForSEO, a CSV/JSON file, or the bundled demo. 0 NodesHub tokens.
compatibility: "Requires Python 3.9+. Volume source: DataForSEO (optional creds), a CSV/JSON file, or --demo. No NodesHub tokens."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Share of Search

Share of Search is your brand's slice of all brand search demand in your
category. If ten thousand people search your brand and a hundred thousand search
every brand in the category combined, your Share of Search is 10%. Tracked over
time it moves ahead of market share — which is why it is read at board level, not
treated as an SEO mechanic. This skill computes it deterministically from monthly
brand search volume: no model judgment in the numbers.

**First action (CLAUDE.md rule):** run the banner before anything else.

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Share of Search')"
```

The script also prints the banner itself, so running it directly satisfies this.

## Why it matters (Les Binet)

Les Binet's research showed that a brand's Share of Search — its portion of total
category brand searches — is a reliable **leading indicator of market share**.
Share of Search tends to move first; sales and market share follow months later.
A rising share signals future growth; a falling share is an early warning that no
amount of short-term performance marketing fully hides. Because it is built from
public search volume rather than your own analytics, it measures **demand for the
brand**, not your ability to capture clicks — which makes it a clean, comparable
signal across you and every competitor in the set.

## Setup

No mandatory setup — `--demo` and `--volumes` work with zero credentials. The
DataForSEO path is optional.

**DataForSEO (optional, live volumes):** add credentials to the `env` block of
`.claude/settings.local.json`:

```json
{ "env": { "DATAFORSEO_LOGIN": "your-login", "DATAFORSEO_PASSWORD": "your-password" } }
```

The adapter calls `keywords_data/google_ads/search_volume`, reads
`monthly_searches` per keyword, and sums aliases per brand. If the credentials
are absent or the call fails, the skill says so and falls back — it never crashes.

**CSV / JSON fallback (works today, no API):** pass `--volumes PATH`. Two CSV
layouts are accepted:

```
# wide — one row per brand, a column per month
brand,2026-01,2026-02,2026-03
Acme,12000,12600,13200
Globex,22000,21500,21800

# long — one row per brand-month
brand,month,volume
Acme,2026-01,12000
Acme,2026-02,12600
```

JSON: `{ "months": ["2026-01", ...], "volumes": { "Acme": [12000, ...] } }` (a
plain `{ "Acme": [..] }` or `{ "Acme": { "2026-01": 12000 } }` also works).

## Workflow

```bash
# Run it now on the bundled fixture (you + 3 competitors, 6 months)
python3 .claude/skills/nod-share-of-search/scripts/analyze.py --demo

# Live volumes via DataForSEO
python3 .claude/skills/nod-share-of-search/scripts/analyze.py \
  --brand "Acme" --competitors "Globex,Initech,Umbrella" --gl us --hl en

# From your own export (CSV or JSON)
python3 .claude/skills/nod-share-of-search/scripts/analyze.py \
  --brand "Acme" --competitors "Globex,Initech" --volumes brands.csv

# Sum multiple search terms per brand (aliases)
python3 .claude/skills/nod-share-of-search/scripts/analyze.py \
  --brand "Acme" --competitors "Globex" \
  --aliases "Acme:acme app,acme.io;Globex:globex corp"
```

For each month the analyzer computes `share(brand) = brand volume / sum of all
brands' volume`. It then reports, per brand, the latest share, the share trend
(least-squares slope across the available months), and the change from first to
last month. It flags the direction of **your** share (rising / falling / flat)
and the competitor with the **fastest upward momentum** (largest positive slope).

If a merged dataset from `nod-merger` exists and exposes your branded-query
clicks, the report adds a secondary view: **search-demand share vs
captured-clicks share** — how much of category brand demand is yours versus how
much of the clicks you actually capture on your own branded queries.

## Output

A Markdown table of brands with current share %, a text trend arrow
(`^` up / `v` down / `-` flat), the first-to-last change in percentage points,
latest volume, and a short ASCII sparkline of each brand's share history. Below
it: a direction read on your brand, the fastest-rising competitor, and (when
available) the captured-clicks comparison. The full structured report is written
to:

```
data/share-of-search/{YYYY-MM-DD}.json
```

with `months`, per-month `totals`, a `brands` array (share series, latest share,
slope, trend, sparkline), and the `flags` block.

## Parameters

| Param | Description |
|-------|-------------|
| `--brand` | Your brand name |
| `--competitors` | Comma-separated competitor brand names |
| `--aliases` | Optional aliases per brand: `"Brand:kw1,kw2;Other:kw3"` |
| `--volumes` | Path to a brand-volume CSV or JSON (brand -> monthly volumes) |
| `--gl` | Country code for DataForSEO (default `us`) |
| `--hl` | Language code for DataForSEO (default `en`) |
| `--demo` | Run on the bundled demo fixture (you + 3 competitors) |
| `--raw` | Print the raw JSON report instead of the table |

## Cost

0 NodesHub tokens. The optional DataForSEO path uses your own DataForSEO account.
The CSV/JSON and demo paths make no network calls at all.
