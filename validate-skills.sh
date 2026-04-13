#!/usr/bin/env bash
# Validate all skills against the Agent Skills specification.
# Usage: bash validate-skills.sh

set -euo pipefail

SKILLS_DIR=".claude/skills"
ERRORS=0
WARNINGS=0
CHECKED=0

red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }

error()   { red   "  ERROR: $*"; ((ERRORS++)); }
warning() { yellow "  WARN:  $*"; ((WARNINGS++)); }
ok()      { green  "  OK:    $*"; }

echo "=== Validating skills in ${SKILLS_DIR}/ ==="
echo ""

for skill_dir in "${SKILLS_DIR}"/*/; do
  dir_name=$(basename "$skill_dir")
  skill_file="${skill_dir}SKILL.md"
  ((CHECKED++))

  echo "--- ${dir_name} ---"

  # 1. SKILL.md exists
  if [[ ! -f "$skill_file" ]]; then
    error "Missing SKILL.md"
    continue
  fi
  ok "SKILL.md exists"

  # 2. Has YAML frontmatter
  if ! head -1 "$skill_file" | grep -q '^---'; then
    error "Missing YAML frontmatter (no opening ---)"
    continue
  fi

  # 3. Extract name field
  name=$(awk '/^---$/{n++; next} n==1 && /^name:/{sub(/^name: */, ""); print; exit}' "$skill_file")
  if [[ -z "$name" ]]; then
    error "Missing 'name' field in frontmatter"
  elif [[ "$name" != "$dir_name" ]]; then
    error "Name mismatch: name='${name}' but dir='${dir_name}'"
  else
    ok "Name matches directory"
  fi

  # 4. Name format: lowercase, numbers, hyphens only
  if [[ -n "$name" ]]; then
    if ! echo "$name" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
      error "Name '${name}' violates naming rules (lowercase, numbers, hyphens only, no leading/trailing hyphens)"
    fi
    if echo "$name" | grep -q '\-\-'; then
      error "Name '${name}' contains consecutive hyphens"
    fi
    if [[ ${#name} -gt 64 ]]; then
      error "Name '${name}' exceeds 64 characters"
    fi
  fi

  # 5. Has description
  desc=$(awk '/^---$/{n++; next} n==1 && /^description:/{sub(/^description: */, ""); print; exit}' "$skill_file")
  if [[ -z "$desc" ]]; then
    # Check for multi-line description (description: |)
    desc=$(awk '/^---$/{n++; next} n==1 && /^description: *\|/{print; exit}' "$skill_file")
    if [[ -z "$desc" ]]; then
      error "Missing 'description' field in frontmatter"
    else
      ok "Description present (multi-line)"
    fi
  else
    ok "Description present"
  fi

  # 6. Check for evals (warning only)
  if [[ ! -f "${skill_dir}evals/evals.json" ]]; then
    warning "No evals/evals.json"
  else
    ok "Evals present"
  fi

  # 7. Check for scripts (info only for nod- skills)
  if [[ "$dir_name" == nod-* ]] && [[ ! -d "${skill_dir}scripts" ]]; then
    warning "nod- skill without scripts/ directory"
  fi

  echo ""
done

echo "=== Results ==="
echo "Checked: ${CHECKED} skills"
green "Passed checks (no errors): $((CHECKED - ERRORS))"
[[ $WARNINGS -gt 0 ]] && yellow "Warnings: ${WARNINGS}"
[[ $ERRORS -gt 0 ]] && red "Errors: ${ERRORS}"

exit $((ERRORS > 0 ? 1 : 0))
