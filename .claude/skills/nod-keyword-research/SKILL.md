---
name: nod-keyword-research
description: |
  Expand seed keywords into comprehensive keyword lists using NodesHub Query Fan-out API.
  Generates related queries, questions, long-tail variations, and topic clusters.
  Use when user says "keyword research," "find keywords," "expand keywords," "related
  queries," "keyword ideas," "long-tail keywords," "keyword clustering," "topical map,"
  "what do people search for," or "keyword expansion." Requires NODESHUB_API_KEY.
  For analyzing search results see nod-serp-analysis. For content planning see nod-content-brief.
compatibility: Requires Python 3.9+, NODESHUB_API_KEY, and internet access
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Keyword Research

You expand seed keywords into comprehensive, clustered keyword lists using NodesHub Query Fan-out API **and** iterative SERP mining (PAA + Related Searches loops).

## Quick Start

```bash
# === Iterative Research (recommended) ===
# Uses SERP PAA + Related Searches in loops for deep keyword discovery

# Standard (5 loops, ~57 tokens max)
python3 .claude/skills/nod-keyword-research/scripts/iterative_research.py "SEO" --gl pl --hl pl --preset standard

# Aggressive (15 loops, ~232 tokens max)
python3 .claude/skills/nod-keyword-research/scripts/iterative_research.py "SEO" --gl pl --hl pl --preset aggressive

# Beast mode (30 loops, ~637 tokens max)
python3 .claude/skills/nod-keyword-research/scripts/iterative_research.py "SEO" --gl pl --hl pl --preset beast

# Custom loops + budget cap
python3 .claude/skills/nod-keyword-research/scripts/iterative_research.py "SEO" --gl pl --hl pl --loops 10 --serp-per-loop 8 --budget 200

# With JSON output
python3 .claude/skills/nod-keyword-research/scripts/iterative_research.py "SEO" --gl pl --hl pl --preset standard --json

# === Simple Fan-out (single pass) ===
python3 .claude/skills/nod-nodeshub-api/scripts/fanout.py "seed keyword" --hl en --mode standard
python3 .claude/skills/nod-nodeshub-api/scripts/fanout.py "seed keyword" --hl en --mode standard --questions --topic-leaders --raw
```

## Iterative Research Presets

| Preset | Loops | SERP/loop | Fan-out seeds | Max cost | Expected keywords | Use when |
|--------|-------|-----------|---------------|----------|-------------------|----------|
| **conservative** | 3 | 5 | 1 | ~22 tokens | 50–150 | Quick check, single subtopic, tight budget |
| **standard** | 5 | 10 | 3 | ~72 tokens | 150–400 | Normal keyword research, enough for a content plan |
| **aggressive** | 15 | 15 | 5 | ~262 tokens | 400–1000+ | Deep niche research, full topical map, wide coverage |
| **beast** | 30 | 20 | 5 | ~637 tokens | 1000–3000+ | Exhaustive mapping, competitor-level keyword database |

**Always present these presets to the user before running** so they can choose the depth and budget that fits their needs. More loops = more unique keywords discovered through PAA and Related Searches chains.

**How it works:**
1. Fan-out on seed keyword (AI-generated variants)
2. SERP on seed keyword → extract PAA questions + Related Searches
3. Loop: pick unprocessed keywords → SERP each → extract new PAA + Related Searches
4. Optional fan-out on top discoveries from early loops
5. Deduplicate throughout, save CSV with source tracking
6. Repeat until loops exhausted, queue empty, or budget spent

**Cost:** Fan-out = 7.5 tokens/keyword. SERP = 1 token/keyword. Use `--budget` to cap spending.

## Parameters Reference

**Always present these parameters to the user before running, so they understand what each one does and can choose.**

| Parameter | What it does | Effect on results | Cost impact |
|-----------|-------------|-------------------|-------------|
| `--loops N` | Number of SERP mining iterations | More loops = more keywords from deeper PAA/Related chains | +N×serp_per_loop tokens |
| `--serp-per-loop N` | Max keywords SERPed per loop | Higher = more keywords/loop but faster token burn. Each SERP extracts ~4 PAA + ~8 Related | +1 token per SERP call |
| `--fanout-seeds N` | Fan-out calls on top keywords from early loops | More fan-out = more AI-generated variants as queue seeds | +7.5 tokens per fan-out |
| `--serp-fanout` | SERP every fan-out result immediately | Massive keyword boost — each fan-out keyword gets SERPed for its own PAA + Related. Without this, fan-out results just wait in the queue | +1 token per fan-out result (~15-20 per fan-out call) |
| `--expand-popular N` | Fan-out on top N keywords that appear most often across SERPs | Expands "hub keywords" that Google considers highly related. Best after several loops | +7.5 tokens per popular keyword |
| `--popular-threshold T` | Min appearances for a keyword to count as "popular" (default: 2) | Lower = more keywords qualify for expand-popular. Higher = only strongest signals | No direct cost |
| `--budget N` | Hard token spending limit | Research stops when budget is reached, regardless of loops left | Controls max spend |
| `--preset` | Pre-configured intensity (conservative/standard/aggressive/beast) | Sets loops, serp-per-loop, fanout-seeds to sensible defaults | See presets table |

## CSV Output Columns

| Column | Description |
|--------|-------------|
| `keyword` | The discovered keyword or question |
| `source` | How it was found: `seed`, `fanout`, `paa`, `related_search`, `fanout_popular` |
| `type` | Keyword type: `seed`, `fanout_variant`, `paa_question`, `related_search`, `fanout_popular` |
| `discovered_in_loop` | Which loop discovered this keyword (0 = seed phase, 99 = expand-popular phase) |
| `serp_overlap` | How many different SERPs this keyword appeared in (PAA or Related Searches). Higher = Google strongly associates it with the topic. Use this to prioritize — keywords with high overlap are "hub keywords" worth targeting first |

## Output Directory

**Before running any research, always ask the user where to save results.**

Prompt the user with something like:
> Where should I save the results? You can:
> 1. Use an existing directory (e.g., `output/`, `research/seo/`)
> 2. Create a new one (e.g., `output/seo_campaign_2026/`)

- If the user specifies a directory, pass it via `--output <dir>/keywords_<keyword>_<gl>.csv`
- If the user doesn't specify, suggest a sensible default: `output/<keyword>_<gl>/`
- If the directory doesn't exist, create it (the script handles this automatically)
- For multi-keyword research, keep all files in the same directory for easy access

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [nod-nodeshub-api setup](../nod-nodeshub-api/setup/README.md) for details. (4) Have them run `check_setup.py` again to verify.

## Workflow: Keyword Expansion

1. **Get seed keyword(s)** from user — topic, product, or question
2. **Run Query Fan-out** with `--raw` for full data
3. **Organize results** into clusters by subtopic/intent
4. **Classify intent** for each cluster (informational, commercial, transactional)
5. **Prioritize** by relevance, estimated difficulty, and business value
6. **Deliver structured keyword map**

## Workflow: Topical Authority Map

1. **Start with main topic** — run Fan-out in `reasoning` mode for better quality
2. **Identify subtopic clusters** from results
3. **Run Fan-out on top 3-5 subtopics** (standard mode to save tokens)
4. **Map relationships** — pillar topic → cluster → supporting articles
5. **Identify content gaps** — topics without coverage
6. **Deliver topical map** with hierarchy and priorities

## Mode Selection

| Mode | Cost | Speed | Quality | Use when |
|------|------|-------|---------|----------|
| **standard** | 7.5 tokens | Fast | Good | Quick expansion, bulk research, budget-conscious |
| **reasoning** | 30 tokens | Slower | Better | Deep research, topical maps, high-value keywords |

**Rule of thumb:** Start with `standard`. Use `reasoning` for your primary topic or when standard results feel shallow.

## Clustering Strategy

Group keywords by:

1. **Intent cluster** — same search intent, similar SERP
2. **Topical cluster** — same subtopic, different angles
3. **Content type** — questions vs. comparisons vs. how-tos
4. **Funnel stage** — awareness → consideration → decision

### Cluster Naming Convention

```
[Main Topic]
├── [Subtopic A] (informational)
│   ├── keyword 1
│   ├── keyword 2 (question)
│   └── keyword 3 (long-tail)
├── [Subtopic B] (commercial)
│   ├── keyword 4
│   └── keyword 5
└── [Subtopic C] (transactional)
    └── keyword 6
```

## Output Format

```markdown
## Keyword Research: [seed keyword]

**Settings:** hl=[language], mode=[mode]
**Tokens used:** [X]

### Keyword Clusters

#### Cluster 1: [Subtopic Name] — [intent]
| Keyword | Type | Priority |
|---------|------|----------|
| ... | query/question/long-tail | high/medium/low |

#### Cluster 2: [Subtopic Name] — [intent]
| Keyword | Type | Priority |
|---------|------|----------|

### Questions (People Might Ask)
- [question 1]
- [question 2]

### Topical Map
[Main Topic]
├── [Pillar 1]: [keywords]
├── [Pillar 2]: [keywords]
└── [Pillar 3]: [keywords]

### Recommendations
1. [Which clusters to target first and why]
2. [Content type suggestions per cluster]
3. [Quick wins vs. long-term plays]
```

## Token Budget Planning

| Task | Mode | Keywords | Tokens |
|------|------|----------|--------|
| Quick expansion | standard | 1 | 7.5 |
| Topic research | standard | 5 | 37.5 |
| Deep topic map | reasoning | 1 + standard x5 | 67.5 |
| Full niche research | reasoning x3 + standard x10 | 13 | 165 |

Always tell the user the expected token cost before running.

## Tips

- **Start broad, then narrow** — seed with topic, then expand specific clusters
- **Questions are gold** — `--questions` flag reveals what users actually ask
- **Combine with SERP analysis** — validate clusters by checking who actually ranks
- **Language matters** — always match `--hl` to target market language
- **Save raw JSON** — pipe to file for later processing: `... --raw > keywords.json`

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(json_output)` from `iterative_research.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **nod-serp-analysis** — analyze SERP for specific keywords from your research
- **nod-content-brief** — turn keyword clusters into content briefs

- Language-specific quirks in fan-out results

**Consolidation (keep under 50 lines):**
Before adding a new entry, check file length. If over 50 lines:
1. Merge duplicate/overlapping entries into single proven patterns
2. Remove entries older than 3 months that haven't been reinforced
3. Drop one-off observations that never recurred
4. Move detailed context to `LEARNED-archive.md` if worth preserving
5. Keep only entries that would change behavior - if obvious, cut it
