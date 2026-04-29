---
name: nod-paa-miner
description: |
  Mine "People Also Ask" questions from Google SERPs for a list of keywords using
  NodesHub SERPdata API. Deduplicates questions, optionally clusters them by topic
  via OpenRouter LLM. Outputs a structured question bank for FAQ and content creation.
  Use when user says "PAA," "people also ask," "mine questions," "extract questions,"
  "FAQ questions," "question bank," "PAA mining," or "SERP questions."
  Requires NODESHUB_API_KEY. Cost: 1 token per keyword + optional OpenRouter for clustering.
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY, and internet access. Optional: OPENROUTER_API_KEY for clustering"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# PAA Miner

Mine "People Also Ask" questions from Google SERPs to build a question bank for content and FAQ.

## Quick Start

```bash
# Single keyword
python3 .claude/skills/nod-paa-miner/scripts/mine.py "seo tools" --gl us --hl en

# Multiple keywords
python3 .claude/skills/nod-paa-miner/scripts/mine.py "seo tools" "keyword research" "link building" --gl us --hl en

# From file
python3 .claude/skills/nod-paa-miner/scripts/mine.py --file keywords.txt --gl us --hl en

# With topic clustering (requires OPENROUTER_API_KEY)
python3 .claude/skills/nod-paa-miner/scripts/mine.py --file keywords.txt --gl us --hl en --cluster

# Raw JSON
python3 .claude/skills/nod-paa-miner/scripts/mine.py "seo tools" --gl us --hl en --raw
```

**Cost:** 1 token per keyword (SERPdata) + small OpenRouter cost if --cluster used.
Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** run `/connect-nodeshub` for step-by-step setup.

For clustering (`--cluster`), also needs `OPENROUTER_API_KEY`. **If not set up:** run `/connect-openrouter`.

## How It Works

1. Fetches SERP for each keyword via NodesHub `/search` endpoint
2. Extracts PAA questions from `snippets.people_also_ask`
3. Also extracts questions from `snippets.answer_box` if present
4. Deduplicates questions (case-insensitive)
5. Tracks which keywords each question appeared for
6. Optionally clusters questions by topic via OpenRouter LLM

## Output Format

### Flat (default)
```markdown
## PAA Questions Mined

**Keywords analyzed:** 5 | **Tokens used:** 5 | **Unique questions:** 23

| # | Question | Found for |
|---|----------|-----------|
| 1 | How does SEO work? | seo tools, keyword research |
| 2 | What is the best SEO tool? | seo tools |

### Source Distribution
- seo tools: 8 questions
- keyword research: 6 questions
```

### Clustered (--cluster)
```markdown
## PAA Questions Mined (Clustered)

**Keywords:** 5 | **Tokens:** 5 | **Questions:** 23 | **Clusters:** 5

### Getting Started
- How does SEO work?
- What is SEO?

### Tools & Software
- What is the best SEO tool?
- Is Ahrefs free?
```

## Workflow

1. **Get keywords** from user (direct or file)
2. **Check token balance** — 1 token per keyword
3. **Fetch SERPs** — batch processing with progress
4. **Extract & deduplicate** PAA questions
5. **Optionally cluster** via LLM
6. **Report results** — structured question bank

## Parameters

| Param | Description |
|-------|-------------|
| `keywords` | Keywords to mine (positional, space-separated) |
| `--file` | File with keywords (one per line) |
| `--gl` | Country code (default: us) |
| `--hl` | Language code (default: en) |
| `--cluster` | Cluster questions by topic via OpenRouter |
| `--raw` | Output raw JSON |

## Tips

- **More keywords = more questions** — PAA varies per keyword, so broad coverage yields richer results
- **Use keyword clusters** — related keywords surface different PAA angles
- **Combine with nod-keyword-research** — expand seeds first, then mine PAA
- **Use --cluster for large sets** — 20+ questions benefit from topic grouping
- **Export for content planning** — pipe to file: `... > paa_questions.md`

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(output_data)` from `mine.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-keyword-research** — expand keywords before mining PAA
- **nod-serp-analysis** — deep SERP dive including PAA context
- **nod-content-brief** — turn PAA questions into content structure
