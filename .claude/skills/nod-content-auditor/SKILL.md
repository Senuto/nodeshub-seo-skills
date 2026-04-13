---
name: nod-content-auditor
description: |
  Audit existing content against current SERP reality using NodesHub SERPdata,
  Query Fan-out APIs, and Jina Reader for competitor page crawling. Identifies
  content gaps, missing keywords, and optimization opportunities by comparing
  your page against crawled competitor content. Use when user says "content audit,"
  "audit my content," "content gaps," "content optimization," "is my content
  competitive," "what am I missing," or "content refresh."
  Requires NODESHUB_API_KEY. Optional: JINA_API_KEY (works without, 20 RPM limit).
  Cost: ~8.5 NodesHub tokens (standard) per audit + Jina Reader (free tier).
license: MIT
compatibility: Requires Python 3.9+, NODESHUB_API_KEY, and internet access. Optional: JINA_API_KEY
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Content Auditor

Audit content against current SERP and keyword data using NodesHub APIs + Jina Reader for real competitor content crawling.

## Quick Start

```bash
# Audit content for a keyword (crawls top 5 competitors)
python3 .claude/skills/nod-content-auditor/scripts/audit.py "target keyword" --gl us --hl en

# Audit YOUR page vs competitors
python3 .claude/skills/nod-content-auditor/scripts/audit.py "target keyword" --gl us --hl en --url https://example.com/page

# Crawl more competitors (top 10)
python3 .claude/skills/nod-content-auditor/scripts/audit.py "target keyword" --gl us --hl en --top 10

# SERP-only mode (no crawling, like before)
python3 .claude/skills/nod-content-auditor/scripts/audit.py "target keyword" --gl us --hl en --no-crawl
```

**Cost:** ~8.5 NodesHub tokens (standard) or ~31 (reasoning). Jina Reader is free (20 RPM without key, 200 RPM with key).

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**Optional:** `JINA_API_KEY` for higher rate limits. Without it, Jina works at 20 RPM (enough for 5-10 pages). Get a free key at [jina.ai](https://jina.ai/reader/) for 200 RPM + 10M free tokens.

Save Jina key: add `"JINA_API_KEY": "jina_xxx"` to `env` in `.claude/settings.local.json`.

## How It Works

1. **SERP data** — fetches top 10 organic results via NodesHub SERPdata
2. **Keyword expansion** — related queries + questions via Query Fan-out
3. **Competitor crawling** — fetches actual page content of top N results via Jina Reader (`r.jina.ai`)
4. **Your page crawling** — fetches your URL content if `--url` provided
5. **Content gap analysis** — compares keyword/topic coverage between your page and competitors
6. **Recommendations** — prioritized list based on real competitor data

## Output Sections

- **SERP Reality** — dominant content type, SERP features, top domains
- **Top 10 Results** — positions, titles, domains, crawl status
- **Keyword Coverage** — which keywords competitors use, whether your page has them, priority
- **Questions to Answer** — PAA + fan-out questions with competitor coverage
- **Content Gaps** — topics competitors cover that your page misses (only with `--url`)
- **Common Heading Patterns** — H2/H3 structures used by multiple competitors
- **Audit Summary** — avg competitor length, critical gaps count, missing must-haves

## Parameters

| Param | Description |
|-------|-------------|
| `keyword` | Target keyword to audit against (required) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--mode` | standard (8.5 tokens) or reasoning (31 tokens) |
| `--url` | URL of your page to audit — enables gap comparison |
| `--top` | Number of top SERP results to crawl (default: 5) |
| `--no-crawl` | Skip Jina crawling, SERP-only mode |
| `--raw` | Output raw JSON |

## Tips

- **Always provide `--url`** when you have existing content — this unlocks the real gap analysis
- **`--top 5` is usually enough** — more pages = more time but marginal gains
- **Without Jina key** the script works fine for 5 pages (20 RPM = ~3s between pages)
- **`--no-crawl`** is useful for quick checks or when Jina is unavailable
- **Content gaps are word-level** — Claude should interpret and group them into actionable topics
- **Combine with nod-content-brief** when gaps require new content, not updates

## Jina Reader Module

The shared `jina_reader.py` module lives in `nod-nodeshub-api/scripts/` and can be reused by other skills:

```python
from jina_reader import JinaReader
reader = JinaReader()  # auto-loads JINA_API_KEY if available
result = reader.fetch("https://example.com")  # → {url, title, content, word_count, ok}
results = reader.fetch_batch(["url1", "url2"], max_workers=3)
```

## Branding

When generating HTML audit reports, use the branding assets from `assets/branding/`:
- `brand-config.json` — company name, colors, fonts for report styling
- `logo-light.svg` / `logo-dark.svg` — company logo in report header

```python
from branding import load_brand, render_header, render_footer, brand_css
brand = load_brand()
```

If no branding is configured, default styling is used. See `assets/branding/README.md` for setup.

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(result_data)` from `audit.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-content-brief** — generate brief for new content
- **nod-serp-analysis** — deeper SERP analysis without keyword expansion
- **nod-keyword-research** — broader keyword research
