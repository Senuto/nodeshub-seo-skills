---
name: nod-cannibalization
description: |
  Deterministic keyword cannibalization detector that runs on Google Search Console
  data. Flags queries where two or more of your own pages compete for the same
  search, scores each conflict by severity, and recommends a fix (consolidate,
  canonical, or de-optimize). Detection is pure rules, so the same export always
  yields the same report. Use when user says "cannibalization," "keyword
  cannibalization," "competing pages," "multiple urls ranking," "duplicate
  ranking," or "two pages ranking for the same query." Reads a GSC export; no
  NodesHub tokens unless --verify-serp is used.
compatibility: "Requires Python 3.9+; reads GSC export. NodesHub key only for --verify-serp."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Cannibalization

Detect keyword cannibalization from Google Search Console data. The detector
groups GSC `query x page` rows by query and flags every query where two or more
distinct pages clear the impression floor. Severity and recommendations are
rule-based, so output is repeatable — no model judgment in the detection path.

## Quick Start

```bash
# Run on the newest GSC export
python3 .claude/skills/nod-cannibalization/scripts/detect.py

# Specific export
python3 .claude/skills/nod-cannibalization/scripts/detect.py --file knowledge/metrics/seo/gsc-2026-06-11.json

# Try it now on the bundled fixture (no GSC data needed)
python3 .claude/skills/nod-cannibalization/scripts/detect.py --demo

# Raise the noise floor, then confirm the live ranker per query
python3 .claude/skills/nod-cannibalization/scripts/detect.py --min-impressions 25 --verify-serp --gl us --hl en
```

## Setup

No NodesHub key is needed for detection. The script reads a GSC export written by
`scripts/fetch-gsc.js` into `knowledge/metrics/seo/`.

1. Connect GSC with the **/connect-gsc** skill if you have not already.
2. Generate an export: `npm run fetch-gsc` (the export must include the
   `queryPages` array — re-run the fetcher if an older export lacks it).
3. Run the detector. Use `--demo` to see the format before you have real data.

`--verify-serp` is the only feature that needs `NODESHUB_API_KEY`. Without a key it
skips gracefully and the rest of the report still runs.

## Workflow

1. **Locate the export** — newest `knowledge/metrics/seo/gsc-*.json`, or `--file PATH`.
2. **Read `queryPages`** — if the array is missing, the script tells you to re-run `npm run fetch-gsc`.
3. **Group by query** and keep pages with impressions >= `--min-impressions` (default 10).
4. **Flag conflicts** — a query is cannibalized when two or more distinct pages clear the floor.
5. **Score severity** — higher when impressions/clicks split evenly and the top page flips. Tags: high / medium / low.
6. **Recommend a fix** — consolidate, set canonical to the strongest URL, or de-optimize the weaker page.
7. **(Optional) `--verify-serp`** — confirm which URL actually ranks live (1 token per query).
8. **Save** the structured report to `data/cannibalization/{YYYY-MM-DD}.json` and print a table summary.

### How severity is computed

- **Even impression split (45%)** — Google can't decide which page to rank.
- **Even click split (30%)** — neither page wins the traffic.
- **Ranking flip (15%)** — the page earning impressions is not the page earning clicks.
- **Page pressure (10%)** — more competing pages means a messier conflict.

Score >= 0.55 is high, >= 0.30 is medium, below that is low. The strongest URL is
picked by clicks, then impressions, then best (lowest) position.

## Output Format

```markdown
## Cannibalization Report
**Source:** ... | **Date:** 2026-06-11 | **Min impressions:** 10

**Conflicts:** 4 (high: 1, medium: 2, low: 1)

### "seo audit checklist"  —  severity: high (0.725)
| URL | Clicks | Impressions | Position | Strongest |
|-----|--------|-------------|----------|-----------|
| /blog/seo-audit-checklist | 120 | 2400 | 6.2 | yes |
| /guides/seo-audit | 110 | 2280 | 7.1 |  |

**Recommendation:** Set canonical to the strongest URL (/blog/seo-audit-checklist) ...
```

The same data is saved as JSON to `data/cannibalization/{YYYY-MM-DD}.json` with the
full per-page metrics, severity scores, and recommendations.

## Cost

- **Detection: 0 NodesHub tokens.** It reads a local GSC export and runs offline.
- **`--verify-serp`: 1 token per cannibalized query.** This is the only feature
  that calls the API, and it skips quietly when no key is configured.

## Parameters

| Param | Description |
|-------|-------------|
| `--file` | Path to a GSC export JSON (default: newest in `knowledge/metrics/seo`) |
| `--demo` | Run on the bundled `sample_gsc.json` fixture |
| `--min-impressions` | Impression floor for a page to count as competing (default: 10) |
| `--verify-serp` | Confirm the live ranking URL via NodesHub (1 token/query) |
| `--gl` | Country code for `--verify-serp` (default: us) |
| `--hl` | Language code for `--verify-serp` (default: en) |
| `--raw` | Print the raw JSON report instead of the table |

## Related Skills

- **nod-rank-tracker** — track positions for the pages you decide to keep.
- **nod-content-auditor** — compare a winning page against the live SERP after consolidation.
- **nod-serp-analysis** — inspect the SERP for a contested query in detail.
