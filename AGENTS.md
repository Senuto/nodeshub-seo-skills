# AGENTS.md

Guidelines for AI agents working in this repository.

## Repository Overview

This repository contains **Agent Skills** for AI agents following the [Agent Skills specification](https://agentskills.io/specification.md). Skills install to `.claude/skills/` (Claude Code native). This repo also serves as a **Claude Code plugin marketplace** via `.claude-plugin/marketplace.json`.

- **Name**: Nodeshub SEO Skills
- **GitHub**: [Senuto/nodeshub-seo-skills](https://github.com/Senuto/nodeshub-seo-skills)
- **Creator**: Senuto
- **License**: Proprietary (see TERMS-OF-USE.md)

## Repository Structure

```
nodeshub-seo-skills/
├── .claude/
│   └── skills/              # Claude Code skills
│       ├── nod-*/           # SEO skills (each has SKILL.md + scripts/)
│       ├── connect-*/       # Setup/connection guides
│       └── skill-creator/   # Skill scaffolding tool
├── .claude-plugin/
│   └── marketplace.json     # Claude Code plugin marketplace manifest
├── docs/                    # Product & brand context (feeds into content skills)
├── tools/                   # Integration guides
├── data/                    # Tracking data (rankings, visibility, competitors)
├── scripts/                 # Utility scripts (fetch-gsc.js, fetch-ga4.js)
├── bin/                     # npm installer
├── AGENTS.md                # This file — agent guidelines
├── CLAUDE.md                # Claude Code project instructions & skill registry
├── CONTRIBUTING.md          # How to add or modify skills
├── LICENSE                  # Proprietary — see TERMS-OF-USE.md
└── README.md
```

## Build / Lint / Test Commands

**Skills** use Python scripts (Python 3.9+). Verify with:

```bash
python3 --check .claude/skills/nod-*/scripts/*.py   # Syntax check (not all support this)
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py  # Connectivity check
python3 .claude/skills/nod-nodeshub-api/scripts/balance.py      # Token balance
```

**Validation:**

```bash
bash validate-skills.sh   # Check all skills for spec compliance
```

**GSC/GA4 data fetching** (Node.js 18+):

```bash
npm install
npm run fetch-gsc
npm run fetch-ga4
```

## Agent Skills Specification

Skills follow the [Agent Skills spec](https://agentskills.io/specification.md).

### Required Frontmatter

```yaml
---
name: skill-name
description: What this skill does and when to use it. Include trigger phrases.
allowed-tools: Bash Read Write
---
```

### Frontmatter Field Constraints

| Field           | Required | Constraints                                                    |
| --------------- | -------- | -------------------------------------------------------------- |
| `name`          | Yes      | 1-64 chars, lowercase `a-z`, numbers, hyphens. Must match dir. |
| `description`   | Yes      | 1-1024 chars. Describe what it does and when to use it.        |
| `allowed-tools` | No       | Space-separated list of tools the skill may use.               |
| `metadata`      | No       | Key-value pairs (author, version, etc.).                       |

### Name Field Rules

- Lowercase letters, numbers, and hyphens only
- Cannot start or end with hyphen
- No consecutive hyphens (`--`)
- Must match parent directory name exactly

**Valid**: `nod-serp-analysis`, `connect-nodeshub`, `skill-creator`
**Invalid**: `nod_serp-analysis`, `-nod-serp`, `nod--serp`

### Optional Skill Directories

```
skill-name/
├── SKILL.md          # Required — skill definition
├── scripts/          # Executable Python scripts
├── evals/
│   └── evals.json    # Test prompts and assertions
└── references/       # Supporting knowledge files
```

## Cross-Skill Dependencies

All `nod-*` skills depend on `nod-nodeshub-api` for:

- API client (`serpdata.py`, `queryfanout.py`, `intent.py`)
- Shared utilities (`banner.py`, `balance.py`, `jina_reader.py`)

Scripts import via `sys.path.insert` pointing to `nod-nodeshub-api/scripts/`.

## API Token Costs

| Operation                 | Cost                 |
| ------------------------- | -------------------- |
| SERPdata (one keyword)    | 1 token              |
| Query Fan-out (standard)  | 7.5 tokens per seed  |
| Query Fan-out (reasoning) | 30 tokens per seed   |
| Intent Classifier         | 2 tokens per keyword |

Always check balance before bulk operations: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`
