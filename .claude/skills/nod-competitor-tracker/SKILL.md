---
name: nod-competitor-tracker
description: |
  Track competitor domains across keyword sets using NodesHub SERPdata API.
  Identifies who ranks for your target keywords and how positions change over time.
  Use when user says "track competitors," "competitor rankings," "who ranks for,"
  "competitor monitoring," "competitive analysis," or "competitor positions."
  Requires NODESHUB_API_KEY. Cost: 1 token per keyword checked.
compatibility: Requires Python 3.9+, NODESHUB_API_KEY, and internet access
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Competitor Tracker

Track competitor domains across keyword sets using NodesHub SERPdata API.

## Quick Start

```bash
# Track competitors for keywords
python3 .claude/skills/nod-competitor-tracker/scripts/track.py "seo tools" "keyword research" --gl us --hl en

# Track from keyword file, watching specific domains
python3 .claude/skills/nod-competitor-tracker/scripts/track.py --file keywords.txt --gl us --hl en --watch ahrefs.com,semrush.com,moz.com

# Compare with previous snapshot
python3 .claude/skills/nod-competitor-tracker/scripts/track.py --file keywords.txt --gl us --hl en --compare
```

**Cost:** 1 token per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## Workflow

1. **Get keywords and competitor domains** from user
2. **Check token balance** — each keyword = 1 token
3. **Run tracker** — fetches SERP for each keyword, extracts all domains in top 10
4. **Save snapshot** to `data/competitor-tracking/{YYYY-MM-DD}.json`
5. **Compare with previous** if `--compare` flag
6. **Report results** — domain frequency, positions, changes

## Output Format

```markdown
## Competitor Tracker

**Date:** 2024-01-15 | **Keywords:** 10 | **Tokens used:** 10

### Domain Frequency (Top 10 across all keywords)
| Domain | Keywords in Top 10 | Avg Position |
|--------|-------------------|--------------|
| ahrefs.com | 8/10 | 2.3 |
| semrush.com | 7/10 | 3.8 |
| moz.com | 5/10 | 5.2 |

### Keyword × Domain Matrix
| Keyword | ahrefs.com | semrush.com | moz.com |
|---------|-----------|------------|---------|
| seo tools | #1 | #3 | #5 |
| keyword research | #2 | #4 | — |

### Changes (vs previous)
- ahrefs.com: +2 new keywords in top 10
- semrush.com: lost "rank tracker" (was #4, now #12)
```

## Data Storage

Snapshots saved to: `data/competitor-tracking/{YYYY-MM-DD}.json`

```json
{
  "date": "2024-01-15",
  "gl": "us",
  "hl": "en",
  "keywords": {
    "seo tools": {
      "top_10": [
        {"position": 1, "domain": "ahrefs.com", "url": "..."},
        {"position": 2, "domain": "semrush.com", "url": "..."}
      ]
    }
  },
  "watched_domains": ["ahrefs.com", "semrush.com"]
}
```

## Parameters

| Param | Description |
|-------|-------------|
| `keywords` | Keywords to track (positional, space-separated) |
| `--file` | File with keywords (one per line) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--watch` | Comma-separated domains to highlight |
| `--compare` | Compare with most recent previous snapshot |

## Tips

- **Use `--watch` for your direct competitors** — highlights them in results
- **Without `--watch`** the tool shows all domains found — good for discovery
- **Combine with nod-rank-tracker** — track your own positions alongside competitors
- **Run monthly** for strategic overview, weekly for active campaigns

## Branding

When outputting reports as HTML, use branding from `assets/branding/brand-config.json` (company logo, colors, fonts). Import `from branding import load_brand, render_header, render_footer, brand_css`. Falls back to defaults if not configured. See `assets/branding/README.md`.

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(data)` from `track.py`, then `create_report()` or `append_section()` from `report.py`:
```python
from report import create_report, append_section
section_html = render_report_section(data)
# New report:
path = create_report("Competitor Tracker", sections=[section_html])
# Append to existing report:
path = append_section("output/reports/existing-report.html", section_html)
```
Signatures: `create_report(title, sections=None, extra_head="")` and `append_section(report_path, section_html, extra_head="")`.

## Related Skills

- **nod-rank-tracker** — track your own domain positions
- **nod-visibility-monitor** — weighted visibility comparison
- **nod-serp-analysis** — deep SERP analysis for individual keywords

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior
