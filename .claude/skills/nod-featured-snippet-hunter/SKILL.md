---
name: nod-featured-snippet-hunter
description: |
  Find Featured Snippet and Answer Box opportunities by analyzing Google SERPs using
  NodesHub SERPdata API. For a domain + keyword list, identifies where you can steal
  snippets (ranking in TOP 10 but not owning the snippet), defend existing snippets,
  or target new ones. Use when user says "featured snippet," "answer box," "position
  zero," "snippet opportunities," "snippet hunter," "win snippets," or "steal snippet."
  Requires NODESHUB_API_KEY. Cost: 1 token per keyword.
license: MIT
compatibility: Requires Python 3.9+, NODESHUB_API_KEY, and internet access
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Featured Snippet Hunter

Find Featured Snippet / Answer Box opportunities for your domain.

## Quick Start

```bash
# Single keyword
python3 .claude/skills/nod-featured-snippet-hunter/scripts/hunt.py --domain example.com "seo tools" --gl us --hl en

# Multiple keywords
python3 .claude/skills/nod-featured-snippet-hunter/scripts/hunt.py --domain example.com "seo tools" "keyword research" --gl us --hl en

# From file
python3 .claude/skills/nod-featured-snippet-hunter/scripts/hunt.py --domain example.com --file keywords.txt --gl us --hl en

# Raw JSON
python3 .claude/skills/nod-featured-snippet-hunter/scripts/hunt.py --domain example.com "seo tools" --gl us --hl en --raw
```

**Cost:** 1 token per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## How It Works

For each keyword:
1. Fetches SERP via NodesHub `/search` endpoint
2. Checks `snippets.answer_box` for Featured Snippet presence
3. Identifies snippet owner domain and type (paragraph/list/table)
4. Finds your domain's position in organic results
5. Classifies opportunity:
   - **Steal** — snippet exists, you're in TOP 10 but don't own it (best opportunity)
   - **Defend** — you own the snippet (monitor it)
   - **Target** — snippet exists, you're outside TOP 10 or not ranking (harder)
   - **No snippet** — no answer box present

## Output Format

```markdown
## Featured Snippet Opportunities for example.com

**Keywords analyzed:** 15 | **Tokens used:** 15
**Opportunities:** 8 steal, 2 defend, 3 target, 2 no snippet

### Steal (you rank but don't own the snippet)
| Keyword | Your Pos | Snippet Owner | Type |
|---------|:--------:|---------------|:----:|
| seo tools | #4 | ahrefs.com | paragraph |
| keyword research | #7 | moz.com | list |

### Defend (you own the snippet)
| Keyword | Your Pos | Type |
|---------|:--------:|:----:|
| seo audit | #1 | paragraph |

### Target (snippet exists, you're not in TOP 10)
| Keyword | Snippet Owner | Type | Your Pos |
|---------|---------------|:----:|:--------:|
| link building | backlinko.com | list | #15 |

### No Snippet
- keyword1, keyword2

### Recommendations
1. Focus on "steal" keywords first
2. For paragraph snippets: add concise 40-60 word definitions
3. For list snippets: structure content with ordered/unordered lists
4. For table snippets: add comparison tables
```

## Workflow

1. **Get domain + keywords** from user
2. **Check token balance** — 1 token per keyword
3. **Fetch SERPs** — batch with progress
4. **Classify opportunities** — steal/defend/target/no snippet
5. **Report** — sorted by opportunity type with recommendations

## Parameters

| Param | Description |
|-------|-------------|
| `keywords` | Keywords to check (positional) |
| `--domain` | Your domain to check (required) |
| `--file` | File with keywords (one per line) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--raw` | Output raw JSON |

## Tips

- **Focus on "steal" keywords** — you already rank, just need snippet-optimized content
- **Paragraph snippets** are easiest to win — add a clear, concise definition paragraph
- **List snippets** need structured content — use H2/H3 with bullet points
- **Table snippets** need comparison data — add HTML or markdown tables
- **Check mobile vs desktop** — snippets differ between devices
- **Combine with nod-rank-tracker** — track snippet ownership changes over time

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section({"domain": domain, "results": all_results})` from `hunt.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-serp-analysis** — deep SERP analysis for specific keywords
- **nod-rank-tracker** — track position changes over time
- **nod-content-brief** — create briefs optimized for snippet capture
