---
name: nod-brief-builder
description: |
  Turn a user-provided keyword LIST into content briefs. Clusters the list (each
  cluster = one candidate page), maps every keyword to its target page with a
  primary/secondary split, then generates one content brief per cluster. Mostly
  orchestration — it reuses nod-serp-clusters for clustering and nod-content-brief
  for per-cluster research. Use when the user says "brief from keyword list,"
  "briefs for these keywords," "turn keyword list into briefs," "map keywords to
  pages," "content plan from keywords," or "brief builder." For a single seed
  keyword use nod-content-brief instead. Requires NODESHUB_API_KEY (non-demo).
compatibility: "Requires Python 3.9+, NODESHUB_API_KEY (and OPENROUTER_API_KEY for clustering); --demo runs fully offline with no keys"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Brief Builder

**First action — run the banner:**
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Brief Builder')"
```

You take a keyword list the user already has (from a client, or a content-gap
export) and turn it into a content plan: clusters → keyword-to-page mapping →
one brief per cluster.

This skill is mostly orchestration. It does not reinvent clustering or brief
research — it reuses two existing skills:

- **nod-serp-clusters** — clusters the keyword list. The SERP method imports
  `run_clustering` directly; the semantic method runs `cluster_semantic.py`.
- **nod-content-brief** — for each cluster it reuses `research.py` (SERP +
  Query Fan-out) on the cluster's primary keyword.

For a single seed keyword that you want to expand into one brief, use
**nod-content-brief** directly — this skill is for a whole list.

## Quick Start

```bash
# From a file (one keyword per line), SERP clustering
python3 .claude/skills/nod-brief-builder/scripts/build.py --file keywords.txt --method serp --gl us --hl en

# From an inline list, cap the number of briefs
python3 .claude/skills/nod-brief-builder/scripts/build.py --keywords "crm software,best crm,crm pricing" --max-briefs 3

# Semantic clustering (no NodesHub tokens for the clustering step)
python3 .claude/skills/nod-brief-builder/scripts/build.py --file keywords.txt --method semantic

# Clustering + mapping only, no briefs (cheapest preview)
python3 .claude/skills/nod-brief-builder/scripts/build.py --file keywords.txt --dry-run

# Mocked demo — no API keys, fabricated research, clearly labelled
python3 .claude/skills/nod-brief-builder/scripts/build.py --demo
```

## Setup

For non-demo runs you need `NODESHUB_API_KEY` (SERP + Fan-out), and for clustering
also `OPENROUTER_API_KEY` (cluster naming, and embeddings for the semantic method).

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

**If NodesHub is not set up:** run `/connect-nodeshub`.
**If OpenRouter is not set up:** run `/connect-openrouter`.

`--demo` needs no keys at all — it uses a built-in keyword list with mocked
clustering and mocked research, so the pipeline is testable offline.

## Workflow (3 steps)

1. **Cluster** the input list with nod-serp-clusters (`--method serp` default, or
   `--method semantic`). Each resulting cluster is a candidate page.
2. **Map** every input keyword to its cluster. Pick a primary keyword per cluster
   (highest volume when available, otherwise the first keyword); the rest become
   secondary targets for the same page. Produces a clear keyword-to-page mapping.
3. **Brief** — for each cluster (up to `--max-briefs`), reuse nod-content-brief's
   research on the primary keyword and fold the secondary keywords into the brief
   as same-page targets.

## Output

Artifacts are written per run to `data/briefs/{slug}/`:

- `mapping.json` — the full keyword → cluster → page mapping (pages with primary
  and secondary keywords, plus a reverse keyword index).
- `brief-{slug}.md` — one content brief per cluster.

The script also prints a readable summary: clusters found, the keyword-to-page
mapping, and the briefs generated.

## Cost

- **Clustering — SERP method:** 1 NodesHub token per input keyword.
- **Clustering — semantic method:** no NodesHub tokens (OpenRouter embeddings only).
- **Each brief:** ~8.5 NodesHub tokens (standard mode) or ~31 (reasoning mode).

Example: 60 keywords, SERP clustering, 10 briefs (standard) ≈ 60 + 85 ≈ 145 tokens.

Cost controls:
- `--dry-run` does clustering + mapping only (clustering cost, no brief cost).
- `--max-briefs N` caps how many briefs are generated.
- `--demo` spends nothing — all data is mocked and labelled as such.

## Related Skills

- **nod-content-brief** — single-seed briefs. Use it when you have one keyword,
  not a list. This skill calls its `research.py` under the hood.
- **nod-serp-clusters** — standalone keyword clustering (SERP or semantic). This
  skill reuses its `run_clustering` / `cluster_semantic.py`.
- **nod-keyword-research** — generate a keyword list to feed into this skill.
