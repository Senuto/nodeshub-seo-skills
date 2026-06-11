---
name: nod-opportunity-detector
description: |
  Deterministic SEO opportunity engine. Reads the merged GSC + GA4 + Ads dataset
  (from nod-merger) and outputs a prioritized SEO action list: striking-distance
  rankings, low CTR for position, traffic without conversions, decaying pages,
  and cannibalization conflicts folded in. Every rule is pure, so the same merged
  file always yields the same actions and scores. Use when the user says "find
  opportunities," "what should I fix," "SEO action list," "quick wins," "striking
  distance," "low-hanging fruit," "opportunity detector," or "where should I focus."
  Reads local merged data; no NodesHub tokens.
compatibility: "Requires Python 3.9+; reads a merged dataset from nod-merger (data/merged/*.json). No API key needed."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Opportunity Detector

Turn the merged GSC + GA4 + Ads dataset into a single prioritized action list.
The detector runs a set of pure rules over the merged file produced by
`nod-merger`, scores each opportunity 0-100, sorts them, and saves a dated
report. Detection is fully deterministic — the same merged file always produces
the same opportunities and the same priorities, with no model judgment in the
path.

## Quick Start

```bash
# Run on the newest merged dataset
python3 .claude/skills/nod-opportunity-detector/scripts/detect.py

# Specific merged dataset
python3 .claude/skills/nod-opportunity-detector/scripts/detect.py --file data/merged/2026-06-11.json

# Try it now on the bundled fixture (no real data needed)
python3 .claude/skills/nod-opportunity-detector/scripts/detect.py --demo

# Raise the striking-distance impression floor
python3 .claude/skills/nod-opportunity-detector/scripts/detect.py --min-impressions 200
```

## Setup

No NodesHub key is needed. The detector reads a merged dataset, so the only
prerequisite is running the merger first.

1. Produce a merged dataset with the **/nod-merger** skill. It writes
   `data/merged/{YYYY-MM-DD}.json` with `by_url` and `by_query` views.
2. Run the detector. It imports the merger's `load_merged` helper to read the
   newest merged file, or you can point it at one with `--file`.
3. Use `--demo` to see the output format before you have real data — it ships a
   `scripts/sample_merged.json` fixture.

Two optional inputs make the report richer when present, and are skipped quietly
when absent:

- **A second merged snapshot** in `data/merged/` enables the decaying-pages rule
  (month-over-month click comparison). With only one snapshot, that rule is
  skipped with a note — it never fabricates a trend.
- **A cannibalization report** in `data/cannibalization/{date}.json` (from
  **/nod-cannibalization**) is folded in as opportunities.

## Workflow

1. **Locate the merged dataset** — newest `data/merged/*.json`, or `--file PATH`.
2. **Read `by_url` and `by_query`** views from the merged file.
3. **Run each rule** to produce opportunity items with deterministic scores.
4. **Fold in** the latest cannibalization report if one exists.
5. **Compare snapshots** for decay if a previous merged file exists.
6. **Sort** by priority (descending), with stable tie-breaks on type then target.
7. **Save** the report to `data/opportunities/{YYYY-MM-DD}.json` and print a
   grouped table summary.

## Rules

Each rule emits items of the form
`{ type, target, evidence, priority (0-100), recommended_action }`.

- **striking_distance** — a query or URL at `position` between 5 and 15 with
  `impressions >= --min-impressions` (default 50). The closer to page 1 (lower
  position), the higher the priority. These are the fastest ranking wins.
- **low_ctr_vs_position** — actual `ctr` compared against a hardcoded
  expected-CTR-by-position curve (pos 1 ~28%, pos 2 ~15%, pos 3 ~11%, ... pos 10
  ~2.5%, flat tail below). Flagged when actual CTR is at most 60% of expected and
  impressions clear a noise floor. Signals a title / meta-description rewrite.
- **high_impr_no_conversions** *(needs GA4)* — a URL with real impressions and
  clicks but `conversions == 0`. Points to search-intent or landing-page
  mismatch. Skipped when GA4 is absent or the conversion metric was not exported.
  Note: this rule uses its own fixed floors (1000 impressions / 30 clicks), not
  `--min-impressions`.
- **decaying_page** *(needs two snapshots)* — clicks dropped beyond -25%
  month-over-month versus the previous merged snapshot. With only one snapshot
  the rule is skipped and the report says so; it does not fabricate a trend.
- **cannibalization** — high/medium conflicts from the latest
  `data/cannibalization/{date}.json` report, mapped onto the same 0-100 priority
  scale and carried through with their original recommendation.

### How priority is scored

Priority is a deterministic 0-100 number per rule. Striking distance scores on
closeness to page 1. Low CTR scores on the size of the shortfall plus the volume
of clicks left on the table. The conversion rule scores on wasted click demand.
Decay scores on the size of the drop and the page's prior click volume.
Cannibalization maps its own severity score onto the shared scale. Ties break
deterministically on type then target, so output order is fully repeatable.

## Output Format

```markdown
## Opportunity Report
**Source:** data/merged/2026-06-11.json | **Date:** 2026-06-11 | **Min impressions:** 50

**Opportunities:** 14 (striking distance: 7, low ctr for position: 5, traffic without conversions: 2)

### Striking distance (page 2 -> page 1)
| Priority | Target | Evidence | Action |
|----------|--------|----------|--------|
| 88 | /blog/link-building-guide | pos 6.2, 5400 impr | Strengthen on-page relevance and internal links to reach page 1. |

### Low CTR for position (title/snippet fix)
| Priority | Target | Evidence | Action |
|----------|--------|----------|--------|
| 96 | /tools/keyword-research | CTR 1.11% vs ~11.0% @ pos 3.1 | Rewrite the title tag and meta description. |
```

The full structured report is saved to `data/opportunities/{YYYY-MM-DD}.json`
with every opportunity's metrics, priority, and recommended action.

## Cost

- **0 NodesHub tokens.** The detector reads a local merged dataset and runs
  offline. It makes no API calls and uses no LLM in the detection path.

## Parameters

| Param | Description |
|-------|-------------|
| `--file` | Path to a merged dataset JSON (default: newest in `data/merged`) |
| `--demo` | Run on the bundled `sample_merged.json` fixture |
| `--min-impressions` | Striking-distance impression floor (default: 50) |
| `--raw` | Print the raw JSON report instead of grouped tables |

## Related Skills

- **nod-merger** — produces the merged dataset this skill reads. Run it first.
- **nod-cannibalization** — its report is folded in here as opportunities.
- **nod-content-auditor** — audit a flagged page against the live SERP.
- **nod-rank-tracker** — track positions for the striking-distance targets you act on.
