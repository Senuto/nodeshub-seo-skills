# Nodeshub SEO Skills - Best Practices

## Local instructions

**IMPORTANT:** If a file `CLAUDE.local.md` exists, Claude MUST read it at the start of each session. It contains private user instructions.

## Working rules

- Always humanize texts - avoid artificial, "AI-like" tone
- Do not use emojis in copy (unless the client explicitly asks)
- Write in English by default
- Before writing SEO content, always read product context

## Missing setup (NodesHub / GSC)

**If NodesHub is not set up** (no API key or `check_setup.py` fails): Use the **/connect-nodeshub** skill for a step-by-step guided setup, or follow the steps in each nod- skill's Setup section and `.claude/skills/nod-nodeshub-api/setup/README.md`.

For GSC setup, use the **/connect-gsc** skill.

For GA4 setup, use the **/connect-ga4** skill.

## Banner

**IMPORTANT:** When **any** skill is invoked (with or without the `nod-` prefix — e.g. `/nod-serp-analysis`, `/connect-nodeshub`, `/connect-gsc`, `/skill-creator`, or any future skill), Claude MUST run the banner as the first action:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('SKILL_NAME')"
```
Replace `SKILL_NAME` with the human-readable skill name (e.g. "Content Brief", "SERP Analysis", "Connect NodesHub", "Connect GSC", "Skill Creator").

## Product context

**INSTRUCTION FOR CLAUDE:** Before any task related to SEO content, briefs, or analysis, Claude MUST read the following files:
- docs/product.md
- docs/audiences.md
- docs/voice-tone.md
- docs/competitors.md
- docs/proof-points.md
- docs/brand-guidelines.md

## Available skills

### Nodeshub SEO (nod-)
<!-- SKILLS:START -->
- `/nod-serp-analysis` - Analyze Google SERP for any keyword: extracts top 10 organic results, SERP features (PAA, AI Overview, Knowledge Panel, Local Pack, Videos), competitor domains, and detects dominant search intent. Starting point for most SEO tasks. Cost: 1 token/keyword.
- `/nod-keyword-research` - Discover keywords using iterative SERP mining (PAA + Related Searches loops) and AI-powered query expansion (Fan-out). Outputs a deduplicated CSV with source tracking and serp_overlap scores for prioritization. Presets from conservative (~22 tokens, 50-150 kws) to beast (~637 tokens, 1000-3000+ kws).
- `/nod-serp-clusters` - Group keywords by SERP similarity — keywords sharing the same Google results land in the same cluster (Weighted Jaccard + Louvain algorithm). Generates an interactive D3.js dendrogram report. Use after keyword research to plan content architecture. Cost: 1 token/keyword + OpenRouter for cluster naming.
- `/nod-content-brief` - Generate a data-driven content brief: combines SERP analysis (top 10 competitors, features, intent) with keyword expansion (related queries, questions) into a ready-to-write outline with suggested headings, target keywords, and content angle. Cost: ~8.5 tokens.
- `/nod-content-auditor` - Audit existing content against live SERP data. Crawls top competitors via Jina Reader, compares keyword/topic coverage, identifies content gaps, missing questions, and heading patterns your page lacks. Provide `--url` for gap comparison. Cost: ~8.5 tokens + Jina (free).
- `/nod-rank-tracker` - Track keyword ranking positions for your domain over time. Saves daily JSON snapshots, compares with previous run (position changes, new/lost rankings, top 3/10 counts). Cost: 1 token/keyword.
- `/nod-visibility-monitor` - Calculate a weighted SEO visibility score (0-100%) for your domain based on keyword positions. Compares against competitor domains. Tracks trends across daily snapshots. Cost: 1 token/keyword.
- `/nod-competitor-tracker` - Discover and monitor which domains rank for your target keywords. Shows domain frequency across all keywords, average positions, and a keyword×domain matrix. Saves snapshots for change comparison. Cost: 1 token/keyword.
- `/nod-featured-snippet-hunter` - Find Featured Snippet / Answer Box opportunities for your domain. Classifies each keyword as steal (you rank but don't own snippet), defend (you own it), target (you're not in top 10), or no snippet. Cost: 1 token/keyword.
- `/nod-paa-miner` - Mine "People Also Ask" questions from Google SERPs for a list of keywords. Deduplicates across keywords, tracks which keyword each question came from, and optionally clusters questions by topic via OpenRouter LLM. Cost: 1 token/keyword.
- `/nod-intent-classifier` - Classify search intent (informational, commercial, transactional, navigational) from real SERP signals like PAA presence, ads, shopping results, and title patterns. Cost: 1 token/keyword.
- `/nod-nodeshub-api` - Shared API client, setup, and balance check. Other nod- skills import from this module. Use directly to check token balance, test API connectivity, or troubleshoot.
<!-- SKILLS:END -->

### Content quality
- `/ai-score` - Check if text is AI-generated using Genuino API. Returns AI probability score (0-100%), writing style classification, and actionable humanization guidelines with specific rewrite instructions. Supports text, files, and URLs. Cost: Genuino credits.

### Agents (sub-agents / orchestrators)
- **topic-planner** - End-to-end topic research pipeline: seed keyword → iterative keyword research → SERP clustering (or semantic) → competitor crawl → content briefs for top clusters. Resumable from any step. (`.claude/agents/topic-planner/`)
- **keyword-to-publish** - Full article creation pipeline: keyword research → SERP analysis → data-driven brief → LLM writes article → Genuino AI score check + iterative humanization → content audit vs competition. Outputs publish-ready article. (`.claude/agents/keyword-to-publish/`)
- **content-humanizer** - Iterative AI content humanization: Genuino score check → identify flagged sections → LLM rewrites only those sections → re-check → loop until AI probability drops below threshold (default 30%) or max iterations reached. (`.claude/agents/content-humanizer/`)

### Utilities
- `/guide` - Interactive onboarding — explains all available skills and agents, helps you pick the right one based on your goal, shows example workflows.
- `/connect-nodeshub` - Step-by-step NodesHub API connection: get key from nodeshub.io, save to settings, verify with test call.
- `/connect-openrouter` - Step-by-step OpenRouter API connection: needed for SERP clustering (cluster naming) and PAA question clustering.
- `/connect-genuino` - Step-by-step Genuino API connection: needed for AI content detection (`/ai-score` and content-humanizer agent).
- `/connect-gsc` - Step-by-step Google Search Console connection: OAuth credentials setup for GSC data (queries, impressions, clicks).
- `/connect-ga4` - Step-by-step Google Analytics 4 connection: OAuth credentials setup for GA4 data (pageviews, sessions, events).
- `/skill-creator` - Scaffold a new skill: creates SKILL.md, scripts/, evals/ directory structure, and auto-syncs the skills registry in CLAUDE.md.

## Git workflow

### Commit convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

**Types:**
- `feat` - new functionality or content
- `fix` - bug fix
- `docs` - documentation changes
- `style` - formatting, no logic changes
- `refactor` - code/content refactoring
- `chore` - configuration, tooling changes

**Examples:**
```bash
git commit -m "feat(serp): add local pack extraction to SERP analysis"
git commit -m "fix(rank-tracker): fix date handling in snapshot comparison"
git commit -m "docs(context): update competitor analysis"
```

### Workflow

1. Before work: `git pull origin main`
2. Make changes
3. Add files: `git add <files>` (avoid `git add .`)
4. Commit: `git commit -m "type(scope): description"`
5. Push: `git push origin main`

### Rules

- Commit often, small changes
- Describe WHAT and WHY, not HOW
- Do not commit sensitive data (API keys, passwords)
- Before push check `git status` and `git diff`
- **After major commits update `CHANGELOG.md`**
  - Version date = date of last change (not first)
  - When adding entries to an existing version, update the date to today
