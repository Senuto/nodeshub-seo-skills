---
name: nod-nodeshub-api
description: |
  Shared NodesHub API client for SEO automation skills. Provides Python wrappers
  for SERPdata (SERP extraction), Query Fan-out (keyword expansion), Intent Classifier
  (search intent), and utility endpoints (balance, countries, languages).
  Other skills import from this module. Use when checking API balance, testing
  endpoints, or troubleshooting API connectivity. Keywords: NodesHub, API key,
  balance, credits, tokens, setup, connection test.
license: MIT
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
| `/nod-competitor-tracker` | Tracks competitor domains across keyword sets, shows who ranks where | 1 token |
| `/nod-content-auditor` | Audits content against SERP reality — finds gaps, missing keywords | ~8.5 tokens (standard) / ~31 tokens (reasoning) |
| `/nod-content-brief` | Combines SERP + keyword research into a ready-to-write content brief | ~8.5 tokens (standard) / ~31 tokens (reasoning) |
| `/nod-featured-snippet-hunter` | Finds Featured Snippet opportunities — steal, defend, or target for your domain | 1 token |
| `/nod-intent-classifier` | Classifies search intent (info/commercial/transactional/navigational) from SERP signals | 1 token |
| `/nod-keyword-research` | Expands a seed keyword into related phrases, questions, long-tail variations, topic clusters | 7.5 tokens (standard) / 30 tokens (reasoning) |
| `/nod-paa-miner` | Mines People Also Ask questions from SERPs, deduplicates, optionally clusters by topic | 1 token + optional OpenRouter |
| `/nod-rank-tracker` | Tracks keyword positions for a domain over time, compares changes | 1 token |
| `/nod-serp-analysis` | Analyzes Google top 10 for a keyword — who ranks, SERP features, intent, content gaps | 1 token |
| `/nod-serp-clusters` | | | — |
| `/nod-visibility-monitor` | Calculates weighted SEO visibility score, compares with competitors | 1 token |
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


