---
name: nod-money-keywords
description: |
  Find the expensive paid terms you could win organically to cut your customer
  acquisition cost (CAC). Surfaces high-CPC, high-volume keywords where you do
  NOT yet rank well organically — the clicks you can only buy today. Estimates
  the monthly paid value you would replace by ranking organically instead, and
  flags an "almost there" list (rank 4-10) where a small push is a big paid
  saving. Deterministic — pure rules, no LLM. The inverse of nod-paid-organic
  (which finds wasted spend on terms you already rank top-3 for). Use when the
  user says "money keywords", "reduce cac", "expensive keywords", "win paid
  terms organically", "high cpc opportunities", or "cut ad spend with seo".
  Reads volume/cpc/position from nod-merger. 0 NodesHub tokens.
compatibility: "Requires Python 3.9+. Needs a merged dataset (nod-merger) with Google Ads volume/cpc and GSC organic position in by_query. No NodesHub key required."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Money Keywords

Find the expensive paid terms you could win with SEO instead of buying every
month. A "money keyword" is a high-CPC, high-volume term where you do NOT yet
rank well organically — so today the only way to get the click is to pay for it.
Rank organically and you stop paying. This skill ranks those terms by the monthly
paid value you could replace, and flags an "almost there" list where you already
sit at positions 4-10 and a small push pays off fast. Pure rules, so the same
inputs always produce the same report.

This is the **complement to nod-paid-organic**: that skill finds *wasted spend*
on terms you already rank top-3 for (stop paying); this one finds *expensive
terms you do not yet rank for* (start winning).

**First action (banner):**
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Money Keywords')"
```

## Quick Start

```bash
# Try it now on the bundled fixture (no real data or key needed)
python3 .claude/skills/nod-money-keywords/scripts/analyze.py --demo

# Real run against the newest merged dataset
python3 .claude/skills/nod-money-keywords/scripts/analyze.py

# Tighter filters and a more ambitious target position
python3 .claude/skills/nod-money-keywords/scripts/analyze.py \
  --min-cpc 2.0 --min-volume 500 --target-position 3 \
  --merged data/merged/2026-06-11.json
```

## Setup

You need **one input: a merged dataset** from **nod-merger**. This skill reads
`volume`, `cpc`, and organic `position` from the merger's `by_query` view via
`load_merged()`, so the data contract lives in one place.

The merger's `by_query` carries Ads keyword metrics (volume / cpc / competition)
joined onto GSC organic positions. Run it first:

```bash
python3 .claude/skills/nod-merger/scripts/merge.py
```

Only keywords with both `volume` and `cpc` present are considered — those are the
ones with enough commercial signal to judge as paid terms. Pass `--merged PATH`
to pin a specific file, or let it pick the newest in `data/merged/`.

No NodesHub key is needed. The whole analysis is local.

## Workflow

1. **Load `by_query`** from nod-merger (volume, cpc, organic position).
2. **Filter** to keywords with both `volume` and `cpc` present.
3. **Select money keywords** — expensive AND in-demand AND weak organic (rules
   below).
4. **Score** each by estimated monthly paid value you could replace at the
   target position.
5. **Rank** descending by that value, and build the secondary "almost there"
   list (positions 4-10).
6. **Save** the report to `data/money-keywords/{YYYY-MM-DD}.json` and print
   tables plus the total addressable paid value.

## Scoring rule

A keyword is a **money keyword** when all three hold:

| Signal | Condition | Why |
|--------|-----------|-----|
| Expensive | `cpc >= --min-cpc` (default 1.0) | A commercially valuable click you are paying for. |
| In demand | `volume >= --min-volume` (default 200) | Enough monthly searches to be worth winning. |
| Weak organic | `position > 10` or not ranking | You can only *buy* this click today — SEO upside is real. |

**Estimated reclaimable monthly value** = `volume * CTR_at_target_position * cpc`,
where the CTR comes from a fixed organic CTR curve at a realistic achievable
position (`--target-position`, default 5 ~ 6% CTR). It is the paid spend you
would stop needing if you ranked there organically.

The **"almost there"** list uses the same expensive + in-demand filter but
selects terms already at positions **4-10** — close enough that a small organic
push is a big, cheap paid saving. Terms already in the top 3 are intentionally
excluded; those belong to nod-paid-organic's wasted-spend case.

Both lists are ranked by estimated reclaimable value, descending.

## Output Format

```markdown
## Money Keywords Report
**Date:** 2026-06-11 | **Filters:** CPC >= $1.00, volume >= 200 | **Target position:** #5 (~6.0% CTR)

- Money keywords (don't rank, expensive):  4
- Total addressable paid value:            $6,901.20/mo (est.)
- Almost there (rank 4-10):                2
- Almost-there paid value:                 $612.40/mo (est.)

### Money keywords — stop paying, win these with SEO (4)
| Keyword | Volume | CPC | Current pos | Est. reclaimable $/mo |
|---------|--------|-----|-------------|-----------------------|
| project management tool | 12000 | $9.50 | 18.4 | $6840.00 |
...
```

The same data is saved as JSON to `data/money-keywords/{YYYY-MM-DD}.json` with
the summary, the ranked `money_keywords` list, and the `almost_there` list. Each
row carries volume, cpc, current position, target position, assumed CTR, the
estimated reclaimable monthly value, and a plain-language rationale.

## Cost

- **0 NodesHub tokens.** The analysis reads the local merged dataset and scores
  offline. There is no network call.

## Note

The reclaimable value is an **estimate** (`volume * assumed CTR at the target
position * cpc`). It assumes you actually reach the target organic position and
ignores SERP layout, brand vs non-brand intent, and seasonality. Treat it as a
prioritized hit list to win organically, not a guaranteed saving. This skill is
the complement to **nod-paid-organic**: there you already rank top-3 (stop
paying); here you do not yet rank (start winning to cut CAC).

## Parameters

| Param | Description |
|-------|-------------|
| `--merged` | Path to a merged dataset (default: newest in `data/merged`) |
| `--demo` | Run on a bundled inline `by_query` fixture (no data/key needed) |
| `--min-cpc` | Minimum CPC for a term to count as expensive (default: 1.0) |
| `--min-volume` | Minimum monthly search volume (default: 200) |
| `--target-position` | Realistic achievable organic position for the CTR estimate (default: 5) |
| `--raw` | Print the raw JSON report instead of tables |

## Related Skills

- **nod-paid-organic** — the inverse: wasted spend on terms you already rank top-3 for.
- **nod-merger** — produces the merged dataset this skill reads volume/cpc/position from.
- **nod-opportunity-detector** — broader SEO opportunity engine across the keyword set.
- **nod-serp-analysis** — inspect the live SERP for a contested money keyword.
