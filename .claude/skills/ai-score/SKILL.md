---
name: ai-score
description: |
  Detect AI-generated content using Genuino API. Analyzes text and returns
  AI probability score, writing style classification, and optional humanization
  guidelines. Supports text input, files, and URLs (via Jina Reader).
  Use when user says "AI score," "AI detection," "check if AI," "is this AI content,"
  "genuino check," "AI probability," "humanize text," or "content authenticity."
  Requires GENUINO_API_KEY.
license: MIT
compatibility: "Requires Python 3.9+, GENUINO_API_KEY, and internet access. Optional: JINA_API_KEY for URL analysis"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# AI Score

Detect whether content is AI-generated or human-written using [Genuino](https://genuino.ai) API.

## Quick Start

```bash
# Analyze a text file
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt

# Analyze with humanization guidelines (+2 credits)
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt --guidelines

# Analyze with humanization prompt (+2 credits)
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt --humanize

# Both guidelines and humanization prompt (+4 credits)
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt --guidelines --humanize

# Analyze a URL (requires Jina Reader — optional JINA_API_KEY)
python3 .claude/skills/ai-score/scripts/analyze.py --url "https://example.com/article"

# Analyze inline text (min 200 words)
python3 .claude/skills/ai-score/scripts/analyze.py --text "Your long text here..."

# Raw JSON output
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt --json
```

## Setup

Requires `GENUINO_API_KEY`. **If not set up:** run `/connect-genuino`.

```bash
# Verify connection
python3 -c "
import json, urllib.request
from pathlib import Path
key = json.loads(Path('.claude/settings.local.json').read_text())['env']['GENUINO_API_KEY']
req = urllib.request.Request('https://api.genuino.ai/v1/health/basic')
req.add_header('X-API-Key', key)
req.add_header('User-Agent', 'genuino-claude-skill/0.1')
resp = urllib.request.urlopen(req, timeout=10)
print(json.loads(resp.read()))
"
```

For URL analysis, optionally set up Jina Reader: run `/connect-nodeshub` (Jina key is saved in the same settings file).

## What It Returns

| Field | Description |
|-------|-------------|
| **Classification** | `AI` or `HUMAN` |
| **AI Probability** | 0-100% score |
| **Writing Style** | Detected writing pattern (with confidence 0-100%) |
| **Style Description** | Human-readable explanation of the style |
| **Decision Threshold** | Model's decision boundary |
| **Decision Margin** | How far from the boundary (higher = more confident) |

### Optional extras (cost extra credits)

| Flag | What you get | Extra cost |
|------|-------------|------------|
| `--guidelines` | Per-section humanization guidelines with priorities and instructions | +2 credits |
| `--humanize` | Ready-to-use prompt to rewrite text more naturally | +2 credits |

## Workflow

1. **Get text** — user provides file, URL, or inline text
2. **Validate** — minimum 200 words required
3. **Analyze** — send to Genuino `/v1/analyze` endpoint
4. **Report** — show classification, AI probability, style, and optional guidelines
5. **If AI score is high** — suggest using `--guidelines` for specific sections to rewrite

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--text` | Inline text to analyze |
| `--file` | Path to text file |
| `--url` | URL to fetch via Jina Reader and analyze |
| `--guidelines` | Include humanization guidelines (+2 credits) |
| `--humanize` | Include humanization prompt (+2 credits) |
| `--json` | Output raw JSON response |

## API Details

- **Endpoint:** `POST https://api.genuino.ai/v1/analyze`
- **Auth:** `X-API-Key` header
- **Min text length:** 200 words
- **Feedback:** After analysis, users can submit feedback via `/v1/feedback` with the `analysis_id`

## Report

After collecting data, ask the user:

> "Add results to an HTML report?"
> 1. **New report** — creates a branded HTML report in `reports/`
> 2. **Existing report** — appends a section to a chosen report
> 3. **Skip** — no report

Use `render_report_section(data)` from `analyze.py`, then `create_report()` or `append_section()` from `report.py`.

## Related Skills

- **connect-genuino** — set up Genuino API key
- **nod-content-auditor** — audit content against SERP reality
- **nod-content-brief** — generate content briefs
