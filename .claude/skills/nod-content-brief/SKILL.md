---
name: nod-content-brief
description: |
  Generates data-driven SEO content briefs using NodesHub SERPdata and Query Fan-out APIs.
  Combines SERP analysis (top 10 competitors, SERP features, intent) with keyword expansion
  (related queries, questions) into a ready-to-write content brief with suggested structure,
  headings, and target keywords. Use when the user mentions "content brief," "writing brief,"
  "article brief," "create brief for keyword," "brief for content," "what to write
  about," or "content outline." Requires NODESHUB_API_KEY. For keyword research only see
  nod-keyword-research. For SERP analysis only see nod-serp-analysis.
license: MIT
compatibility: Requires Python 3.9+, NODESHUB_API_KEY, and internet access
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Content Brief

You generate comprehensive, data-driven content briefs by combining NodesHub SERPdata (competitor analysis), Query Fan-out (keyword expansion), and **Jina Reader** (competitor content crawling) APIs.

## Quick Start

```bash
# Generate research data for a brief
python3 .claude/skills/nod-content-brief/scripts/research.py "target keyword" --gl us --hl en

# With reasoning mode for deeper keyword expansion
python3 .claude/skills/nod-content-brief/scripts/research.py "target keyword" --gl us --hl en --mode reasoning
```

**Cost:** ~8.5 tokens (standard) or ~31 tokens (reasoning) per brief = 1 SERPdata + 1 Fan-out.

## Setup

Requires `NODESHUB_API_KEY`. Optional: `JINA_API_KEY` for competitor content crawling.

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

### Jina Reader (competitor crawling)

Jina Reader fetches competitor page content as clean markdown. Used to analyze what top-ranking pages actually contain.

```bash
# API: https://r.jina.ai/{URL}
# Key stored in .claude/settings.local.json under env.JINA_API_KEY
# Free tier: 20 RPM without key, 200 RPM with key (10M free tokens)
```

**Graceful degradation:** If Jina is unavailable, brief generation still works — just without competitor content analysis.

## Workflow: Generate Content Brief

1. **Clarify target** — keyword, target audience, content goal
2. **Run research script** — fetches SERP + keyword expansion in one call
3. **Crawl competitor content** — use Jina Reader to fetch top 3-5 competitor pages as markdown
4. **Analyze SERP competition** — what ranks, what content types, what's missing
5. **Map keyword opportunities** — related queries, questions, long-tail
6. **Determine intent** — match content format to dominant search intent
7. **Generate brief** — structured brief using output template
8. **Present to user** — with clear recommendations and alternatives

### Crawling competitors with Jina Reader

After getting SERP results, crawl top competitor URLs to analyze their actual content:

```bash
# Jina Reader API — URL to clean markdown
curl "https://r.jina.ai/{COMPETITOR_URL}" \
  -H "Authorization: Bearer $JINA_API_KEY" \
  -H "X-Return-Format: markdown"
```

Use the crawled content to:
- Identify what topics competitors cover (content gaps)
- Extract heading structures (H2/H3 patterns)
- Estimate word counts and content depth
- Find unique angles competitors miss

## Research Script Output

The `research.py` script returns combined data:

```json
{
  "keyword": "...",
  "serp": {
    "organic_results": [...],
    "serp_features": [...],
    "dominant_intent": "...",
    "domains": [...]
  },
  "fanout": {
    "related_queries": [...],
    "questions": [...],
    "topic_leaders": [...]
  },
  "tokens_used": 8.5
}
```

## Brief Components

### 1. Target Keyword & Intent

- Primary keyword and intent classification
- Secondary keywords (from Fan-out)
- Questions to answer (from Fan-out + PAA)

### 2. SERP Landscape

- Who ranks and what content type dominates
- SERP features present (opportunities)
- Content gaps in current results

### 3. Suggested Structure

Based on top-ranking content patterns:

| Dominant Type | Suggested Structure |
|---------------|-------------------|
| How-to guides | Step-by-step with H2 per step |
| Listicles | Numbered items with H2 per item |
| In-depth guides | Topical sections with H2/H3 hierarchy |
| Comparisons | Feature-by-feature with tables |
| Product pages | Benefits → Features → Social proof → CTA |

### 4. Heading Suggestions

Derive from:
- Top-ranking titles → H1 inspiration
- PAA questions → H2 candidates
- Fan-out queries → H2/H3 subtopics
- Related searches → additional sections

### 5. Content Requirements

- Estimated word count (based on competitor average)
- Must-cover topics (present in all top results)
- Differentiation angle (gap in current results)
- Internal linking opportunities

## Output Format

```markdown
## Content Brief: [Primary Keyword]

**Target:** [keyword] | **Intent:** [type] | **Difficulty:** [easy/medium/hard]
**Audience:** [who this content is for]

### Search Landscape
- **Total results:** [X]
- **SERP features:** [list]
- **Dominant content type:** [guide/listicle/comparison/...]
- **Top domains:** [domain1, domain2, domain3]

### Target Keywords
**Primary:** [keyword]
**Secondary:**
- [keyword 2]
- [keyword 3]

**Questions to Answer:**
- [question 1 — from PAA/Fan-out]
- [question 2]
- [question 3]

### Competitor Analysis (Top 5)
| # | Title | Domain | Strengths | Gaps |
|---|-------|--------|-----------|------|
| 1 | ... | ... | ... | ... |

### Suggested Structure
**H1:** [suggested title]

**H2:** [section 1 — from top patterns]
- Key points to cover

**H2:** [section 2 — from PAA]
- Key points to cover

**H2:** [section 3 — from Fan-out]
- Key points to cover

**H2:** FAQ
- [question 1]
- [question 2]

### Content Requirements
- **Word count:** [X-Y words] (competitor average: [Z])
- **Must include:** [topics present in all top results]
- **Differentiation:** [what's missing from current results]
- **Media:** [images/video/tables/infographics needed]
- **Internal links:** [suggest pages to link to/from]

### SEO Checklist
- [ ] Primary keyword in H1, first paragraph, URL
- [ ] Secondary keywords naturally distributed
- [ ] All PAA questions addressed
- [ ] Schema markup: [Article/FAQ/HowTo]
- [ ] Meta title: [suggestion, <60 chars]
- [ ] Meta description: [suggestion, <160 chars]
```

## Token Budget

| Brief Type | Mode | Tokens | Use Case |
|------------|------|--------|----------|
| Quick brief | standard | 8.5 | Blog posts, quick content |
| Deep brief | reasoning | 31 | Pillar content, high-value pages |
| Batch (5 briefs) | standard | 42.5 | Content calendar planning |

## Tips

- **Always check balance first** — briefs use both APIs
- **Standard mode is usually enough** — save reasoning for pillar content
- **Combine with nod-keyword-research** for editorial calendar context
- **Use the competitor gaps** as your primary differentiation angle
- **PAA questions make great H2s** — Google literally tells you what users want

## Branding

When outputting briefs as HTML, use branding from `assets/branding/brand-config.json` (company logo, colors, fonts). Import `from branding import load_brand, render_header, render_footer, brand_css`. Falls back to defaults if not configured. See `assets/branding/README.md`.

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(result_data)` from `research.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-serp-analysis** — deeper SERP analysis for individual keywords
- **nod-keyword-research** — broader keyword expansion and clustering

- Token-efficient research workflows

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries into single proven patterns
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior - if obvious, cut it
