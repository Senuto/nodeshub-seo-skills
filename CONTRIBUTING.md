# Contributing

We accept pull requests! Whether it's a new skill, a bug fix, or a docs improvement — contributions from the community are welcome. You don't need any special access: the repo is public, so anyone can fork it and open a PR.

## How to submit a pull request

### 1. Fork the repository

Click **Fork** on [github.com/Senuto/nodeshub-seo-skills](https://github.com/Senuto/nodeshub-seo-skills), or use the GitHub CLI:

```bash
gh repo fork Senuto/nodeshub-seo-skills --clone
cd nodeshub-seo-skills
```

### 2. Create a branch

```bash
git checkout -b my-change
```

Use a short, descriptive branch name (e.g. `add-serp-volatility-skill`, `fix-sync-script-encoding`).

### 3. Make your changes

- **New skill?** Follow [Creating your own skills](#creating-your-own-skills) below — the same structure applies whether you keep a skill local or contribute it back.
- **Bug fix or docs?** Keep the change focused — one fix per PR.

### 4. Validate

```bash
bash validate-skills.sh
```

Checks: frontmatter validity, name matches directory, naming conventions, description length, required files. PRs that fail validation won't be merged.

### 5. Commit and push

```bash
git add -A
git commit -m "Add nod-my-skill: short description of what it does"
git push -u origin my-change
```

### 6. Open the pull request

```bash
gh pr create --repo Senuto/nodeshub-seo-skills --title "Add nod-my-skill" --body "What it does and why"
```

Or open it from the GitHub web UI — after pushing, GitHub shows a "Compare & pull request" button on your fork.

In the PR description, include:
- **What** the change does
- **Why** it's useful (example use case)
- For new skills: a sample prompt + the output it produced when you tested it

### What makes a PR easy to merge

- One skill / one fix per PR — small PRs get reviewed faster
- `bash validate-skills.sh` passes
- New skills include `evals/evals.json` with at least one eval
- New `nod-` skills are registered via `sync_skills.py`; generic skills are added to `CLAUDE.md` and `.claude-plugin/marketplace.json`
- You actually ran the skill and it works

### Review process

A maintainer will review your PR, possibly request changes, and merge it. We aim to respond within a few days. If a PR goes quiet, feel free to ping us in the [SEO Testers Discord](https://discord.gg/VhB7FFfndJ).

---

## Other ways to contribute

### Suggest a skill or improvement

Not ready to write code? [Open an issue](https://github.com/Senuto/nodeshub-seo-skills/issues/new) with:
- What the skill should do
- Example use case (e.g. "I want to check if my competitors use AI content")
- Which existing skills it could build on

### Report a bug

[Open an issue](https://github.com/Senuto/nodeshub-seo-skills/issues/new) with:
- What you did
- What you expected
- What happened instead
- Your setup (OS, Python version, Claude Code version)

---

## Creating your own skills

You can extend this toolkit with custom skills — keep them local to your project, or contribute them back via PR (see above). Everything you create works immediately.

### The fast way: `/skill-creator`

Run `/skill-creator` inside Claude Code. It scaffolds a spec-compliant skill with full frontmatter, scripts directory, and starter evals.

```bash
# NodesHub API skill
python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
  --name "nod-my-skill" \
  --description "What it does and when to use it" \
  --cost "1 token"

# Generic skill (no NodesHub dependency)
python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
  --name "my-utility" \
  --description "What it does" \
  --type generic
```

This creates:

```
.claude/skills/{name}/
├── SKILL.md          # Full Agent Skills frontmatter + template
├── scripts/          # Your code goes here
└── evals/
    └── evals.json    # Starter test prompts
```

### The manual way

#### 1. Create the skill directory

```bash
mkdir -p .claude/skills/my-skill-name/scripts
mkdir -p .claude/skills/my-skill-name/evals
```

#### 2. Create SKILL.md with full frontmatter

Every skill needs a `SKILL.md` file following the [Agent Skills spec](https://agentskills.io/specification):

```yaml
---
name: my-skill-name
description: |
  What this skill does. Include trigger phrases that help agents
  recognize when to activate it. Use when user says "do X," "run Y,"
  or related phrases.
compatibility: "Requires Python 3.9+"
metadata:
  author: your-name
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# My Skill Name

Instructions for the agent go here...

## Quick Start
## Workflow
## Related Skills
```

#### 3. Naming conventions

- **Lowercase + hyphens only** (e.g. `nod-serp-analysis`, `my-utility`)
- **Max 64 characters**, no leading/trailing/consecutive hyphens
- **`name` field must match directory name** exactly
- **`nod-` prefix** = uses NodesHub API; no prefix = standalone

#### 4. Add a script (if your skill runs code)

```python
#!/usr/bin/env python3
"""Your skill description."""

import sys
from pathlib import Path

# Import shared NodesHub API client (for nod- skills)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))
from serpdata import fetch_serp  # or other shared modules
```

#### 5. Add evals

Create `evals/evals.json`:

```json
{
  "skill_name": "my-skill-name",
  "evals": [
    {
      "id": 1,
      "prompt": "Example user prompt that should trigger this skill",
      "expected_output": "What the skill should produce",
      "assertions": [
        "Calls the appropriate endpoint",
        "Returns structured data",
        "Handles errors gracefully"
      ],
      "files": []
    }
  ]
}
```

#### 6. Register the skill

For nod- skills — sync runs automatically after `create_skill.py`. Or manually:

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/sync_skills.py
```

For generic skills — add manually to:
- `CLAUDE.md` (Available skills section)
- `.claude-plugin/marketplace.json` (skills array)

### Validate

```bash
bash validate-skills.sh
```

Checks: frontmatter validity, name matches directory, naming conventions, description length, required files.
