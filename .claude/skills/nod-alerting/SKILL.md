---
name: nod-alerting
description: |
  Turns one-off SEO snapshots into monitoring. Compares the two newest snapshots
  from rank-tracker, visibility-monitor, or the merger and raises alerts when
  rankings, visibility, or traffic move past a threshold — drops and gains both.
  No new data is fetched and no model judgment is used, so the same two snapshots
  always produce the same alerts. Use when user says "alert," "what dropped,"
  "ranking drops," "traffic drop alert," "monitor changes," "what changed since
  last time," or "alerting." Reads existing snapshots; 0 NodesHub tokens.
compatibility: "Requires Python 3.9+. Reads existing snapshots (rank-history / visibility / merged). No NodesHub key needed."
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Alerting

Monitoring on top of the snapshots other skills already write. Alerting finds the
two newest snapshots for a source, diffs them, and reports only the changes that
cross a threshold — grouped by severity. It never calls the API and never invents
data: if a source has fewer than two snapshots, it says so and stops.

## First action

Run the banner before anything else (CLAUDE.md rule):

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Alerting')"
```

## Setup

No NodesHub key is needed. Alerting reads snapshots that other skills save. You
need **at least two snapshots** of the same source before it can compare:

- **nod-rank-tracker** -> `data/rank-history/{domain}/{date}.json`
- **nod-visibility-monitor** -> `data/visibility/{domain}/{date}.json`
- **nod-merger** -> `data/merged/{date}.json`

Run one of those skills on two different days (or two merges), then run alerting.
Use `--demo` to see the format before you have real history.

## Quick Start

```bash
# Auto-detect a source with >= 2 snapshots (prefers merged)
python3 .claude/skills/nod-alerting/scripts/alert.py

# Compare rank-tracker snapshots for one domain
python3 .claude/skills/nod-alerting/scripts/alert.py --source rank --domain example.com

# Compare visibility snapshots
python3 .claude/skills/nod-alerting/scripts/alert.py --source visibility --domain example.com

# Compare merged funnel snapshots (traffic + average position)
python3 .claude/skills/nod-alerting/scripts/alert.py --source merged

# See it now on bundled snapshots (drops + gains)
python3 .claude/skills/nod-alerting/scripts/alert.py --demo
```

## Workflow

1. **Pick the source** — `--source rank|visibility|merged`, or let it auto-detect
   (it prefers `merged`, then `rank`, then `visibility`).
2. **Find the two newest snapshots** for that source (and `--domain` where the
   path is domain-scoped). Fewer than two? It prints a clear "need at least two
   snapshots" message and exits cleanly — nothing is fabricated.
3. **Diff them**, keyed appropriately: keyword for rank/visibility, url and query
   for merged.
4. **Raise alerts** only where a change crosses a threshold.
5. **Group by severity** (critical / warning / info) and save to
   `data/alerts/{YYYY-MM-DD}.json`.

## What triggers an alert

- **Rank drop** (`rank`): a keyword's position worsens by >= `--rank-threshold`
  (default 3), or it was in the top 10 and is now absent (lost ranking). Big
  gains and recoveries surface as info.
- **Traffic drop** (`merged`): clicks fall by >= `--drop-pct` (default 25%) on a
  URL or query that had at least `--min-clicks` prior clicks (default 20). Clicks
  going to zero is critical; large gains surface as info. Merged also flags
  average-position moves of 3+ on `by_query`.
- **Visibility change** (`visibility`): the overall score moves beyond
  `--vis-threshold` points (default 5), plus per-keyword top-10 entries/exits.

### Severity

- **critical** — lost a top-3 ranking, dropped out of the top 10, clicks to zero,
  a 50%+ traffic fall, or a visibility drop of twice the threshold.
- **warning** — a smaller-but-meaningful drop that still cleared the threshold.
- **info** — gains and recoveries (climbed positions, new rankings, traffic up).

## Thresholds

| Param | Default | Meaning |
|-------|---------|---------|
| `--rank-threshold` | 3 | Positions a keyword must move to alert |
| `--drop-pct` | 25 | Percent click change for a merged traffic alert |
| `--vis-threshold` | 5 | Visibility-point change to alert |
| `--min-clicks` | 20 | Minimum prior clicks for a merged traffic alert |

Other flags: `--source`, `--domain`, `--demo`, `--raw`.

## Output

A report grouped by severity, each alert carrying the entity, `before -> after`,
and the delta. When nothing crosses a threshold it prints a clear "no significant
changes" line. Saved to `data/alerts/{YYYY-MM-DD}.json`.

```markdown
## Alerting Report
**Source:** merged | **Date:** 2026-06-11 | **Compared:** 2026-06-01 -> 2026-06-08

**Alerts:** 5 (critical: 2, warning: 1, info: 2)

### Critical (2)
| Entity | Change | Delta | Detail |
|--------|--------|-------|--------|
| /blog/old-post | 120 -> 0 | -120 | URL /blog/old-post lost all clicks (120 -> 0). |
| best seo tool | 300 -> 120 | -60.0 | Query best seo tool clicks fell 60.0% (300 -> 120). |
```

## Cost

**0 NodesHub tokens.** Alerting only reads snapshots already on disk and runs
fully offline.

## Schedule it (real monitoring)

For continuous monitoring, run the fetch skill and alerting on a schedule, e.g. a
daily cron: `0 7 * * * cd /path/to/repo && python3 .claude/skills/nod-alerting/scripts/alert.py --source merged`.

## Related Skills

- **nod-rank-tracker** — produces the rank snapshots this skill diffs.
- **nod-visibility-monitor** — produces the visibility snapshots.
- **nod-merger** — produces the merged funnel snapshots (traffic + position).
