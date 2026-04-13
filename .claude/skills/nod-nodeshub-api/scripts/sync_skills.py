#!/usr/bin/env python3
"""
Sync skills registry — regenerates skills tables in SKILL.md and CLAUDE.md
from actual skill directories under .claude/skills/nod-*.

Reads descriptions and cost info directly from each SKILL.md frontmatter
so new skills are picked up automatically without hardcoded maps.

Usage:
    python3 .claude/skills/nod-nodeshub-api/scripts/sync_skills.py
    python3 .claude/skills/nod-nodeshub-api/scripts/sync_skills.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

# Resolve repo root (4 levels up from this script)
REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
API_SKILL_MD = SKILLS_DIR / "nod-nodeshub-api" / "SKILL.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

MARKER_START = "<!-- SKILLS:START -->"
MARKER_END = "<!-- SKILLS:END -->"


def parse_frontmatter(skill_md: Path) -> dict:
    """Parse YAML frontmatter from a SKILL.md file.

    Handles multiline description fields (indented continuation lines).
    """
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    current_key = None
    current_val_lines = []

    for line in match.group(1).split("\n"):
        # Top-level key (not indented, contains colon)
        if not line.startswith(" ") and not line.startswith("\t") and ":" in line:
            # Save previous key
            if current_key:
                fm[current_key] = " ".join(current_val_lines).strip()
            key, val = line.split(":", 1)
            current_key = key.strip()
            val = val.strip()
            if val == "|" or val == ">":
                current_val_lines = []
            else:
                current_val_lines = [val]
        elif current_key and (line.startswith("  ") or line.startswith("\t")):
            # Continuation of multiline value
            current_val_lines.append(line.strip())
        elif current_key and line.strip() == "":
            # Blank line inside multiline
            continue

    if current_key:
        fm[current_key] = " ".join(current_val_lines).strip()

    return fm


def extract_cost(description: str) -> str:
    """Extract cost info from description field (e.g. 'Cost: 1 token per keyword.')."""
    match = re.search(r"Cost:\s*(.+?)(?:\.|$)", description)
    if match:
        return match.group(1).strip()
    return "—"


def extract_first_sentence(description: str) -> str:
    """Get first meaningful sentence from description for short display."""
    # Remove "Requires..." and "Cost:..." suffixes
    cleaned = re.sub(r"\s*Requires\s+\w+.*$", "", description)
    cleaned = re.sub(r"\s*Cost:.*$", "", cleaned)
    cleaned = cleaned.strip().rstrip(".")
    # Take first sentence
    parts = cleaned.split(". ")
    return parts[0].strip()


def discover_skills() -> list[dict]:
    """Discover all nod-* skill directories and return metadata."""
    skills = []
    for skill_dir in sorted(SKILLS_DIR.glob("nod-*")):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md)
        name = fm.get("name", skill_dir.name)
        description = fm.get("description", "")

        skills.append({
            "name": name,
            "dir": skill_dir.name,
            "description": description,
            "short_desc": extract_first_sentence(description),
            "cost": extract_cost(description),
        })
    return skills


def build_skill_table(skills: list[dict]) -> str:
    """Build the markdown table for SKILL.md (excludes nod-nodeshub-api itself)."""
    lines = [
        "| Skill | What it does | Cost per keyword |",
        "|-------|-------------|------------------|",
    ]
    for s in skills:
        if s["name"] == "nod-nodeshub-api":
            continue
        lines.append(f"| `/{s['name']}` | {s['short_desc']} | {s['cost']} |")
    return "\n".join(lines)


def build_claude_list(skills: list[dict]) -> str:
    """Build the bullet list for CLAUDE.md."""
    lines = []
    for s in skills:
        # Use short description, lowercase first letter
        short = s["short_desc"]
        if short:
            short = short[0].lower() + short[1:]
        lines.append(f"- `/{s['name']}` - {short}")
    return "\n".join(lines)


def replace_between_markers(filepath: Path, new_content: str, dry_run: bool = False) -> bool:
    """Replace content between SKILLS:START and SKILLS:END markers."""
    text = filepath.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"({re.escape(MARKER_START)})\n.*?\n({re.escape(MARKER_END)})",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        print(f"  [WARN] No markers found in {filepath.relative_to(REPO_ROOT)}")
        return False

    new_text = pattern.sub(rf"\1\n{new_content}\n\2", text)
    if new_text == text:
        print(f"  [OK] {filepath.relative_to(REPO_ROOT)} — no changes needed")
        return False

    if dry_run:
        print(f"  [DRY-RUN] Would update {filepath.relative_to(REPO_ROOT)}")
    else:
        filepath.write_text(new_text, encoding="utf-8")
        print(f"  [OK] Updated {filepath.relative_to(REPO_ROOT)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Sync skills registry")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    print("Discovering skills...")
    skills = discover_skills()
    print(f"  Found {len(skills)} skills: {', '.join(s['name'] for s in skills)}")

    print("\nUpdating SKILL.md skills table...")
    table = build_skill_table(skills)
    replace_between_markers(API_SKILL_MD, table, dry_run=args.dry_run)

    print("\nUpdating CLAUDE.md skills list...")
    bullet_list = build_claude_list(skills)
    replace_between_markers(CLAUDE_MD, bullet_list, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
