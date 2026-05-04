---
name: nod-rank-tracker
description: |
  Track keyword ranking positions for a domain over time using NodesHub SERPdata API.
  Saves daily snapshots and compares changes. Use when user says "track rankings,"
  "position tracking," "keyword positions," "rank check," "where do I rank,"
  "ranking history," or "SERP position monitoring." Requires NODESHUB_API_KEY.
  Cost: 1 token per keyword checked.
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY, and internet access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Rank Tracker

Track keyword positions for a domain using NodesHub SERPdata API.

## Quick Start

```bash
# Track a single keyword
python3 .claude/skills/nod-rank-tracker/scripts/track.py example.com "seo tools" --gl us --hl en

# Track multiple keywords from a file (one per line)
python3 .claude/skills/nod-rank-tracker/scripts/track.py example.com --file keywords.txt --gl us --hl en

# Compare with previous snapshot
python3 .claude/skills/nod-rank-tracker/scripts/track.py example.com --file keywords.txt --gl us --hl en --compare
```

**Cost:** 1 token per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## Workflow

1. **Get domain and keywords** from user
2. **Check token balance** — each keyword = 1 token
3. **Run tracker** — fetches SERP for each keyword, finds domain position
4. **Save snapshot** to `data/rank-history/{domain}/{YYYY-MM-DD}.json`
5. **Compare with previous** if `--compare` flag or previous data exists
6. **Report results** — positions, changes, not-ranking keywords

## Output Format

```markdown
## Rank Tracker: example.com

**Date:** 2024-01-15 | **Keywords:** 10 | **Tokens used:** 10

### Rankings
| Keyword | Position | Change | URL |
|---------|----------|--------|-----|
| seo tools | #3 | +2 ↑ | /blog/seo-tools |
| keyword research | #7 | -1 ↓ | /tools/keyword |
| rank tracker | — | new | — |

### Summary
- **Ranking:** 8/10 keywords
- **Top 3:** 3 keywords
- **Top 10:** 6 keywords
- **Improved:** 4 | **Declined:** 2 | **Stable:** 2
```

## Data Storage

Snapshots saved to: `data/rank-history/{domain}/{YYYY-MM-DD}.json`

```json
{
  "domain": "example.com",
  "date": "2024-01-15",
  "gl": "us",
  "hl": "en",
  "keywords": {
    "seo tools": {"position": 3, "url": "/blog/seo-tools"},
    "keyword research": {"position": 7, "url": "/tools/keyword"}
  }
}
```

## Parameters

| Param | Description |
|-------|-------------|
| `domain` | Domain to track (required) |
| `keyword` | Single keyword to track |
| `--file` | File with keywords (one per line) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--compare` | Compare with most recent previous snapshot |

## Tips

- **Track weekly, not daily** — saves tokens, rankings don't change hourly
- **Keep keyword lists in files** — easier to maintain and repeat
- **Start with 10-20 keywords** — your most important terms
- **Use with nod-visibility-monitor** for a weighted score view

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

To generate, use `render_report_section(snapshot, previous)` from `track.py`,
then `create_report()` or `append_section()` from `report.py`:
```python
from report import create_report, append_section
section_html = render_report_section(snapshot, previous)
# New report:
path = create_report("Rank Tracker", sections=[section_html])
# Append to existing report:
path = append_section("output/reports/existing-report.html", section_html)
```
Signatures: `create_report(title, sections=None, extra_head="")` and `append_section(report_path, section_html, extra_head="")`.

## Related Skills

- **nod-serp-analysis** — deep dive into SERP for specific keywords
- **nod-visibility-monitor** — weighted visibility score across keywords
- **nod-competitor-tracker** — track competitor positions alongside yours

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior
