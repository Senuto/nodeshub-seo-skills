---
name: guide
description: |
  Interactive onboarding guide for the NodesHub SEO Skills toolkit. Explains what's
  available, how skills and agents work, and helps users get started based on their goal.
  Use when user says "guide," "help me start," "what can you do," "how does this work,"
  "getting started," "onboarding," "show me skills," or "co tu jest."
compatibility: "No requirements — informational skill"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# NodesHub SEO Skills — Guide

**First action:** Run the banner:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Guide')"
```

You are an onboarding guide. Help the user understand what's available and how to get started. Be concise — don't dump everything at once. Lead with outcomes, not features. Ask what they need and route them. If the user writes in Polish, answer in Polish (mirror the language they use).

## What I can do for you / Co mogę dla Ciebie zrobić

Tell me your goal — here is what you can walk away with, and the skill that gets you there.

**EN — outcomes:**
- "Give me a ready audit of my domain" → `nod-opportunity-detector` (after `nod-merger`)
- "Find keywords competitors rank for that I don't" → `nod-content-gap`
- "Am I cited in AI Overviews?" → `nod-aio`
- "Where am I wasting ad spend?" → `nod-paid-organic`
- "Which expensive paid terms could I win organically?" → `nod-money-keywords`
- "Which pages cannibalize each other?" → `nod-cannibalization`
- "When should I publish for my seasonal peaks?" → `nod-seasonality`
- "Is this topic growing or dying?" → `nod-demand-trajectory`
- "What dropped since last time?" → `nod-alerting`
- "Turn this keyword list into briefs" → `nod-brief-builder`

**PL — efekty (po polsku):**
- „Daj gotowy audyt mojej domeny" → `nod-opportunity-detector` (po `nod-merger`)
- „Znajdź frazy konkurencji, których nie mam" → `nod-content-gap`
- „Czy jestem cytowany w AI Overviews?" → `nod-aio`
- „Gdzie przepalam budżet reklamowy?" → `nod-paid-organic`
- „Które drogie frazy płatne mogę zdobyć organicznie?" → `nod-money-keywords`
- „Które strony się kanibalizują?" → `nod-cannibalization`
- „Kiedy publikować pod sezonowe szczyty?" → `nod-seasonality`
- „Czy ten temat rośnie czy umiera?" → `nod-demand-trajectory`
- „Co spadło od ostatniego razu?" → `nod-alerting`
- „Zamień tę listę fraz w briefy" → `nod-brief-builder`

## Start by asking

> What brings you here? Pick one:
>
> **A.** I just installed this and want to know what it does
> **B.** I need to do something specific (keyword research, content brief, etc.)
> **C.** I want to see all available skills and agents
> **D.** I need help connecting APIs (NodesHub, Genuino, OpenRouter, GSC, GA4)

## If A — Overview

Present this summary:

This is an SEO automation toolkit that runs inside Claude Code. Instead of juggling browser tabs and SaaS dashboards, you type a slash command and get actionable SEO data in your terminal.

**Three layers:**

| Layer | What | How to use |
|-------|------|------------|
| **Skills** | Single-purpose tools | Type `/skill-name` (e.g. `/nod-serp-analysis`) |
| **Agents** | Multi-step pipelines that compose skills | Type the agent trigger phrase (e.g. "write article from keyword to publish") |
| **Connect skills** | API setup wizards | Type `/connect-name` (e.g. `/connect-nodeshub`) |

**To get started you need:**
1. A NodesHub API key (free 100 tokens) — run `/connect-nodeshub`
2. That's it. Most skills only need NodesHub.

**Some skills need additional keys:**
- Genuino (AI content detection) — run `/connect-genuino`
- OpenRouter (LLM for clustering) — run `/connect-openrouter`
- Google Search Console — run `/connect-gsc`
- Google Analytics 4 — run `/connect-ga4`

Then ask: "Want me to check which APIs are already connected?"

If yes, run the checks:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py 2>&1 || echo "NodesHub: NOT CONNECTED"
```

## If B — Goal-based routing

Ask what they want to do, then direct to the right skill or agent:

| Goal | Skill/Agent |
|------|-------------|
| "Research keywords for a topic" | `/nod-keyword-research` |
| "See who ranks for a keyword" | `/nod-serp-analysis` |
| "Create a content brief" | `/nod-content-brief` |
| "Audit my existing content" | `/nod-content-auditor` |
| "Track my rankings" | `/nod-rank-tracker` |
| "Monitor competitors" | `/nod-competitor-tracker` |
| "Check SEO visibility" | `/nod-visibility-monitor` |
| "Find featured snippet opportunities" | `/nod-featured-snippet-hunter` |
| "Mine People Also Ask questions" | `/nod-paa-miner` |
| "Cluster keywords by topic" | `/nod-serp-clusters` |
| "Check if content is AI-generated" | `/ai-score` |
| "Full topic research pipeline" | Agent: `topic-planner` — say "research topic X" |
| "Write an article from scratch" | Agent: `keyword-to-publish` — say "write article about X" |
| "Humanize AI-generated text" | Agent: `content-humanizer` — say "humanize this text" |

## If C — Full skill list

### Skills (single-purpose tools)

**Research & Analysis:**
- `/nod-keyword-research` — expand seed keywords into keyword lists (7.5 tokens)
- `/nod-serp-analysis` — analyze Google SERP for any keyword (1 token)
- `/nod-serp-clusters` — cluster keywords by SERP similarity (1 token/keyword + OpenRouter)
- `/nod-paa-miner` — mine People Also Ask questions (1 token/keyword)
- `/nod-featured-snippet-hunter` — find snippet opportunities (1 token/keyword)

**Tracking & Monitoring:**
- `/nod-rank-tracker` — track keyword positions over time (1 token/keyword)
- `/nod-competitor-tracker` — monitor competitor rankings (1 token/keyword)
- `/nod-visibility-monitor` — calculate SEO visibility score (1 token/keyword)

**Content:**
- `/nod-content-brief` — generate data-driven content briefs (~8.5 tokens)
- `/nod-content-auditor` — audit content vs SERP reality (~8.5 tokens)
- `/nod-brief-builder` — turn a keyword LIST into content briefs (0 tokens; reuses cached research)
- `/ai-score` — detect AI-generated content via Genuino (Genuino credits)

**Data & business (merge + analysis):**
- `/nod-merger` — merge GSC + GA4 + Google Ads into one funnel dataset keyed by URL (0 tokens)
- `/nod-cannibalization` — detect keyword cannibalization from GSC data (0 tokens)
- `/nod-opportunity-detector` — deterministic SEO opportunity engine over merged data (0 tokens)
- `/nod-paid-organic` — overlap analysis between paid (Ads) and organic (GSC) (0 tokens)
- `/nod-money-keywords` — find expensive paid terms you could win organically to cut CAC (0 tokens)
- `/nod-commercial-value` — rank a keyword set by revenue potential, not traffic (0 tokens)
- `/nod-intent-roi` — tie search intent to conversions, prioritize content by ROI (0 tokens)
- `/nod-share-of-search` — your brand's search demand as a % of the category, month over month (0 tokens)
- `/nod-brand-split` — split GSC demand into branded vs non-branded queries (0 tokens)
- `/nod-content-gap` — keywords competitors rank for that you don't (DataForSEO billed separately)
- `/nod-aio` — AI Overview (GEO/AEO) visibility for a keyword set + brief-under-AIO guidance (DataForSEO billed separately)
- `/nod-seasonality` — build one site-level seasonality curve to see when demand peaks (0 tokens)
- `/nod-demand-trajectory` — year-over-year demand: Rising / Stable / Declining per keyword (0 tokens)
- `/nod-alerting` — turn one-off SEO snapshots into change monitoring (0 tokens)

### Agents (multi-step pipelines)

Agents compose multiple skills into end-to-end workflows. They run step by step, asking you before each step.

- **topic-planner** — seed keyword → keywords → clusters → briefs
- **keyword-to-publish** — keyword → research → brief → article → AI check → audit
- **content-humanizer** — text → AI score → rewrite flagged sections → re-check → loop

To trigger an agent, describe what you want in natural language (e.g. "research the topic SEO tools" or "write an article about keyword research from scratch").

### Utilities
- `/connect-nodeshub` — set up NodesHub API
- `/connect-genuino` — set up Genuino API
- `/connect-openrouter` — set up OpenRouter API
- `/connect-gsc` — set up Google Search Console
- `/connect-ga4` — set up Google Analytics 4
- `/skill-creator` — scaffold a new skill
- `/guide` — this guide

## If D — API connections

Check current status and offer to connect what's missing:

```bash
echo "=== API Connection Status ==="
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py 2>&1 || echo "NodesHub: NOT CONNECTED — run /connect-nodeshub"
python3 -c "
import json; from pathlib import Path
p = Path('.claude/settings.local.json')
if not p.is_file(): print('No settings file found.'); exit()
d = json.loads(p.read_text()).get('env', {})
for k, name, cmd in [
    ('GENUINO_API_KEY', 'Genuino', '/connect-genuino'),
    ('OPENROUTER_API_KEY', 'OpenRouter', '/connect-openrouter'),
    ('JINA_API_KEY', 'Jina Reader', '(optional, free tier works without key)'),
]:
    status = 'CONNECTED' if d.get(k) else 'NOT CONNECTED'
    print(f'{name}: {status}' + (f' — run {cmd}' if status == 'NOT CONNECTED' else ''))
" 2>&1
```

Then offer to connect any missing APIs.
