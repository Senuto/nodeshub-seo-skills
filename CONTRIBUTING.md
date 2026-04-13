# Contributing

## How contributions work right now

This project is in **early development**. We're not accepting pull requests yet — but we'd love to hear your ideas.

### Suggest a skill or improvement

[Open an issue](https://github.com/Senuto/nodeshub-seo-skills/issues/new) with:
- What the skill should do
- Example use case (e.g. "I want to check if my competitors use AI content")
- Which existing skills it could build on

We review suggestions and may include them in future releases.

### Report a bug

[Open an issue](https://github.com/Senuto/nodeshub-seo-skills/issues/new) with:
- What you did
- What you expected
- What happened instead
- Your setup (OS, Python version, Claude Code version)

---

## Creating your own skills locally

You can extend this toolkit with custom skills in your own project — no PR needed. Everything you create stays local and works immediately.

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
license: MIT
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

---

*When we open up for pull requests, we'll add code style and commit guidelines here.*
