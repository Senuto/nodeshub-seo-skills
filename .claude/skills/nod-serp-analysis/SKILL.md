---
name: nod-serp-analysis
description: |
  Analyze Google SERP for any keyword using NodesHub SERPdata API. Extracts organic
  results, SERP features (PAA, AI Overview, Knowledge Panel, Local Pack, Videos),
  competitor domains, content gaps, and dominant search intent. Use when user says
  "analyze SERP," "who ranks for," "SERP features," "check competition," "what's
  ranking for," "SERP overview," "search results analysis," or "top 10 for keyword."
  Requires NODESHUB_API_KEY. For keyword expansion see nod-keyword-research. For full
  SEO audit see nod-content-auditor.
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY, and internet access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# SERP Analysis

You analyze Google search results using NodesHub SERPdata API to provide actionable SEO intelligence.

## Quick Start

```bash
# Single keyword analysis
python3 .claude/skills/nod-nodeshub-api/scripts/serpdata.py "keyword" --gl us --hl en

# Raw JSON for deeper analysis
python3 .claude/skills/nod-nodeshub-api/scripts/serpdata.py "keyword" --gl us --hl en --raw
```

**Cost:** 1 token per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY` in environment. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```
If missing, see [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md).

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## Input

Before running, always ask the user for:
1. **Keyword** — what to analyze
2. **Market** — country code `--gl` and language `--hl` (e.g. `pl/pl`, `us/en`)
3. **Device** — `desktop` (default) or `mobile`? SERP features and layouts differ significantly between devices.

## Workflow: Single Keyword SERP Analysis

1. **Fetch SERP data** — run `serpdata.py` with `--raw` flag
2. **Analyze organic results** — who ranks, what content types dominate
3. **Map SERP features** — which features appear, what they reveal about intent
4. **Assess competition** — domain authority signals, content depth
5. **Identify opportunities** — gaps in existing results, underserved angles
6. **Deliver report** — structured analysis with actionable recommendations

## Workflow: Multi-Keyword SERP Comparison

1. **Fetch SERP for each keyword** (batch — mind token budget)
2. **Cross-reference domains** — who ranks across multiple keywords
3. **Compare SERP features** — how feature presence varies by keyword
4. **Identify keyword clusters** — keywords with overlapping SERPs = same intent
5. **Prioritize targets** — rank keywords by opportunity score

## Analysis Framework

### Organic Results Analysis

For each result in top 10, extract:
- **Domain** — who's ranking (brand vs. niche vs. aggregator)
- **Title patterns** — what title structures Google prefers
- **URL structure** — subfolder vs. subdomain, URL depth
- **Content type** — blog, product page, listicle, guide, tool, forum

### SERP Features Mapping

| Feature | What it reveals |
|---------|----------------|
| **People Also Ask** | Related questions users have — content expansion opportunities |
| **AI Overview** | Google's AI summary — what content gets cited |
| **Knowledge Panel** | Entity recognition — brand/topic authority signals |
| **Local Pack** | Local intent — needs local SEO strategy |
| **Videos** | Video intent — YouTube/video content opportunity |
| **Top Stories** | News intent — freshness matters |
| **Related Searches** | Semantic connections — keyword expansion ideas |
| **Featured Snippet** | Direct answer opportunity — structure content for position 0 |

### Intent Classification (from SERP signals)

Classify based on what you see:
- **Informational** — PAA, Knowledge Panel, long-form content dominate
- **Commercial** — Product comparisons, reviews, "best X" in titles
- **Transactional** — Shopping results, product pages, pricing in titles
- **Navigational** — Brand dominates, official site in #1

### Competition Assessment

Rate difficulty based on:
- **Domain types** — all big brands = hard; niche sites ranking = opportunity
- **Content quality** — thin results = easy to outrank; deep guides = harder
- **SERP volatility** — many SERP features = more entry points
- **Content freshness** — old dates = opportunity for fresh content

## Output Format

```markdown
## SERP Analysis: [keyword]

**Settings:** gl=[country], hl=[language], device=[device]
**Total results:** [count]

### Dominant Intent
[informational/commercial/transactional/navigational] — [evidence]

### SERP Features Present
- [Feature]: [insight]

### Top 10 Organic Results
| # | Domain | Title | Type | Notes |
|---|--------|-------|------|-------|
| 1 | ... | ... | ... | ... |

### Domain Distribution
- [domain.com]: positions [X, Y] — [pattern]

### Content Patterns
- Dominant format: [listicle/guide/tool/...]
- Average title length: [X chars]
- Title patterns: [common structures]

### Opportunities
1. [Gap or angle not covered by current results]
2. [SERP feature not being targeted]
3. [Content type missing from results]

### Recommendations
1. [Specific, actionable recommendation]
2. [...]
```

## Parameters Reference

| Param | Values | Notes |
|-------|--------|-------|
| `--gl` | us, pl, de, uk, fr, es... | Country — affects local results |
| `--hl` | en, pl, de, fr, es... | Language — affects interface/results language |
| `--device` | desktop, mobile | Different SERP layouts and features |

For full country/language list: `python3 .claude/skills/nod-nodeshub-api/scripts/params.py countries`

## Tips

- **Always use `--raw`** for full analysis — the pretty output is just a preview
- **Compare desktop vs mobile** — SERP features differ significantly
- **Check different countries** — local competition varies
- **Mind token budget** — each call = 1 token. For 20 keywords = 20 tokens
- **Parse `snippets_data`** carefully — SERP features are the richest insight source

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

To generate, use the `render_report_section(data)` function from this skill's script,
then `create_report()` or `append_section()` from `report.py`:
```python
from report import create_report, append_section
section_html = render_report_section(analysis_data)
# New report:
path = create_report("SERP Analysis", sections=[section_html])
# Or append to existing:
path = append_section("reports/existing.html", section_html)
```

## Related Skills

- **nod-keyword-research** — expand keywords before analyzing SERPs
- **nod-content-brief** — turn SERP analysis into content brief

- API response quirks or undocumented fields

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries into single proven patterns
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior - if obvious, cut it
