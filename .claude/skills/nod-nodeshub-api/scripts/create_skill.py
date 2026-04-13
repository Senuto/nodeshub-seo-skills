#!/usr/bin/env python3
"""
Scaffold a new Agent Skills-compliant skill and auto-sync the registry.

Supports both nod- skills (NodesHub API-based) and generic skills.

Usage:
    # nod- skill (default)
    python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
        --name "nod-new-skill" \
        --description "Short description of what it does" \
        --cost "1 token"

    # Generic skill (no NodesHub dependency)
    python3 .claude/skills/nod-nodeshub-api/scripts/create_skill.py \
        --name "my-utility" \
        --description "What this utility does" \
        --type generic
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
SYNC_SCRIPT = Path(__file__).resolve().parent / "sync_skills.py"

NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
MAX_NAME_LEN = 64


def validate_name(name: str) -> None:
    """Validate skill name per Agent Skills spec."""
    if len(name) > MAX_NAME_LEN:
        print(f"[ERROR] Name too long ({len(name)} chars, max {MAX_NAME_LEN}): {name}")
        sys.exit(1)
    if not NAME_PATTERN.match(name):
        print(f"[ERROR] Invalid name: '{name}'")
        print("  Must be lowercase letters, numbers, and hyphens only.")
        print("  Cannot start/end with hyphen or have consecutive hyphens.")
        sys.exit(1)


def make_title(name: str) -> str:
    """Convert skill-name or nod-skill-name to human-readable title."""
    without_prefix = name.removeprefix("nod-")
    return without_prefix.replace("-", " ").title()


def create_nod_skill_md(name: str, description: str, cost: str) -> str:
    """Generate SKILL.md for a nod- skill (NodesHub API-based)."""
    title = make_title(name)
    return f"""---
name: {name}
description: |
  {description}
  Requires NODESHUB_API_KEY. Cost: {cost} per keyword.
license: MIT
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY, and internet access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# {title}

{description}

## Quick Start

```bash
# Check setup
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py

# Check balance
python3 .claude/skills/nod-nodeshub-api/scripts/balance.py
```

**Cost:** {cost} per keyword. Check balance: `python3 .claude/skills/nod-nodeshub-api/scripts/balance.py`

## Setup

Requires `NODESHUB_API_KEY`. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

## Workflow

1. **Get input** from user
2. **Check token balance**
3. **Run analysis**
4. **Report results**

## Related Skills

- **nod-serp-analysis** -- SERP analysis for specific keywords
- **nod-keyword-research** -- keyword expansion and clustering
"""


def create_generic_skill_md(name: str, description: str) -> str:
    """Generate SKILL.md for a generic (non-nod-) skill."""
    title = make_title(name)
    return f"""---
name: {name}
description: |
  {description}
  Use when user says "{title.lower()}," or related phrases.
license: MIT
compatibility: "Requires Python 3.9+"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# {title}

{description}

## Quick Start

<!-- Add example commands here -->

## Workflow

1. **Get input** from user
2. **Process**
3. **Report results**
"""


def create_evals(name: str, description: str) -> dict:
    """Generate a starter evals.json for the skill."""
    title = make_title(name)
    return {
        "skill_name": name,
        "evals": [
            {
                "id": 1,
                "prompt": f"Run {title.lower()} for a sample input.",
                "expected_output": f"Should execute {title.lower()} workflow and return structured results.",
                "assertions": [
                    f"Triggers on {title.lower()}-related language",
                    "Processes user input correctly",
                    "Returns structured output",
                ],
                "files": [],
            },
            {
                "id": 2,
                "prompt": f"Help me with {description.split('.')[0].lower().strip()}.",
                "expected_output": f"Should activate {name} skill and follow the documented workflow.",
                "assertions": [
                    "Activates the correct skill",
                    "Follows workflow steps",
                    "Provides actionable output",
                ],
                "files": [],
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new Agent Skills-compliant skill"
    )
    parser.add_argument("--name", required=True, help="Skill name, e.g. nod-my-skill or my-utility")
    parser.add_argument("--description", required=True, help="Short description of the skill")
    parser.add_argument("--cost", default=None, help="Cost per keyword (nod- skills only), e.g. '1 token'")
    parser.add_argument(
        "--type",
        choices=["nod", "generic"],
        default=None,
        help="Skill type: 'nod' (NodesHub API) or 'generic'. Auto-detected from name if omitted.",
    )
    args = parser.parse_args()

    name = args.name
    validate_name(name)

    # Auto-detect type from name prefix
    skill_type = args.type
    if skill_type is None:
        skill_type = "nod" if name.startswith("nod-") else "generic"

    if skill_type == "nod" and not name.startswith("nod-"):
        print(f"[ERROR] nod-type skills must start with 'nod-', got: {name}")
        sys.exit(1)

    if skill_type == "nod" and not args.cost:
        print("[ERROR] --cost is required for nod- skills (e.g. '1 token')")
        sys.exit(1)

    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        print(f"[ERROR] Skill directory already exists: {skill_dir.relative_to(REPO_ROOT)}")
        sys.exit(1)

    print(f"Creating skill: {name} (type: {skill_type})")
    print(f"  Directory: .claude/skills/{name}/")

    # Create directory structure
    skill_dir.mkdir(parents=True)
    (skill_dir / "scripts").mkdir()
    (skill_dir / "evals").mkdir()

    # Write SKILL.md
    if skill_type == "nod":
        content = create_nod_skill_md(name, args.description, args.cost)
    else:
        content = create_generic_skill_md(name, args.description)

    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    print("  Created SKILL.md (full Agent Skills frontmatter)")

    # Write evals/evals.json
    evals = create_evals(name, args.description)
    (skill_dir / "evals" / "evals.json").write_text(
        json.dumps(evals, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("  Created evals/evals.json")

    print(f"\nSkill '{name}' scaffolded successfully.")
    title = make_title(name)
    print(f"\nNext steps:")
    print(f"  1. Edit .claude/skills/{name}/SKILL.md — flesh out description, workflow, and trigger phrases")
    print(f"  2. Add scripts to .claude/skills/{name}/scripts/")
    print(f"     Include the banner in your main script:")
    print(f"       sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nod-nodeshub-api' / 'scripts'))")
    print(f"       from banner import print_banner")
    print(f"       print_banner(\"{title}\")")
    print(f"  3. Update evals/evals.json with real test prompts and assertions")

    # Auto-sync registry (covers nod- skills; generic skills need manual CLAUDE.md update)
    if skill_type == "nod":
        print("\nRunning sync_skills.py...")
        result = subprocess.run(
            [sys.executable, str(SYNC_SCRIPT)],
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"[WARN] sync_skills.py failed:\n{result.stderr}")
    else:
        print(f"\n[INFO] Generic skill — add it manually to CLAUDE.md under the appropriate section.")

    print("Done.")


if __name__ == "__main__":
    main()
