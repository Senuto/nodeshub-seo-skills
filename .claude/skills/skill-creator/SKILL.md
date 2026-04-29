---
name: skill-creator
description: |
  Scaffold a new Agent Skills-compliant skill and auto-sync the skills registry.
  Creates the full directory structure (SKILL.md with complete frontmatter, scripts/, evals/)
  from a template. Supports both nod- skills (NodesHub API) and generic skills.
  Automatically updates the skills table in nod-nodeshub-api/SKILL.md and the skills list
  in CLAUDE.md. Use when user says "create skill," "new skill," "scaffold skill,"
  "add skill," or "skill creator."
compatibility: "Requires Python 3.9+"
metadata:
  author: nodeshub
  version: "0.2.0"
allowed-tools: Bash Read Write
---

# Skill Creator

Scaffold new Agent Skills-compliant skills and keep the skills registry in sync.

## What You Do

1. **Ask the user** for:
   - Skill name (e.g. `nod-my-skill` for NodesHub API skills, or `my-utility` for generic skills)
   - Short description (one sentence — include trigger phrases for agent discovery)
   - Cost per keyword (nod- skills only) or skip for generic skills

2. **Validate the name** against Agent Skills spec:
   - Lowercase letters, numbers, hyphens only
   - Max 64 characters
   - No leading/trailing/consecutive hyphens
   - Must match the directory name

3. **Run the scaffolding script:**

```bash
# For nod- skills (NodesHub API-based)
python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
  --name "nod-new-skill" \
  --description "Short description of what it does" \
  --cost "1 token"

# For generic skills (no NodesHub dependency)
python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
  --name "my-utility" \
  --description "What this utility does" \
  --type generic
```

4. **Registry sync** happens automatically:
   - nod- skills: `sync_skills.py` updates SKILL.md table and CLAUDE.md list
   - Generic skills: manually add to CLAUDE.md under the appropriate section

5. **Tell the user** what was created and what to do next.

## What Gets Scaffolded

```
.claude/skills/{name}/
├── SKILL.md          # Full Agent Skills frontmatter + template
├── scripts/          # Empty — user adds implementation
└── evals/
    └── evals.json    # Starter eval prompts and assertions
```

### Generated SKILL.md includes:

```yaml
---
name: {name}
description: |
  {description with trigger phrases}
compatibility: "{environment requirements}"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---
```

All five Agent Skills spec fields — `name`, `description`, `compatibility`, `metadata`, `allowed-tools`.

## Banner Requirement

For **every** new skill (with or without `nod-` prefix), when the skill is invoked Claude must run the banner as the first action:

```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Human-Readable Skill Name')"
```

Replace `Human-Readable Skill Name` with the skill title (e.g. "SERP Analysis", "Connect GSC").

## Sync Scripts

Located in `.claude/skills/nod-nodeshub-api/scripts/`:

| Script | What it does |
|--------|-------------|
| `create_skill.py` | Scaffolds a new skill (nod- or generic) with full spec compliance, auto-runs sync |
| `sync_skills.py` | Regenerates skills tables from nod-* directories — reads descriptions and cost from frontmatter |

`sync_skills.py` reads all metadata directly from each SKILL.md frontmatter. No hardcoded maps — new nod- skills are picked up automatically.

## Agent Skills Spec Reference

| Requirement | How this skill handles it |
|-------------|--------------------------|
| `name` (lowercase, hyphens, max 64) | Validated before creation |
| `description` (1-1024 chars, trigger phrases) | Template includes trigger phrase pattern |
| `compatibility` | Auto-set based on skill type |
| `metadata` (author, version) | Always included (nodeshub, 0.1.0) |
| `allowed-tools` | Default: Bash Read Write |
| `evals/evals.json` | Auto-generated with starter prompts |
| SKILL.md < 500 lines | Template is ~40 lines, user extends |
