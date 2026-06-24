---
name: nod-nodeshub-api
description: |
  Shared NodesHub API client for SEO automation skills. Provides Python wrappers
  for SERPdata (SERP extraction), Query Fan-out (keyword expansion), Intent Classifier
  (search intent), and utility endpoints (balance, countries, languages).
  Other skills import from this module. Use when checking API balance, testing
  endpoints, or troubleshooting API connectivity. Keywords: NodesHub, API key,
  balance, credits, tokens, setup, connection test.
compatibility: "Requires Python 3.9+ and internet access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# NodesHub API

## Quick Start

```bash
# Check setup
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py

# Check balance
python3 .claude/skills/nod-nodeshub-api/scripts/balance.py

# Test SERPdata
python3 .claude/skills/nod-nodeshub-api/scripts/serpdata.py "seo tools" --gl us --hl en

# Test Query Fan-out
python3 .claude/skills/nod-nodeshub-api/scripts/fanout.py "seo tools" --hl en --mode standard

# List countries/languages
python3 .claude/skills/nod-nodeshub-api/scripts/params.py countries
python3 .claude/skills/nod-nodeshub-api/scripts/params.py languages

# Sync skills registry (updates SKILL.md + CLAUDE.md)
python3 .claude/skills/nod-nodeshub-api/scripts/sync_skills.py

# Scaffold a new skill (auto-syncs after creation)
python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
  --name "nod-new-skill" --description "What it does" --cost "1 token"
```

**If NodesHub is not set up:** Walk the user through the full process: (1) Get API key from [nodeshub.io](https://nodeshub.io) (API Playground). (2) Save to `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`. (3) Point to [setup/README.md](setup/README.md) for details and security. (4) Have them run `check_setup.py` to verify.

## What You Can Do With NodesHub

This skill is the base API client. The real power is in skills that use it:

<!-- SKILLS:START -->
| Skill | What it does | Cost per keyword |
|-------|-------------|------------------|
| `/nod-aio` | AI Overview (GEO/AEO) visibility for a keyword set, plus a brief-under-AIO recommendation | — |
| `/nod-alerting` | Turns one-off SEO snapshots into monitoring | — |
| `/nod-brand-split` | Deterministically split Google Search Console demand into BRANDED vs NON-BRANDED queries, so you can see how much traffic is people who already know the brand versus genuine new acquisition | — |
| `/nod-brief-builder` | Turn a user-provided keyword LIST into content briefs | — |
| `/nod-cannibalization` | Deterministic keyword cannibalization detector that runs on Google Search Console data | — |
| `/nod-commercial-value` | Deterministically rank a keyword set by REVENUE potential, not by traffic | — |
| `/nod-competitor-tracker` | Track competitor domains across keyword sets using NodesHub SERPdata API | 1 token per keyword checked |
| `/nod-content-auditor` | Audit existing content against current SERP reality using NodesHub SERPdata, Query Fan-out APIs, and Jina Reader for competitor page crawling | ~8 |
| `/nod-content-brief` | Generates data-driven SEO content briefs using NodesHub SERPdata and Query Fan-out APIs | — |
| `/nod-content-gap` | Classic content/keyword gap analysis: the keywords your competitors rank for that you don't (or rank worse for) | — |
| `/nod-demand-trajectory` | Year-over-year demand trajectory for a keyword set: decide whether each keyword/topic is Rising, Stable, or Declining so you know where to invest and where to exit | — |
| `/nod-featured-snippet-hunter` | Find Featured Snippet and Answer Box opportunities by analyzing Google SERPs using NodesHub SERPdata API | 1 token per keyword |
| `/nod-intent-roi` | Ties search intent to actual conversions so content is prioritized by ROI, not by traffic volume | — |
| `/nod-keyword-research` | Expand seed keywords into comprehensive keyword lists using NodesHub Query Fan-out API | — |
| `/nod-merger` | Merge Google Search Console + Google Analytics 4 + Google Ads into one clean funnel dataset keyed by URL (and by query where available) | — |
| `/nod-money-keywords` | Find the expensive paid terms you could win organically to cut your customer acquisition cost (CAC) | — |
| `/nod-opportunity-detector` | Deterministic SEO opportunity engine | — |
| `/nod-paa-miner` | Mine "People Also Ask" questions from Google SERPs for a list of keywords using NodesHub SERPdata API | 1 token per keyword + optional OpenRouter for clustering |
| `/nod-paid-organic` | Marketing-grade overlap analysis between paid (Google Ads) and organic (GSC) for the same keywords | — |
| `/nod-rank-tracker` | Track keyword ranking positions for a domain over time using NodesHub SERPdata API | 1 token per keyword checked |
| `/nod-seasonality` | Build ONE site-level seasonality curve from your keyword set so you can see when demand peaks, when to publish, and how to diversify away from a single annual spike | — |
| `/nod-serp-analysis` | Analyze Google SERP for any keyword using NodesHub SERPdata API | — |
| `/nod-serp-clusters` | Cluster keywords by SERP similarity — keywords sharing the same Google results belong to the same cluster | 1 NodesHub token per keyword + OpenRouter LLM for naming |
| `/nod-share-of-search` | Track Share of Search (Les Binet): your brand's search demand as a percentage of the total brand search demand in your category, measured month over month | — |
| `/nod-visibility-monitor` | Calculate SEO visibility score for a domain using weighted keyword positions via NodesHub SERPdata API | 1 token per keyword |
<!-- SKILLS:END -->

**After checking balance, always tell the user what they can do with their remaining tokens.** Example for 75 tokens: ~10 SERP analyses, ~5 keyword researches (standard), or ~3-4 full content briefs.

## API Endpoints

| Endpoint | Script | Cost | Key Params |
|----------|--------|------|------------|
| `/search` | `serpdata.py` | 1 token | keyword, gl, hl, device |
| `/query-fanout` | `fanout.py` | 7.5 (standard) / 30 (reasoning) | keyword, hl, mode |
| `/intent-classifier` | *beta* | 2 tokens | keyword, gl, hl |
| `/api-key/balance` | `balance.py` | 0 | — |
| `/google-params/gl` | `params.py countries` | 0 | — |
| `/google-params/hl` | `params.py languages` | 0 | — |

## Using in Other Skills

Other skills import the shared client:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from client import NodeshubClient

client = NodeshubClient()  # auto-resolves key from settings/env/prompt
results = client.search("keyword", gl="us", hl="en")
fanout = client.query_fanout("keyword", hl="en", mode="standard")
balance = client.get_balance()
```

## Authentication

The client resolves `NODESHUB_API_KEY` in this order:
1. Explicit `api_key` argument
2. `NODESHUB_API_KEY` environment variable
3. `.claude/settings.local.json` → `env.NODESHUB_API_KEY` (repo-level)
4. `~/.claude/settings.local.json` (user-level)
5. `~/.claude/settings.json` (user-level)
6. **Interactive prompt** — asks user to paste key and saves to `.claude/settings.local.json`

**First run:** If no key is found, the script will ask for it and save automatically.

Get your key at [nodeshub.io](https://nodeshub.io) — scroll to API Playground, click "Copy to clipboard". Free plan includes 100 tokens.

## Error Handling

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized` | Invalid or expired key | Get new key from nodeshub.io |
| `Insufficient balance` | No tokens left | Buy credits at nodeshub.io |
| Connection timeout | Network issue | Check internet, retry |


