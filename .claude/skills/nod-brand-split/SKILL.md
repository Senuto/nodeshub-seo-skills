---
name: nod-brand-split
description: |
  Deterministically split Google Search Console demand into BRANDED vs
  NON-BRANDED queries, so you can see how much traffic is people who already
  know the brand versus genuine new acquisition. Reports the split for clicks and
  impressions, average position per bucket, top queries in each bucket, and the
  trend in non-branded share when two snapshots exist. Matching is pure
  string/regex, so the same input always yields the same report. Use when user
  says "brand vs non-brand," "branded traffic," "non-branded keywords," "brand
  split," "how much traffic is branded," or "acquisition vs brand." Reads a
  merger by_query view or a GSC export; 0 NodesHub tokens.
compatibility: "Requires Python 3.9+; reads merger by_query, a GSC export, or a CSV. No NodesHub key needed."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Brand Split

Split search demand into **branded** (people who already know you — navigational
intent) and **non-branded** (genuine new demand — the acquisition signal). The
script partitions queries using a deterministic, case-insensitive matcher, then
reports clicks, impressions, average position, and top queries per bucket. When
two dated snapshots are available it also reports the trend in non-branded share.
No model judgment is in the path, so the same data plus the same brand terms
always produces the same report.

## Quick Start

```bash
# Run on the newest merger by_query view with your brand name
python3 .claude/skills/nod-brand-split/scripts/analyze.py --brand "acme,acme corp"

# Add a regex for misspellings and variants, and the domain
python3 .claude/skills/nod-brand-split/scripts/analyze.py --brand "acme,acme.com" --brand-regex "acme|akme|acmecorp"

# Run straight off a raw GSC export
python3 .claude/skills/nod-brand-split/scripts/analyze.py --gsc knowledge/metrics/seo/gsc-2026-06-11.json --brand "acme"

# Try it now on the built-in fixture (no data, no brand args needed)
python3 .claude/skills/nod-brand-split/scripts/analyze.py --demo
```

## Setup

No NodesHub key is needed. The script reads queries from one of three sources, in
priority order:

1. `--gsc PATH` — a raw GSC export (uses `topQueries`).
2. `--file PATH` — a CSV with a `query`/`keyword` column (optional clicks,
   impressions, position, conversions columns).
3. Default — the newest `data/merged/*.json` produced by the **/nod-merger**
   skill (the `by_query` view: `query, clicks, impressions, ctr, position`).

You must supply a brand definition with `--brand` and/or `--brand-regex` —
without one, every query would fall into non-branded. `--demo` ships its own
brand terms so it runs with zero arguments.

## Workflow

1. **Resolve the source** — `--gsc`, `--file`, else newest merger output, else
   newest GSC export.
2. **Build the matcher** from `--brand` terms and `--brand-regex`.
3. **Partition** every query into branded / non-branded.
4. **Compute the split** for clicks and impressions: bucket totals, percentages,
   and average position per bucket.
5. **Rank top queries** in each bucket (by clicks, then impressions).
6. **Call out non-branded clicks** as the acquisition signal — demand from people
   who did not search the brand by name.
7. **Trend** — if two or more snapshots exist (`data/merged/*.json` or dated
   `gsc-*.json`), report the change in non-branded share of clicks between the
   two newest. With only one snapshot, say so plainly — no second point is
   invented.
8. **Save** to `data/brand-split/{YYYY-MM-DD}.json` and print readable tables.

## The matching rule

A query is **branded** if it matches **any** supplied brand term or the brand
regex (case-insensitive):

- **`--brand` terms** match as whole words/phrases with a word boundary on each
  side, so `acme` matches `acme shoes` but not `acmebackwards`. A term that looks
  like a domain (contains a dot, e.g. `acme.com`) matches as a substring, because
  word boundaries behave poorly around dots.
- **`--brand-regex`** is a raw case-insensitive regular expression for
  misspellings and variants, e.g. `acme|akme|acmecorp`.

Everything matching no term and no regex is **non-branded**.

## Output

```markdown
## Brand Split
**Source:** ... | **Date:** 2026-06-11 | **Brand terms:** acme, acme corp

| Bucket | Queries | Clicks | Clicks % | Impressions | Impr % | Avg pos |
|--------|---------|--------|----------|-------------|--------|---------|
| Branded | 5 | 1265 | 56.2% | 17500 | 21.6% | 2.2 |
| Non-branded | 6 | 985 | 43.8% | 63400 | 78.4% | 9.1 |

**Acquisition signal:** non-branded clicks = 985 (43.8% of all clicks).

### Top branded queries / Top non-branded queries
...

### Trend (non-branded share of clicks)
2026-05-11.json: 41.0%  ->  2026-06-11.json: 43.8%  (▲ +2.8 pts)
```

The same data is saved as JSON to `data/brand-split/{YYYY-MM-DD}.json` with
totals, per-bucket metrics, top queries, and the trend.

Conversions: GSC has no query dimension for conversions, so per-query
conversions cannot be attributed honestly. If the merged dataset carries
URL-level conversions, the report notes this and skips the conversions split
rather than fabricate it.

## Cost

- **0 NodesHub tokens.** Everything runs offline on local data; there are no API
  calls in this skill.

## Note

Review the matching for false positives before trusting the split: a generic
brand name (e.g. "apple," "shell") can match informational queries that are not
truly branded. Inspect the top branded queries and tighten `--brand` /
`--brand-regex` if anything looks like real non-branded demand.

## Parameters

| Param | Description |
|-------|-------------|
| `--gsc` | Path to a raw GSC export JSON (uses `topQueries`) |
| `--file` | Path to a CSV with a query column (+ optional metrics) |
| `--brand` | Comma-separated brand terms, e.g. `"acme,acme corp,acme.com"` |
| `--brand-regex` | Raw case-insensitive regex for brand variants/misspellings |
| `--top` | Top N queries per bucket (default: 10) |
| `--demo` | Run on the built-in mixed branded/non-branded fixture |
| `--raw` | Print the raw JSON report instead of the tables |

## Related Skills

- **nod-merger** — produces the `by_query` view this skill reads by default.
- **nod-keyword-research** — expand the non-branded queries that are growing.
- **nod-content-brief** — turn winning non-branded demand into content.
