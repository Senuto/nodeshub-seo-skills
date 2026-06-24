---
name: nod-paid-organic
description: |
  Marketing-grade overlap analysis between paid (Google Ads) and organic (GSC)
  for the same keywords. Surfaces the money-shot: keywords where you PAY in Ads
  but ALREADY rank top-3 organically (potential wasted spend), plus where to keep
  paying (weak organic) and where to defend (competitor ads on your terms).
  Deterministic — pure rules, no LLM. Use when the user says "paid vs organic",
  "wasted ad spend", "ppc seo overlap", "am i paying for keywords i rank for",
  "ads cannibalization", or "reclaim ad budget". Reads a paid-keywords CSV and
  organic positions from nod-merger. No NodesHub tokens unless --check-serp-ads.
compatibility: "Requires Python 3.9+. Needs an Ads campaign keywords CSV and a merged dataset (nod-merger). NodesHub key only for --check-serp-ads."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Paid vs Organic

Find where your Google Ads spend overlaps your organic rankings. The headline
insight is wasted spend: keywords you pay for in Ads while you already rank in
the organic top 3. The flip side matters too — terms where organic is weak (or
absent) are where paid genuinely earns its keep. Classification is pure rules, so
the same inputs always produce the same report.

**First action (banner):**
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Paid vs Organic')"
```

## Quick Start

```bash
# Try it now on the bundled fixture (no real data needed)
python3 .claude/skills/nod-paid-organic/scripts/analyze.py --demo

# Real run: your Ads campaign export, joined with the newest merged dataset
python3 .claude/skills/nod-paid-organic/scripts/analyze.py --paid-csv ads-campaign.csv

# Pin a specific merged dataset and check competitor ads on your organic terms
python3 .claude/skills/nod-paid-organic/scripts/analyze.py \
  --paid-csv ads-campaign.csv \
  --merged data/merged/2026-06-11.json \
  --check-serp-ads --gl us --hl en
```

## Setup

You need two inputs:

1. **A paid-keywords CSV** (`--paid-csv PATH`) — your Google Ads campaign export:
   the keywords you actually bid on, with **cost / spend**, **clicks / paid
   clicks**, **conversions**, and optionally **cpc**. Header names are normalized
   and alias-matched (the same approach as `scripts/fetch-google-ads.js`), so
   `Cost`, `Spend`, `Total cost` all map to one field. Duplicate keywords across
   ad groups are aggregated into a single spend figure.

   Why a separate CSV? The merger's Ads view holds keyword *metrics* (volume,
   cpc, competition) — that is search demand, not proof you run ads. Only your
   campaign export shows real spend.

2. **A merged dataset** for organic positions. Run **nod-merger** first; this
   skill reads organic `position` from its `by_query` view via `load_merged()`.
   ```bash
   python3 .claude/skills/nod-merger/scripts/merge.py
   ```
   Pass `--merged PATH` to pin a specific file, or let it pick the newest in
   `data/merged/`.

No NodesHub key is needed for the core analysis. `--check-serp-ads` is the only
feature that calls the API and it skips gracefully without a key.

## Workflow

1. **Ingest the paid CSV** — normalize headers, alias-match columns, aggregate
   duplicate keywords (cost/clicks/conversions summed).
2. **Load organic positions** — from nod-merger's `by_query`, joined on the
   normalized keyword (lowercase, collapsed whitespace).
3. **Classify** each overlapping keyword by its organic position (rules below).
4. **(Optional) `--check-serp-ads`** — for terms where you rank organically,
   check whether competitor ads sit on the SERP (1 token per term).
5. **Summarize** total spend and estimated reclaimable spend.
6. **Save** the report to `data/paid-organic/{YYYY-MM-DD}.json` and print tables.

## Classification rules

| Class | Condition | Meaning |
|-------|-----------|---------|
| **Wasted spend candidate** | paid cost AND organic position `<= 3` | You already rank top-3 organically — this paid cost is potentially reclaimable. The money-shot. |
| **Justified paid** | paid cost AND organic position `> 10` or not ranking | Organic is weak or absent — paid is doing the work. Keep it. |
| **Defend / monitor** | paid cost AND organic position `4-10` | Borderline. Watch the organic position before cutting paid. |

Estimated reclaimable spend = the sum of paid cost on wasted-spend candidates.

## Output Format

```markdown
## Paid vs Organic Report
**Date:** 2026-06-11 | **Paid keywords:** 7

- Total ad spend:            $6896.95
- Estimated reclaimable:     $2215.90 (32.1% of spend)
- Wasted spend candidates:   3
- Justified paid:            3
- Defend / monitor:          1

### Wasted spend candidates (you already rank top-3) (3)
| Keyword | Spend | Paid clicks | Conv. | Organic pos |
|---------|-------|-------------|-------|-------------|
| seo tools | $1240.50 | 410 | 18 | 2.1 |
...
```

The same data is saved as JSON to `data/paid-organic/{YYYY-MM-DD}.json` with the
summary plus the three classified lists, each row carrying its cost, paid clicks,
conversions, organic position, classification, and a plain-language rationale.

## Cost

- **Core analysis: 0 NodesHub tokens.** It reads a local CSV and the local
  merged dataset, then classifies offline.
- **`--check-serp-ads`: 1 token per organic-ranking term.** This is the only
  feature that calls the API, and it skips quietly when no key is configured.

## Note

Reclaimable spend is an **estimate**. It assumes paid clicks on top-3 organic
terms could be recovered organically, which ignores SERP layout, brand vs
non-brand intent, and ad incrementality. Treat it as a prioritized hit list to
validate with incrementality testing, not a guaranteed saving.

## Parameters

| Param | Description |
|-------|-------------|
| `--paid-csv` | Path to your Ads campaign keywords export (CSV). Required unless `--demo`. |
| `--merged` | Path to a merged dataset (default: newest in `data/merged`) |
| `--demo` | Run on the bundled `sample_paid.csv` + an inline organic fixture |
| `--check-serp-ads` | Check competitor ads on your organic terms (1 token/term) |
| `--gl` | Country code for `--check-serp-ads` (default: us) |
| `--hl` | Language code for `--check-serp-ads` (default: en) |
| `--raw` | Print the raw JSON report instead of tables |

## Related Skills

- **nod-merger** — produces the merged dataset this skill reads organic positions from.
- **nod-cannibalization** — find organic pages competing with each other for one query.
- **nod-serp-analysis** — inspect the live SERP for a contested paid/organic term.
