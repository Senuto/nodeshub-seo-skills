> By cloning or downloading this repository you accept the terms described in [TERMS-OF-USE.md](TERMS-OF-USE.md).

# NodesHub SEO Skills – documentation

A set of skills for SEO automation, built on the NodesHub API (live Google SERP data) and optionally OpenRouter (LLM for cluster naming and brief generation).

The toolkit consists of two layers:

- **Skills layer (SKILL.md)** – Native integration with Claude Code. Type something like `/nod-serp-analysis` and Claude automatically knows what to do: it runs the script, analyzes the results, and returns a formatted report. Slash commands, automatic context, intent recognition – this only works in Claude Code.
- **Python scripts layer** – Fully standalone. Each skill has scripts that can be run from any terminal, CI pipeline, or other AI tool (Gemini CLI, Cursor, Aider). Just set your API key.

SERP data is fetched live from Google (not from a historical database), so results reflect the current state of search.

## What this repository is

This repository is a promotional package created by Senuto to demonstrate the capabilities of the NodesHub platform. It is a collection of instructions (SKILL.md files), Python scripts, and configuration templates that extend Claude Code – Anthropic's AI terminal tool – with SEO-related functionality.

It is not a standalone application. It is an add-on layer for Claude Code that connects to the NodesHub API for data. Here is how it works step by step:

1. The user installs Claude Code (a paid Anthropic product).
2. The user downloads this repository to their computer or server from the public GitHub repository.
3. The user navigates to the repository folder in their terminal.
4. The user types commands such as `/nod-serp-analysis "keyword"` – Claude Code reads the included instructions and performs the analysis in a defined way.
5. In the background, Python scripts connect to the NodesHub API to fetch SERP data, and Claude Code interprets and presents the results.
6. To use the full capabilities of the repository, the user must separately purchase a NodesHub plan and provide their NodesHub API key to Claude Code.
7. Everything runs locally on the user's computer – no server is involved, and no user data is stored by Senuto or NodesHub.

## What is NodesHub?

[NodesHub](https://nodeshub.io/) is a SERP data API built by [Senuto](https://senuto.com/). It fetches Google search results in real time and returns them as structured JSON. Instead of building your own scraper (and dealing with proxies, CAPTCHAs, rate limits, and constant maintenance), you make one API call and get back everything Google shows for a given query: organic results, featured snippets, People Also Ask, AI Overviews, Knowledge Graph panels, Local Pack, Videos, Top Stories, ads, and more.

NodesHub exposes three main endpoints:

- **SERPdata API** — the core endpoint. Returns the full Google SERP for any keyword, in any country and language. One call = one token. You get the top 10 organic results, all SERP features present on the page, and metadata like search volume signals and result types.
- **Query Fan-out** — takes a seed keyword and expands it into 15–20 related queries, questions, and long-tail variations using AI. Useful for keyword research and topical mapping. One call = 7.5 tokens (standard) or 30 tokens (reasoning mode for higher quality).
- **Intent Classifier** — analyzes the actual SERP (not the keyword text) to determine whether a query is informational, commercial, transactional, or navigational. Returns a percentage confidence score for each category. One call = 2 tokens.

All data is live — fetched from Google at the moment you make the request, not pulled from a historical database. This means results always reflect the current state of search.

NodesHub is pay-as-you-go with no subscription required. New users receive **100 free tokens on sign-up** — enough to run a full keyword research session, several SERP analyses, or a content brief. API keys are available in the [NodesHub Playground](https://nodeshub.io/).

## Installation

### A) npx (recommended) – installs skills into an existing project:

```bash
npx nodeshub-seo-skills
```

### B) Clone the repo:

```bash
git clone https://github.com/Senuto/nodeshub-seo-skills.git
```

## Requirements

- **Claude Code** – for full integration (slash commands, automatic context). Alternatively, scripts can be run manually from any terminal.
- **Python 3.9+** – to run the scripts.
- **NodesHub API key** – to fetch SERP data (free 100 tokens included upon registration). Required for most skills.
- **OpenRouter API key** – required for SERP Clusters (naming), PAA Miner (clustering), and Topic Planner (briefs). Not required for other skills.
- **Genuino API key** (optional) – required for AI Score, Keyword to Publish, and Content Humanizer.
- **Jina API key** (optional) – for crawling competitor pages in Topic Planner and for URL-based AI Score analysis.

## Configuration (one-time setup)

### Connecting NodesHub

1. Go to [nodeshub.io](https://nodeshub.io) and scroll to the API Playground section.
2. Click "Copy to clipboard" to copy your API key.
3. Save the key using one of three methods:
   - **Via Claude Code:** type `/connect-nodeshub` and enter your key.
   - **Manually:** run `python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py YOUR_KEY`.
   - **Environment variable:** `export NODESHUB_API_KEY=YOUR_KEY`.

The key is saved to `.claude/settings.local.json` (this file is in `.gitignore`).

**Verification:**
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

### Connecting OpenRouter (optional)

1. Go to [openrouter.ai/keys](https://openrouter.ai/keys) and generate a key.
2. Run:
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/save_openrouter_key.py YOUR_KEY
```

Or type `/connect-openrouter` in Claude Code for a guided setup.

### Connecting Genuino (optional)

1. Go to [genuino.ai](https://genuino.ai) and obtain an API key.
2. Save the key:
```bash
python3 -c "
import json; from pathlib import Path
p = Path('.claude/settings.local.json')
cfg = json.loads(p.read_text()) if p.exists() else {'env': {}}
cfg['env']['GENUINO_API_KEY'] = 'YOUR_KEY'
p.write_text(json.dumps(cfg, indent=2))
print('Genuino key saved.')
"
```

Or type `/connect-genuino` in Claude Code for a guided setup.

### Connecting Google Search Console (optional)

Type `/connect-gsc` in Claude Code – it will walk you through the setup step by step. Requires a Google Cloud account and a Service Account with access to GSC. The JSON key is saved as `local/gsc-credentials.json`.

### Connecting Google Analytics 4 (optional)

Type `/connect-ga4` in Claude Code – it will walk you through the setup step by step. Requires a Google Cloud account and a Service Account with access to GA4. The JSON key is saved as `local/ga4-credentials.json`.

## Tokens (costs)

Each NodesHub API call costs tokens. New users receive 100 free tokens upon registration. Genuino features are billed separately in Genuino credits.

**Check your balance:**
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/balance.py
```

| Operation | Cost |
|---|---|
| Fetch SERP (1 keyword) | 1 token |
| Query Fan-out standard (1 keyword) | 7.5 tokens |
| Query Fan-out reasoning (1 keyword) | 30 tokens |
| Intent Classifier | 2 tokens per keyword |
| Content Brief / Audit | ~8.5 tokens |
| AI Score (Genuino) | 1 Genuino credit (base) + optional 2 for guidelines + 2 for humanization prompt |
| Check balance | 0 |
| List countries/languages | 0 |

## Skills – overview

### Research & analysis

#### 1. SERP Analysis (`/nod-serp-analysis`)

Fetches and analyzes the top 10 Google results for a given keyword.

**What you get:**
- A list of 10 organic results (domain, title, content type).
- SERP features present (PAA, AI Overview, Knowledge Panel, Local Pack, Videos).
- Search intent classification (informational / commercial / transactional / navigational).
- Gaps in the results – what's missing from the current top 10.
- Recommendations.

**Cost:** 1 token per keyword.

**When to use:** When you want to see who's ranking for a keyword, which SERP features appear, and what the competitive landscape looks like. A good starting point for most SEO analyses.

**Example (Claude Code):**
```
/nod-serp-analysis
> Analyze the SERP for "website SEO" gl=us hl=en
```

**Example (terminal):**
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/serpdata.py "website SEO" --gl us --hl en
```

#### 2. Keyword Research (`/nod-keyword-research`)

Expands a single seed keyword into a full list of related phrases, questions, long-tail variants, and topic clusters.

**Two modes:**

**A) Iterative Research (recommended)** – fetches the SERP for the seed, extracts PAA questions and related searches, then repeats the process for the discovered phrases – and so on in a loop. The result: hundreds to thousands of keywords.

| Preset | Loops | Cost | Keywords |
|---|---|---|---|
| conservative | 3 | ~22 tokens | 50–150 |
| standard | 5 | ~72 tokens | 150–400 |
| aggressive | 15 | ~262 tokens | 400–1,000+ |
| beast | 30 | ~637 tokens | 1,000–3,000+ |

**B) Simple Fan-out** – a single API call returning related phrases, questions, and variants. Faster, but shallower.

**Fan-out cost:** 7.5 tokens (standard) / 30 (reasoning).

**Output:** A CSV file with columns: `keyword`, `source`, `type`, `discovered_in_loop`, `serp_overlap` (how many times the keyword appeared across different SERPs – the higher the count, the more important the keyword).

**When to use:** When planning content, looking for topics to write about, or building a topical map.

#### 3. SERP Clusters (`/nod-serp-clusters`)

Groups a list of keywords based on the similarity of their Google results. If two keywords share similar top-10 results, they end up in the same cluster – meaning they can be covered by a single page.

**Two clustering methods:**

**A) SERP-based (default)** – compares Google results across keywords (Weighted Jaccard + Louvain). Cost: 1 token per keyword.

**B) Semantic** – groups keywords by meaning using an LLM. Cost: 0 NodesHub tokens, only OpenRouter.

**Cluster levels:**
- `--levels 1` – single layer (default).
- `--levels 2` – broad + detailed.
- `--levels 3` – broad + medium + detailed (e.g., silo → subtopic → page).

**Reports:**
- `--report html` – interactive D3.js dendrogram, domain tables, SERP features.
- `--report md` – the same in Markdown.

**Cost:** 1 NodesHub token per keyword + minimal OpenRouter costs (naming).

**When to use:** When you have a list of keywords and want to know which ones can be combined on a single page and which require separate subpages.

**Requires:** NodesHub key + OpenRouter key.

#### 4. Intent Classifier (`/nod-intent-classifier`)

Classifies search intent based on SERP signals – not on the phrase itself, but on what Google actually shows.

**Four categories:**
- **Informational** – the user is looking for knowledge (PAA, AI Overview, how-to guides).
- **Commercial** – comparing options (reviews, "best X", ads).
- **Transactional** – ready to buy (Shopping, prices, products).
- **Navigational** – looking for a specific page (brand ranked #1).

Each keyword receives a percentage confidence score.

**Cost:** 2 tokens per keyword.

**When to use:** When you have a list of keywords and want to match the content type to the intent – e.g., an informational guide for informational queries, a product page for transactional ones.

#### 5. PAA Miner (`/nod-paa-miner`)

Extracts "People Also Ask" questions from Google for a list of keywords, deduplicates them, and optionally clusters them by topic using an LLM.

**What you get:**
- A bank of unique questions with information about which keywords they appeared for.
- Optional grouping of questions into topics (requires OpenRouter).

**Cost:** 1 token per keyword + optional OpenRouter for clustering.

**When to use:** When building a FAQ section, looking for questions to answer in your content, or planning an article's structure.

#### 6. Featured Snippet Hunter (`/nod-featured-snippet-hunter`)

Finds Featured Snippet (position zero) opportunities for your domain.

**Classifies opportunities as:**
- **Steal** – a snippet exists, you rank in the top 10, but don't own the snippet (best opportunity).
- **Defend** – you own the snippet; monitor it.
- **Target** – a snippet exists, but you're not in the top 10 (harder to win).
- **No snippet** – no answer box present.

**Cost:** 1 token per keyword.

**When to use:** When you want to win Featured Snippets or defend the ones you already have.

### Tracking & monitoring

#### 7. Rank Tracker (`/nod-rank-tracker`)

Checks where your domain ranks for given keywords. Saves snapshots and compares changes over time.

**Output:** A table with positions, changes (up/down), and the URLs that are ranking.

**Data saved to:** `data/rank-history/{domain}/{YYYY-MM-DD}.json`

**Cost:** 1 token per keyword.

**When to use:** When you want to monitor ranking changes. Recommended frequency: once a week (positions don't change hour by hour).

#### 8. Competitor Tracker (`/nod-competitor-tracker`)

Shows who is ranking for your target keywords. Displays domain frequency in the top 10, average positions, and a keyword × domain matrix.

**Key difference vs. Rank Tracker:** Rank Tracker monitors your domain. Competitor Tracker shows everyone ranking (or specific domains via `--watch`).

**Cost:** 1 token per keyword.

**When to use:** When you want to know who your competition is for specific keywords and who is gaining or losing ground.

#### 9. Visibility Monitor (`/nod-visibility-monitor`)

Calculates an SEO visibility score for a domain based on weighted positions. Position #1 = 10 pts, #2 = 9, ..., #8–10 = 2, outside top 10 = 0. The score is expressed as a percentage of the maximum possible visibility.

You can benchmark against competitors – add competitor domains and see who has greater visibility across a given keyword set.

**Cost:** 1 token per keyword.

**When to use:** When you need a single number that says "how visible is my site" and want to compare it against competitors. Useful for reporting.

### Content

#### 10. Content Brief (`/nod-content-brief`)

Generates a complete content brief for writing an article. Combines SERP data (who ranks, what content dominates) with keyword expansion (related phrases, questions) to produce a comprehensive plan.

**The brief includes:**
- Primary and secondary keywords.
- Analysis of the top 5 competitors (strengths, gaps).
- Suggested heading structure (H1, H2, H3).
- Questions to answer (from PAA and fan-out).
- Requirements: length, must-cover topics, schema, meta tags.
- An SEO checklist.

**Cost:** ~8.5 tokens (standard) / ~31 (reasoning) per brief.

**When to use:** When you know which keyword you want to target and need a content plan.

#### 11. Content Auditor (`/nod-content-auditor`)

Audits an existing page against current Google results and identifies what's missing compared to what's ranking.

**What you get:**
- Missing keywords, questions, and topics.
- Content gaps vs. the competition.
- Recommendations: what to add, what to improve, and in what order.

**Cost:** ~8.5 tokens (standard) / ~31 (reasoning).

**When to use:** When you have an existing article and want to optimize or refresh it.

### Content quality

#### 12. AI Score (`/ai-score`)

Analyzes text for the probability of being AI-generated using the Genuino API.

**What you get:**
- AI probability score (0–100%).
- Writing style classification.
- Optional humanization guidelines: which sections sound most artificial and why.
- Optional humanization prompt: rewrite instructions for flagged sections.

Supports three input methods: text files, inline text (minimum 200 words), and URLs (fetched via Jina Reader).

**Cost:** 1 Genuino credit per analysis. +2 credits for guidelines. +2 credits for humanization prompt.

**Requires:** Genuino API key. Jina API key optional (for URL analysis).

**When to use:** After writing or generating content, before publishing – to verify the text reads as human-written. Also useful for auditing existing published content.

**Example (Claude Code):**
```
/ai-score
> Check this article: article.txt
```

**Example (terminal):**
```bash
python3 .claude/skills/ai-score/scripts/analyze.py --file article.txt --guidelines
```

## Agents

Agents are orchestrators that compose multiple skills into end-to-end pipelines. Unlike skills (single-purpose tools), agents run multi-step workflows with user interaction between steps. Each agent saves progress per step and can be resumed from any point.

### Topic Planner

Orchestrates the entire pipeline from a seed keyword to finished content briefs. Combines three steps into a single run with progress reporting between stages:

1. **Keyword Research** – collects keywords (iterative research).
2. **Clustering** – groups keywords (SERP-based or semantic).
3. **Content Briefs** – crawls competitors (Jina) and generates briefs (OpenRouter).

**Resumable** – each step saves its results to `data/topics/[slug]/`. You can stop and pick up where you left off.

**Cost:** ~25 tokens (keywords) + ~1 token/keyword (clustering) + OpenRouter (briefs).

**Requires:** NodesHub key + OpenRouter key. Jina is optional.

**When to use:** When you want to go from a topic to finished briefs in a single pass.

### Keyword to Publish

Runs the full pipeline from a seed keyword to a publish-ready article:

1. **Keyword Research** – discovers related keywords.
2. **SERP Analysis** – analyzes the competitive landscape.
3. **Content Brief** – generates a writing plan.
4. **Article Writing** – Claude writes the article based on the brief.
5. **AI Score Check** – Genuino verifies the text reads as human-written. If the score exceeds the threshold, Claude rewrites flagged sections and rechecks.
6. **Content Audit** – compares the final article against the competition.

Saves all artifacts to `data/articles/[slug]/`.

**Cost:** ~40–80 NodesHub tokens + Genuino credits.

**Requires:** NodesHub key + Genuino key. OpenRouter and Jina optional.

**When to use:** When you want to go from a keyword to a finished, human-sounding article in a single session.

### Content Humanizer

Iteratively rewrites AI-generated text until it passes AI detection:

1. Analyzes the text with Genuino – identifies AI probability and flagged sections.
2. Rewrites only the flagged sections – the rest stays untouched.
3. Re-checks the score – repeats until AI probability drops below the threshold.
4. Stops after a maximum of 3 iterations to avoid infinite loops.

**Cost:** 1–3 Genuino credits per iteration (depending on options).

**Requires:** Genuino key.

**When to use:** When you have AI-generated content that needs to sound human before publishing.

## Common use cases

**Scenario 1: Planning new content (manual)**
1. `/nod-keyword-research` – collect keywords (standard preset).
2. `/nod-serp-clusters` – group keywords into clusters.
3. `/nod-content-brief` – create a brief for each cluster.
4. Write content based on the briefs.

**Scenario 1b: Planning new content (automated)**
- `/topic-planner` – provide a seed keyword; the agent handles everything.

**Scenario 2: Optimizing existing content**
1. `/nod-content-auditor` – identify what's missing vs. the competition.
2. Update the content based on recommendations.
3. `/nod-rank-tracker` – monitor ranking changes after publishing.

**Scenario 3: Competitive analysis**
1. `/nod-competitor-tracker` – see who ranks for your keywords.
2. `/nod-visibility-monitor` – compare your visibility against competitors.
3. `/nod-serp-analysis` – dive deeper into specific phrases.

**Scenario 4: Quick reconnaissance**
1. `/nod-serp-analysis` – check who ranks and what the SERP looks like.
2. `/nod-intent-classifier` – determine which content type fits the intent.

**Scenario 5: Winning Featured Snippets**
1. `/nod-featured-snippet-hunter` – find snippet opportunities.
2. `/nod-paa-miner` – collect PAA questions for a FAQ section.
3. Optimize content for snippets (lists, tables, definitions).

**Scenario 6: Writing an article from scratch (automated)**
- `/keyword-to-publish` – provide a seed keyword; the agent handles research, writing, AI check, and audit.

**Scenario 7: Humanizing AI content**
1. `/ai-score` – check the current AI probability.
2. `/content-humanizer` – if the score is too high, the agent rewrites flagged sections automatically.

## Shared parameters

Most skills accept the same parameters:

| Parameter | Description | Example |
|---|---|---|
| `--gl` | Country code (Google geolocation) | `pl`, `us`, `de`, `uk` |
| `--hl` | Language code (Google host language) | `pl`, `en`, `de` |
| `--device` | Device type | `desktop`, `mobile` |
| `--file` | File with keywords (one per line) | `keywords.txt` |
| `--raw` | Return raw JSON | – |
| `--compare` | Compare with previous snapshot | – |

**List all country and language codes:**
```bash
python3 .claude/skills/nod-nodeshub-api/scripts/params.py countries
python3 .claude/skills/nod-nodeshub-api/scripts/params.py languages
```

## Where data is stored

All output is saved under the `output/` folder (gitignored – data accumulates between sessions).

| Skill | Path |
|---|---|
| Rank Tracker | `output/data/rank-history/{domain}/{YYYY-MM-DD}.json` |
| Competitor Tracker | `output/data/competitor-tracking/{YYYY-MM-DD}.json` |
| Visibility Monitor | `output/data/visibility/{domain}/{YYYY-MM-DD}.json` |
| Keyword Research | `output/data/keywords/` |
| PAA Miner | `output/data/paa/{slug}_{date}.json` |
| Content Brief | `output/data/briefs/{slug}.md` |
| SERP cache (shared) | `output/data/serp-cache/{gl}-{hl}/{keyword}.json` |
| Topic Planner | `output/data/topics/{slug}/` (keywords, clusters, briefs) |
| Keyword to Publish | `output/data/articles/{slug}/` (keywords, SERP, brief, drafts, final article) |
| HTML / Markdown reports | `output/reports/` |

## Infrastructure & setup

The following setup commands and utilities are available in Claude Code:

- `/connect-nodeshub` – guided NodesHub API setup (SERP data)
- `/connect-openrouter` – guided OpenRouter API setup (LLM for clustering and briefs)
- `/connect-genuino` – guided Genuino API setup (AI content detection)
- `/connect-gsc` – guided Google Search Console setup
- `/connect-ga4` – guided Google Analytics 4 setup
- `/guide` – interactive onboarding: explains what's available and routes you to the right skill based on your goal
- `/skill-creator` – scaffold a new skill with the correct directory structure and auto-register it

## Brand context (docs/ folder)

The `docs/` folder contains editable Markdown templates that Claude reads automatically before any content-related task (briefs, audits, articles). Fill them in once and every skill output will reflect your brand from the start.

| File | Contents |
|---|---|
| `docs/product.md` | Overview, key features, value proposition, pricing |
| `docs/audiences.md` | Target segments and personas |
| `docs/voice-tone.md` | Brand voice, tone guidelines, do's and don'ts |
| `docs/competitors.md` | Direct/indirect competitors, positioning |
| `docs/proof-points.md` | Statistics, case studies, testimonials |
| `docs/brand-guidelines.md` | Logo, colors, typography, components |

## Branding

HTML reports (SERP Clusters dendrograms, audits, dashboards) can display your company logo and use your brand colors.

**Setup:**
- Replace `assets/branding/logo-light.svg` and `logo-dark.svg` with your own logo.
- Edit `assets/branding/brand-config.json` (colors, fonts, company name).
- **Auto-extract from your site:** open your site in a browser, then paste `assets/branding/extract-brand-styles.js` into the DevTools console.

## Admin tools

| Command | What it does |
|---|---|
| `python3 .../check_setup.py` | Verifies that the API key is working |
| `python3 .../balance.py` | Shows remaining token balance |
| `python3 .../params.py countries` | Lists country codes |
| `python3 .../params.py languages` | Lists language codes |
| `python3 .../sync_skills.py` | Syncs the skills registry |
| `python3 .../create_skill.py` | Creates a new skill from a template |
| `bash validate-skills.sh` | Validates skill structure |

Admin scripts are located in `.claude/skills/nod-nodeshub-api/scripts/`.

## Project structure

```
nodeshub-seo-skills/
├── .claude/
│   ├── skills/                 # Skills (each has SKILL.md + scripts/ + evals/)
│   │   ├── nod-*/              # 11 SEO skills
│   │   ├── ai-score/           # AI content detection (Genuino)
│   │   ├── connect-*/          # Setup guides (NodesHub, OpenRouter, Genuino, GSC, GA4)
│   │   ├── guide/              # Interactive onboarding
│   │   └── skill-creator/      # Creating new skills
│   ├── agents/
│   │   ├── topic-planner/      # Agent: keyword → brief pipeline
│   │   ├── keyword-to-publish/ # Agent: keyword → article → AI check → audit
│   │   └── content-humanizer/  # Agent: text → AI score → rewrite → loop
│   └── settings.local.json     # API keys (gitignored)
├── assets/branding/            # Logos, colors, fonts for HTML reports
├── docs/                       # Brand context files (auto-read by Claude before content tasks)
├── output/                     # All generated data and reports (gitignored)
│   ├── data/                   # Snapshots, keyword lists, briefs, SERP cache
│   └── reports/                # HTML and Markdown reports
├── CLAUDE.md                   # Project instructions and skills registry
├── AGENTS.md                   # Agent specifications
├── CONTRIBUTING.md             # How to add/modify skills
└── validate-skills.sh          # Skills structure validation
```

## Caching

SERP results are cached locally to avoid redundant API calls and save tokens. If you run the same keyword twice – even across different skills – the cached result is used at zero cost.

- Cache location: `output/data/serp-cache/{gl}-{hl}/{keyword}.json`
- Default TTL: 24 hours (configurable in `.claude/skills/nod-nodeshub-api/scripts/serp_cache.py`)
- Force a fresh fetch: pass `--no-cache` to `nod-serp-clusters` (other skills use the cache transparently and bypass it automatically for cache misses)

## Security

- API keys are stored in `.claude/settings.local.json` (listed in `.gitignore`).
- GSC/GA4 credentials are stored in the `local/` folder (also in `.gitignore`).
- The repository should be kept private until published – even with `.gitignore` in place, it's best not to risk accidentally exposing keys.
- Never commit files containing API keys.

## FAQ

**Q: How much does it cost?**
A: This repository is free to download. You will need a NodesHub API key to use most features – new users receive 100 free tokens upon registration at nodeshub.io. Additional tokens can be purchased there. Genuino features are billed separately in Genuino credits; see genuino.ai for pricing.

**Q: Can I use it without a NodesHub API key?**
A: Without an API key, most skills will not return data. The repository is designed to work with the NodesHub API. A free registration at nodeshub.io is sufficient to get started.

**Q: What is Genuino and do I need it?**
A: Genuino is a third-party AI content detection API. You only need it for three features: the AI Score skill, the Keyword to Publish agent, and the Content Humanizer agent. All other skills work without it. Registration and pricing at genuino.ai.

**Q: Can the agents write articles for me?**
A: Yes. The Keyword to Publish agent can research a topic, write an article, verify it passes AI detection, and audit it against the competition – all in a single session. The article is written by Claude based on a data-driven brief, not from a template.

**Q: Is this available to individual (non-business) users?**
A: No. This repository and the NodesHub platform it connects to are intended exclusively for professional and business use. If you are an individual user acting outside of any business capacity, this repository is not intended for you, and you will not be able to purchase access to NodesHub.

**Q: Does it work for non-English markets?**
A: Yes. Set `--gl` and `--hl` to your target country and language codes. All skills work on any market and in any language.

**Q: How often should I check rankings?**
A: Once a week is more than enough. Positions don't change from hour to hour.

**Q: Can I run the scripts without Claude Code?**
A: Yes. Each skill has a Python script that can be run directly from the terminal. You'll need to set the `NODESHUB_API_KEY` environment variable or save the key via `save_key.py`. Claude Code adds a convenience layer (slash commands, automatic result analysis), but it isn't required.

**Q: Does it work with tools other than Claude Code?**
A: The Python scripts work independently – from the terminal, Gemini CLI, Cursor, or Aider. Slash commands and automatic skill recognition (the SKILL.md layer) are native Claude Code features. Other tools can invoke the scripts directly.

**Q: Can I modify or redistribute this repository?**
A: Yes. You are free to modify and redistribute the repository, including modified versions. All intellectual property rights remain with Senuto sp. z o.o. See the License and terms of use section below for details.

**Q: Will the repository be kept up to date?**
A: Senuto is under no obligation to update this repository or maintain its compatibility with future versions of NodesHub or Claude Code. It is provided as-is as promotional material.

**Q: How do I add a new skill?**
A: Use `/skill-creator` in Claude Code, or do it manually: create a folder in `.claude/skills/`, add a SKILL.md and scripts in `scripts/`, then run `sync_skills.py`. Details are in CONTRIBUTING.md.

**Q: What's the difference between a skill and an agent?**
A: A skill is a single tool (e.g., SERP analysis). An agent is an orchestrator that chains several skills into a pipeline (e.g., topic-planner: keywords → clusters → briefs). Skills live in `.claude/skills/`, agents in `.claude/agents/`.

## License and terms of use

Copyright © Senuto sp. z o.o. All rights reserved.

This repository is made available under the following terms:

**You are free to:**
- Download and use this repository for your own professional purposes.
- Modify the scripts and instructions to suit your workflow.
- Share or redistribute the repository, including modified versions.

**You must not:**
- Remove or alter copyright notices.
- Represent this repository as your own original work when redistributing it.
- Use this repository in any way that violates applicable law.

All intellectual property rights in the contents of this repository – including scripts, instructions, and configuration files – remain with Senuto sp. z o.o. Senuto reserves the right to pursue any available legal remedies in the event of an infringement of its rights.

## Disclaimer

**Provided as-is.** This repository is provided as promotional material, free of charge, strictly on an "as-is" basis. Senuto makes no representations or warranties of any kind – express or implied – regarding its quality, accuracy, fitness for a particular purpose, or compatibility with any specific version of Claude Code or the NodesHub API.

**No obligation to update.** Senuto is under no obligation to update, maintain, or ensure the ongoing compatibility of this repository with the NodesHub API or Claude Code. The repository reflects the state of the NodesHub platform at the time of its release. Future changes to either platform may render parts of this repository non-functional.

**No liability.** Senuto and NodesHub accept no liability for any damages, losses, or consequences arising from the use, modification, or redistribution of this repository or anything derived from it.

**No complaints or refund process.** As this repository is promotional material provided free of charge, it is not subject to any complaints or warranty claims. This does not affect any rights you may have under the separate NodesHub Terms of Service if you are a paying NodesHub customer.

**Right to withdraw.** Senuto reserves the right to remove this repository or disable its connection to the NodesHub API at any time and without notice.

## For business users only

This repository – and the NodesHub platform it connects to – is intended exclusively for professional and business use. By downloading this repository you confirm that you are acting in your capacity as a business, freelancer, or other professional entity, and not as a consumer.

Downloading this repository does not create any contractual relationship with Senuto or NodesHub, and does not entitle you to access or purchase the NodesHub platform. Access to NodesHub is governed solely by the NodesHub Terms of Service, available at [nodeshub.io](https://nodeshub.io).

**NodesHub API key required.** This repository requires a NodesHub API key to function. New users receive 100 free tokens upon registration. Without an API key, most skills will not work. This repository is promotional material designed to showcase the capabilities of the NodesHub platform – it is not a standalone application.
