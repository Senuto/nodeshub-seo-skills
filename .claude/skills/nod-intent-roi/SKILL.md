---
name: nod-intent-roi
description: |
  Ties search intent to actual conversions so content is prioritized by ROI, not
  by traffic volume. Aggregates a merged GSC + GA4 + Ads dataset into intent
  buckets (informational / commercial / transactional / navigational) and reports
  which intent type actually converts and where to invest next. Aggregation is
  deterministic — the same merged dataset always yields the same table; no model
  judgment. Use when user says "intent roi," "which intent converts," "prioritize
  by roi," "intent conversions," "roi by search intent," or "content roi." Reads
  the merger's output; no NodesHub tokens unless --classify is used.
compatibility: "Requires Python 3.9+; reads nod-merger output (needs GA4 conversions). NodesHub key only for --classify."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Intent ROI

Most content roadmaps are sorted by traffic. This one sorts by money. Intent ROI
takes the merged funnel dataset (GSC + GA4 + Ads), buckets every query by search
intent, attributes the conversions earned on each landing page back up to the
query's intent, and tells you which intent type pays — informational, commercial,
transactional, or navigational. The aggregation is pure rules, so the same merged
dataset always produces the same table.

**Banner first.** When this skill is invoked, run the banner as the first action:

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Intent ROI')"
```

## Quick Start

```bash
# Run on the newest merged dataset
python3 .claude/skills/nod-intent-roi/scripts/analyze.py

# Specific merged dataset, with a GSC export for query x page association
python3 .claude/skills/nod-intent-roi/scripts/analyze.py --merged data/merged/2026-06-11.json --gsc knowledge/metrics/seo/gsc-2026-06-11.json

# Try it now on the bundled fixture (no key, no data needed)
python3 .claude/skills/nod-intent-roi/scripts/analyze.py --demo

# Fill in missing intents via NodesHub (2 tokens per keyword)
python3 .claude/skills/nod-intent-roi/scripts/analyze.py --classify --gl us --hl en
```

## Setup

This skill consumes the **nod-merger** output, so the merged dataset must exist
and ideally carry GA4 conversions in its `by_url` view.

1. Connect GSC (**/connect-gsc**) and GA4 (**/connect-ga4**) if you have not.
   GA4 conversions are what make the ROI numbers real.
2. Build the merged dataset with **/nod-merger** (`python3 .claude/skills/nod-merger/scripts/merge.py`).
3. Run the analyzer. Use `--demo` to see the format before you have real data.

Intent comes from one of three places, in order:
- `by_query.intent` if the merged rows are already SERP-enriched
  (`merge.py --enrich-serp`), then
- the NodesHub intent classifier when `--classify` is passed (2 tokens/keyword),
  which skips quietly without a key, then
- `unknown` for anything still unlabeled.

Only `--classify` needs `NODESHUB_API_KEY`. Without it, the deterministic core
still runs and unlabeled queries are reported as `unknown`.

## Workflow

1. **Load merged** — newest `data/merged/*.json`, or `--merged PATH`.
2. **Resolve intent per query** — use `by_query.intent`; else `--classify` via
   NodesHub; else `unknown`. Aliases (buy, compare, brand, ...) map onto the four
   canonical buckets.
3. **Associate query -> landing page** — prefer GSC `queryPages` (the page with
   the most clicks for that query), else a coarse URL token match against
   `by_url`. An explicit `page`/`landing_page` field on a row wins outright.
4. **Pull URL-level outcomes** — sessions and conversions from `by_url` (GA4).
5. **Roll up into intent buckets** — each URL's outcomes are counted once (into
   the first query that claims it) so totals stay honest.
6. **Compute per intent** — clicks, sessions, conversions, conversion rate, ROI
   proxy (conversions per 100 clicks), and share of conversions.
7. **Rank by efficiency** — order intents by ROI proxy, then pick the best- and
   worst-converting intent and a one-line investment recommendation.
8. **Save** to `data/intent-roi/{YYYY-MM-DD}.json` and print the table.

## Attribution caveat (read this)

GA4 has no query dimension. Conversions and sessions exist **only per URL**, never
per query. To get a per-intent number, the skill attributes each query to the page
it ranks for, then rolls that page's GA4 outcomes up into the query's intent
bucket. Each URL's outcomes are counted once to avoid inflating totals when a URL
ranks for several queries.

This is an **approximation**, not an exact split: one URL can rank for queries of
different intents, so its conversions cannot be cleanly divided among them. Treat
the per-intent ROI as a directional signal for prioritization, not a precise
attribution model. The caveat is printed in every report.

## Output Format

```markdown
## Intent ROI
**Source:** ... | **Date:** 2026-06-11 | **Classify:** no

Attributed 8 / 8 queries to 7 landing page(s).
_Caveat:_ GA4 has no query dimension. ... approximation, not an exact split ...

| Intent | Clicks | Conversions | CvR | ROI /100 clicks | Share of conv. |
|--------|--------|-------------|-----|-----------------|----------------|
| transactional | 470 | 152 | 8.0% | 32.34 | 67% |
| commercial | 470 | 57 | 3.0% | 12.13 | 25% |
| informational | 1310 | 16 | 0.3% | 1.22 | 7% |

**Best-converting intent:** transactional
**Worst-converting intent:** informational

**Recommendation:** Shift content investment toward transactional intent ...
```

The same data is saved as JSON to `data/intent-roi/{YYYY-MM-DD}.json` with the full
per-intent metrics, the attribution stats, and the recommendation.

## Cost

- **Core analysis: 0 NodesHub tokens.** It reads the local merged dataset and runs
  offline.
- **`--classify`: 2 tokens per keyword** lacking an intent. This is the only
  feature that calls the API, and it skips quietly when no key is configured.

## Parameters

| Param | Description |
|-------|-------------|
| `--merged` | Path to a merged dataset (default: newest in `data/merged`) |
| `--gsc` | GSC export used for query x page association (`queryPages`) |
| `--demo` | Run on the bundled `sample_intent_roi.json` fixture |
| `--classify` | Classify queries missing an intent via NodesHub (2 tokens/keyword) |
| `--gl` | Country code for `--classify` (default: us) |
| `--hl` | Language code for `--classify` (default: en) |
| `--raw` | Print the raw JSON report instead of the table |

## Related Skills

- **nod-merger** — builds the GSC + GA4 + Ads dataset this skill consumes.
- **nod-opportunity-detector** — finds high-traffic pages with zero conversions.
- **nod-cannibalization** — resolve competing pages before trusting per-URL ROI.
