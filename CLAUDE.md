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
- `/nod-aio` - aI Overview (GEO/AEO) visibility for a keyword set, plus a brief-under-AIO recommendation
- `/nod-alerting` - turns one-off SEO snapshots into monitoring
- `/nod-brand-split` - deterministically split Google Search Console demand into BRANDED vs NON-BRANDED queries, so you can see how much traffic is people who already know the brand versus genuine new acquisition
- `/nod-brief-builder` - turn a user-provided keyword LIST into content briefs
- `/nod-cannibalization` - deterministic keyword cannibalization detector that runs on Google Search Console data
- `/nod-commercial-value` - deterministically rank a keyword set by REVENUE potential, not by traffic
- `/nod-competitor-tracker` - track competitor domains across keyword sets using NodesHub SERPdata API
- `/nod-content-auditor` - audit existing content against current SERP reality using NodesHub SERPdata, Query Fan-out APIs, and Jina Reader for competitor page crawling
- `/nod-content-brief` - generates data-driven SEO content briefs using NodesHub SERPdata and Query Fan-out APIs
- `/nod-content-gap` - classic content/keyword gap analysis: the keywords your competitors rank for that you don't (or rank worse for)
- `/nod-demand-trajectory` - year-over-year demand trajectory for a keyword set: decide whether each keyword/topic is Rising, Stable, or Declining so you know where to invest and where to exit
- `/nod-featured-snippet-hunter` - find Featured Snippet and Answer Box opportunities by analyzing Google SERPs using NodesHub SERPdata API
- `/nod-intent-roi` - ties search intent to actual conversions so content is prioritized by ROI, not by traffic volume
- `/nod-keyword-research` - expand seed keywords into comprehensive keyword lists using NodesHub Query Fan-out API
- `/nod-merger` - merge Google Search Console + Google Analytics 4 + Google Ads into one clean funnel dataset keyed by URL (and by query where available)
- `/nod-money-keywords` - find the expensive paid terms you could win organically to cut your customer acquisition cost (CAC)
- `/nod-nodeshub-api` - shared NodesHub API client for SEO automation skills
- `/nod-opportunity-detector` - deterministic SEO opportunity engine
- `/nod-paa-miner` - mine "People Also Ask" questions from Google SERPs for a list of keywords using NodesHub SERPdata API
- `/nod-paid-organic` - marketing-grade overlap analysis between paid (Google Ads) and organic (GSC) for the same keywords
- `/nod-rank-tracker` - track keyword ranking positions for a domain over time using NodesHub SERPdata API
- `/nod-seasonality` - build ONE site-level seasonality curve from your keyword set so you can see when demand peaks, when to publish, and how to diversify away from a single annual spike
- `/nod-serp-analysis` - analyze Google SERP for any keyword using NodesHub SERPdata API
- `/nod-serp-clusters` - cluster keywords by SERP similarity — keywords sharing the same Google results belong to the same cluster
- `/nod-share-of-search` - track Share of Search (Les Binet): your brand's search demand as a percentage of the total brand search demand in your category, measured month over month
- `/nod-visibility-monitor` - calculate SEO visibility score for a domain using weighted keyword positions via NodesHub SERPdata API
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
