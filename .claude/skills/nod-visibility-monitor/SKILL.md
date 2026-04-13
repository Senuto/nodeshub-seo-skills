---
name: nod-visibility-monitor
description: |
  Calculate SEO visibility score for a domain using weighted keyword positions via
  NodesHub SERPdata API. Tracks visibility over time and compares against competitors.
  Use when user says "visibility score," "SEO visibility," "visibility monitor,"
  "visibility index," "how visible am I," "domain visibility," or "visibility trend."
  Requires NODESHUB_API_KEY. Cost: 1 token per keyword.
license: MIT
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY, and internet access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Visibility Monitor

Calculate weighted SEO visibility score using NodesHub SERPdata API.

## Quick Start

```bash
# Check visibility for a domain
python3 .claude/skills/nod-visibility-monitor/scripts/monitor.py example.com --file keywords.txt --gl us --hl en

# Compare with competitors
python3 .claude/skills/nod-visibility-monitor/scripts/monitor.py example.com --file keywords.txt --gl us --hl en --competitors ahrefs.com,semrush.com

# Compare with previous snapshot
python3 .claude/skills/nod-visibility-monitor/scripts/monitor.py example.com --file keywords.txt --gl us --hl en --compare
```

**Cost:** 1 token per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## Scoring System

Visibility score is based on weighted positions:

| Position | Points | Rationale |
|----------|--------|-----------|
| #1 | 10 | ~31% CTR |
| #2 | 9 | ~16% CTR |
| #3 | 8 | ~11% CTR |
| #4-5 | 6 | ~5-8% CTR |
| #6-7 | 4 | ~3-4% CTR |
| #8-10 | 2 | ~1-3% CTR |
| Not in top 10 | 0 | Negligible CTR |

**Max score** = 10 points × number of keywords. **Visibility %** = score / max × 100.

## Workflow

1. **Get domain, keywords, and optional competitors**
2. **Check token balance** — 1 token per keyword
3. **Run monitor** — fetches SERP for each keyword, calculates weighted scores
4. **Save snapshot** to `data/visibility/{domain}/{YYYY-MM-DD}.json`
5. **Compare** — vs previous snapshot and/or competitors
6. **Report** — score, breakdown, trend

## Output Format

```markdown
## Visibility Monitor: example.com

**Date:** 2024-01-15 | **Keywords:** 20 | **Tokens used:** 20

### Visibility Score
**example.com: 68/200 (34.0%)**

### Score Breakdown
| Position Bucket | Keywords | Points |
|----------------|----------|--------|
| #1 | 2 | 20 |
| #2-3 | 3 | 26 |
| #4-5 | 4 | 24 |
| #6-7 | 2 | 8 |
| #8-10 | 3 | 6 |
| Not in top 10 | 6 | 0 |

### Competitor Comparison
| Domain | Score | Visibility % |
|--------|-------|-------------|
| ahrefs.com | 142/200 | 71.0% |
| example.com | 68/200 | 34.0% |
| semrush.com | 58/200 | 29.0% |

### Change (vs previous)
- Score: 68 → from 62 (+6, +9.7%)
- New in top 10: "seo audit" (#5)
- Lost from top 10: "backlink checker"
```

## Data Storage

Snapshots saved to: `data/visibility/{domain}/{YYYY-MM-DD}.json`

```json
{
  "domain": "example.com",
  "date": "2024-01-15",
  "gl": "us",
  "hl": "en",
  "score": 68,
  "max_score": 200,
  "visibility_pct": 34.0,
  "keywords": {
    "seo tools": {"position": 3, "points": 8},
    "keyword research": {"position": 7, "points": 4}
  },
  "competitors": {
    "ahrefs.com": {"score": 142, "visibility_pct": 71.0}
  }
}
```

## Parameters

| Param | Description |
|-------|-------------|
| `domain` | Domain to check (required) |
| `--file` | File with keywords (one per line, required) |
| `--keywords` | Keywords as arguments (alternative to --file) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--competitors` | Comma-separated competitor domains |
| `--compare` | Compare with most recent previous snapshot |

## Tips

- **20-50 keywords is the sweet spot** — representative but affordable
- **Include a mix** — branded, non-branded, head terms, long-tail
- **Run bi-weekly or monthly** — visibility shifts gradually
- **Competitor comparison** gives context — your score alone means less without benchmarks

## Branding

When outputting reports as HTML, use branding from `assets/branding/brand-config.json` (company logo, colors, fonts). Import `from branding import load_brand, render_header, render_footer, brand_css`. Falls back to defaults if not configured. See `assets/branding/README.md`.

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(snapshot)` from `monitor.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-rank-tracker** — detailed position tracking per keyword
- **nod-competitor-tracker** — discover who else ranks for your keywords
- **nod-keyword-research** — find keywords worth tracking

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior
