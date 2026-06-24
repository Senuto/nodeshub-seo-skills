---
name: nod-commercial-value
description: |
  Deterministically rank a keyword set by REVENUE potential, not by traffic.
  Scores each keyword by commercial value (volume x cpc — the market's own price
  on a click) weighted by how far it sits from page one, then sorts the set into
  Tier 1 / 2 / 3 so the client decides what to work on FIRST by money, not by
  search volume. Pure rules, so the same input always yields the same ranking.
  Use when user says "commercial value," "prioritize by revenue," "value-weighted
  keywords," "what to work on first," "revenue potential keywords," or "priority by
  money." Reads keywords from the merger (by_query) or a CSV; no NodesHub tokens.
compatibility: "Requires Python 3.9+. Needs volume + cpc per keyword (via the merger's Ads data or a CSV). No NodesHub key required."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Commercial Value

Rank any keyword set by the money behind it, not the traffic in front of it. A
keyword with huge search volume can be worth little (cheap clicks, already
captured at #1), while a smaller keyword with a high CPC and no ranking can be
worth chasing first. This skill makes that trade-off explicit and repeatable.

The scoring is pure rules — no model judgment — so the same keyword set always
produces the same tiers.

## First action

When this skill is invoked, run the banner first (CLAUDE.md rule):

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Commercial Value')"
```

## Quick Start

```bash
# Rank keywords from the newest merged dataset (by_query)
python3 .claude/skills/nod-commercial-value/scripts/analyze.py

# Rank a CSV of keywords (keyword, volume, cpc, position — position optional)
python3 .claude/skills/nod-commercial-value/scripts/analyze.py --file keywords.csv

# Point at a specific merged dataset
python3 .claude/skills/nod-commercial-value/scripts/analyze.py --merged data/merged/2026-06-11.json

# Try it now on the bundled fixture (no data or key needed)
python3 .claude/skills/nod-commercial-value/scripts/analyze.py --demo
```

## Setup

No NodesHub key is needed. The skill needs **volume + cpc** per keyword. Two ways
to supply them:

1. **Via the merger (recommended).** Run
   `python3 .claude/skills/nod-merger/scripts/merge.py` after fetching Google Ads
   metrics (`node scripts/fetch-google-ads.js --csv your-keywords.csv`). The
   merger's `by_query` view carries volume, cpc, and your current GSC position —
   everything this skill needs in one place.
2. **Via a CSV.** Export a keyword list with columns `keyword, volume, cpc,
   position` (position optional). The same flexible header aliases used by
   `scripts/fetch-google-ads.js` apply, so Google Ads, DataForSEO, and Senuto
   exports all work. Keywords missing volume or cpc cannot be valued and are
   scored at zero so they sort to the bottom.

Use `--demo` to see the output format before you have real data.

## Workflow

1. **Load the keyword set** — newest `data/merged/*.json` `by_query` view by
   default, or `--merged PATH`, or `--file keywords.csv`.
2. **Value each keyword** — `commercial_value = volume * cpc`.
3. **Weight by opportunity gap** — map the current organic position to an
   opportunity multiplier (see formula below).
4. **Compute priority** — `priority = commercial_value * opportunity_multiplier`.
5. **Rank and tier** — sort by priority descending and split into Tier 1 / 2 / 3.
6. **Report** — print the tiered table, the set's total commercial value, and the
   share of priority concentrated in Tier 1.
7. **Save** the structured report to `data/commercial-value/{YYYY-MM-DD}.json`.

## Scoring formula

```
commercial_value = volume * cpc
```

Volume is how many people search; CPC is what an advertiser pays for one click —
the market's own estimate of a click's worth. Their product is a clean proxy for
the money on the table behind a keyword.

```
opportunity_multiplier  (from current organic position)

  not ranking / position > 20  -> 1.00   full upside, nothing captured yet
  page 2 (11 - 20)             -> 0.75   high upside, close to page one
  positions 4 - 10             -> 0.40   medium upside, partly captured
  top 3 (1 - 3)                -> 0.10   low upside, already captured
```

```
priority = commercial_value * opportunity_multiplier
```

A keyword you already own at #1 has high commercial value but low priority — that
revenue is already yours. A high-CPC keyword you do not rank for keeps its full
value, so it rises to the top of the work list.

## Output Format

```markdown
## Commercial Value Report
**Source:** ... | **Date:** 2026-06-11

**Keywords:** 10
**Total commercial value:** $607,752 (volume x cpc across the set)
**Tier 1 share of priority:** 70.7% in 3 keyword(s)

### Tier 1 — work on first (highest revenue priority)
| Keyword | Volume | CPC | Commercial value | Position | Opportunity | Priority |
|---------|--------|-----|------------------|----------|-------------|----------|
| enterprise seo platform | 4,400 | $18.50 | $81,400 | not ranking | full | $81,400 |
...
```

Tiers split the ranked set into thirds by priority (Tier 1 = top third). Small
sets degrade gracefully, and zero-priority keywords (unvalued, or top-ranked with
nothing left to capture) always fall to Tier 3. The same data is saved as JSON to
`data/commercial-value/{YYYY-MM-DD}.json` with per-keyword commercial value,
opportunity, and priority, plus set-wide totals.

## Cost

- **0 NodesHub tokens.** The skill reads local data (a merged dataset or a CSV)
  and runs entirely offline. No API calls.

## Parameters

| Param | Description |
|-------|-------------|
| `--file` | CSV with columns `keyword, volume, cpc, position` (position optional) |
| `--merged` | Explicit merged dataset JSON (default: newest in `data/merged`) |
| `--demo` | Run on the bundled `sample_keywords.csv` fixture |
| `--raw` | Print the raw JSON report instead of the table |

## Note

This complements **nod-money-keywords**: that skill is the paid-CAC-reduction
angle (rank organically for terms you already pay for). Commercial Value is the
general prioritization lens — it ranks ANY keyword set, ranked or not, by revenue.

## Related Skills

- **nod-merger** — builds the `by_query` dataset (volume, cpc, position) this skill consumes.
- **nod-money-keywords** — the paid-CAC angle on the same money question.
- **nod-opportunity-detector** — surfaces opportunities across the merged dataset.
