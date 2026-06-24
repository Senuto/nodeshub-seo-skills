#!/usr/bin/env node

import { existsSync, mkdirSync, cpSync, readFileSync, writeFileSync, appendFileSync } from 'fs';
import { join, resolve, dirname } from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const pkgRoot = resolve(__dirname, '..');
const dest = process.cwd();

// ── Helpers ──────────────────────────────────────────────────────────

function log(msg) { console.log(`  ${msg}`); }
function ok(msg)  { console.log(`  \u2713 ${msg}`); }
function warn(msg){ console.log(`  ! ${msg}`); }

function copyDir(src, dst) {
  if (!existsSync(src)) return;
  cpSync(src, dst, { recursive: true, force: true });
}

function ensureDir(dir) {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

// ── Banner ───────────────────────────────────────────────────────────

console.log();
console.log('  ╔════════════════════════════════════════════╗');
console.log('  ║      nodeshub-seo-skills installer        ║');
console.log('  ║   SEO automation skills for Claude Code   ║');
console.log('  ╚════════════════════════════════════════════╝');
console.log();

// ── Guard: don't install into the package itself ─────────────────────

if (resolve(dest) === resolve(pkgRoot)) {
  warn('You are inside the nodeshub-seo-skills package directory.');
  warn('Run this command from your target project instead.');
  process.exit(1);
}

// ── 1. Check Python 3 ───────────────────────────────────────────────

log('Checking Python 3...');
try {
  const pyVer = execSync('python3 --version', { encoding: 'utf8' }).trim();
  ok(`Found ${pyVer}`);
} catch {
  warn('python3 not found. Skills require Python 3 — install it before using nod- skills.');
}

// ── 2. Copy .claude/skills/ ─────────────────────────────────────────

log('Installing skills...');
const skillsSrc = join(pkgRoot, '.claude', 'skills');
const skillsDst = join(dest, '.claude', 'skills');
ensureDir(skillsDst);
copyDir(skillsSrc, skillsDst);
ok('Copied .claude/skills/');

log('Installing agents...');
const agentsSrc = join(pkgRoot, '.claude', 'agents');
const agentsDst = join(dest, '.claude', 'agents');
if (existsSync(agentsSrc)) {
  ensureDir(agentsDst);
  copyDir(agentsSrc, agentsDst);
  ok('Copied .claude/agents/');
}

// ── 3. Create directory scaffolding ─────────────────────────────────

log('Creating directory structure...');
const dirs = [
  'output/data/rank-history',
  'output/data/competitor-tracking',
  'output/data/visibility',
  'output/data/gsc',
  'output/data/serp-cache',
  'output/data/briefs',
  'output/data/keywords',
  'output/data/paa',
  'output/data/topics',
  'output/data/articles',
  'output/reports',
  'output/knowledge/metrics/seo',
  'output/knowledge/metrics/analytics',
  'docs',
  'scripts',
  'local',
];
for (const d of dirs) {
  ensureDir(join(dest, d));
}
ok('Directory scaffolding ready');

// ── 4. Copy utility scripts ─────────────────────────────────────────

log('Copying utility scripts...');
for (const script of ['fetch-gsc.js', 'fetch-ga4.js']) {
  const src = join(pkgRoot, 'scripts', script);
  const dst = join(dest, 'scripts', script);
  if (existsSync(src) && !existsSync(dst)) {
    writeFileSync(dst, readFileSync(src));
    ok(`scripts/${script}`);
  } else if (existsSync(dst)) {
    ok(`scripts/${script} (already exists, skipped)`);
  }
}

// ── 5. Handle CLAUDE.md ─────────────────────────────────────────────

log('Setting up CLAUDE.md...');

const MARKER_START = '<!-- NODESHUB:START -->';
const MARKER_END   = '<!-- NODESHUB:END -->';

const skillSection = `${MARKER_START}
# Nodeshub SEO Skills - Best Practices

## Local instructions

**IMPORTANT:** If a file \`CLAUDE.local.md\` exists, Claude MUST read it at the start of each session. It contains private user instructions.

## Working rules

- Always humanize texts - avoid artificial, "AI-like" tone
- Do not use emojis in copy (unless the client explicitly asks)
- Write in English by default
- Before writing SEO content, always read product context

## Missing setup (NodesHub / GSC)

**If NodesHub is not set up** (no API key or \`check_setup.py\` fails): Use the **/connect-nodeshub** skill for a step-by-step guided setup, or follow the steps in each nod- skill's Setup section and \`.claude/skills/nod-nodeshub-api/setup/README.md\`.

For GSC setup, use the **/connect-gsc** skill.

For GA4 setup, use the **/connect-ga4** skill.

## Banner

**IMPORTANT:** When **any** skill is invoked (with or without the \`nod-\` prefix), Claude MUST run the banner as the first action:
\`\`\`bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('SKILL_NAME')"
\`\`\`
Replace \`SKILL_NAME\` with the human-readable skill name.

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
- \`/nod-competitor-tracker\` - track competitor domains across keywords
- \`/nod-content-auditor\` - audit content against SERP reality
- \`/nod-content-brief\` - generate data-driven content briefs
- \`/nod-featured-snippet-hunter\` - find Featured Snippet / Answer Box opportunities
- \`/nod-intent-classifier\` - classify search intent from SERP signals
- \`/nod-keyword-research\` - expand seed keywords into keyword lists
- \`/nod-nodeshub-api\` - shared API client, setup & balance check
- \`/nod-paa-miner\` - mine People Also Ask questions from SERPs
- \`/nod-rank-tracker\` - track keyword positions for a domain over time
- \`/nod-serp-analysis\` - analyze Google SERP for any keyword
- \`/nod-serp-clusters\` - cluster keywords by SERP similarity
- \`/nod-visibility-monitor\` - calculate SEO visibility score
<!-- SKILLS:END -->

### Utilities
- \`/connect-nodeshub\` - step-by-step NodesHub API connection (key saved in repo)
- \`/connect-gsc\` - step-by-step GSC connection (credentials in repo)
- \`/connect-ga4\` - step-by-step GA4 connection (credentials in repo)
- \`/skill-creator\` - scaffold new skills and sync the registry
${MARKER_END}`;

const claudeMdPath = join(dest, 'CLAUDE.md');

if (!existsSync(claudeMdPath)) {
  // No CLAUDE.md — create one with our section
  writeFileSync(claudeMdPath, skillSection + '\n');
  ok('Created CLAUDE.md');
} else {
  // CLAUDE.md exists — merge idempotently
  let content = readFileSync(claudeMdPath, 'utf8');
  const startIdx = content.indexOf(MARKER_START);
  const endIdx   = content.indexOf(MARKER_END);

  if (startIdx !== -1 && endIdx !== -1) {
    // Replace existing section
    content = content.slice(0, startIdx) + skillSection + content.slice(endIdx + MARKER_END.length);
    writeFileSync(claudeMdPath, content);
    ok('Updated existing Nodeshub section in CLAUDE.md');
  } else {
    // Append
    appendFileSync(claudeMdPath, '\n\n' + skillSection + '\n');
    ok('Appended Nodeshub section to CLAUDE.md');
  }
}

// ── 6. Copy repo-level files ─────────────────────────────────────────

log('Copying repo-level files...');

const repoFiles = [
  'AGENTS.md',
  'CONTRIBUTING.md',
  'validate-skills.sh',
];

for (const file of repoFiles) {
  const src = join(pkgRoot, file);
  const dst = join(dest, file);
  if (existsSync(src) && !existsSync(dst)) {
    writeFileSync(dst, readFileSync(src));
    ok(file);
  } else if (existsSync(dst)) {
    ok(`${file} (already exists, skipped)`);
  }
}

// Copy .claude-plugin/marketplace.json
const pluginSrc = join(pkgRoot, '.claude-plugin');
const pluginDst = join(dest, '.claude-plugin');
if (existsSync(pluginSrc)) {
  ensureDir(pluginDst);
  const mjson = join(pluginSrc, 'marketplace.json');
  const mjsonDst = join(pluginDst, 'marketplace.json');
  if (existsSync(mjson) && !existsSync(mjsonDst)) {
    writeFileSync(mjsonDst, readFileSync(mjson));
    ok('.claude-plugin/marketplace.json');
  } else if (existsSync(mjsonDst)) {
    ok('.claude-plugin/marketplace.json (already exists, skipped)');
  }
}

// ── 7. Copy branding assets ──────────────────────────────────────────

log('Setting up branding assets...');
const brandingSrc = join(pkgRoot, 'assets', 'branding');
const brandingDst = join(dest, 'assets', 'branding');
if (existsSync(brandingSrc)) {
  ensureDir(brandingDst);
  const brandFiles = [
    'brand-config.json',
    'brand-guidelines.md',
    'logo-light.svg',
    'logo-dark.svg',
    'extract-brand-styles.js',
    'README.md',
  ];
  for (const file of brandFiles) {
    const src = join(brandingSrc, file);
    const dst = join(brandingDst, file);
    if (existsSync(src) && !existsSync(dst)) {
      writeFileSync(dst, readFileSync(src));
    }
  }
  ok('assets/branding/ (logo placeholders + brand-config.json)');
  log('  Replace logo-light.svg and logo-dark.svg with your company logos');
  log('  Edit brand-config.json with your colors and fonts');
}

// ── 8. Create .claude/settings.local.json from template ─────────────

log('Setting up settings.local.json...');
const settingsExampleSrc = join(pkgRoot, '.claude', 'settings.local.json.example');
const settingsDst = join(dest, '.claude', 'settings.local.json');
if (existsSync(settingsExampleSrc) && !existsSync(settingsDst)) {
  ensureDir(join(dest, '.claude'));
  writeFileSync(settingsDst, readFileSync(settingsExampleSrc));
  ok('.claude/settings.local.json created (fill in your API keys)');
} else if (existsSync(settingsDst)) {
  ok('.claude/settings.local.json (already exists, skipped)');
}

// ── 9. Update .gitignore ────────────────────────────────────────────

log('Updating .gitignore...');

const gitignoreEntries = [
  '# Nodeshub SEO Skills',
  'local/',
  '*.local.md',
  'CLAUDE.local.md',
  'settings.local.json',
  '.claude/settings.local.json',
  'output/',
  '__pycache__/',
  '*.pyc',
];

const gitignorePath = join(dest, '.gitignore');
let gitignoreContent = existsSync(gitignorePath) ? readFileSync(gitignorePath, 'utf8') : '';

const newEntries = gitignoreEntries.filter(e => !e.startsWith('#') && !gitignoreContent.includes(e));

if (newEntries.length > 0) {
  const block = '\n# Nodeshub SEO Skills\n' + newEntries.join('\n') + '\n';
  appendFileSync(gitignorePath, block);
  ok('.gitignore updated');
} else {
  ok('.gitignore already up to date');
}

// ── Summary ─────────────────────────────────────────────────────────

console.log();
console.log('  ────────────────────────────────────────────');
console.log('  Installation complete!');
console.log();
console.log('  Next steps:');
console.log('    1. Open Claude Code in this project');
console.log('    2. Run /connect-nodeshub to set up your API key');
console.log('    3. (Optional) Run /connect-gsc for Search Console data');
console.log('    4. (Optional) Run /connect-ga4 for Analytics data');
console.log('    5. Try /nod-serp-analysis to analyze any keyword');
console.log();
console.log('  Docs: https://github.com/Senuto/nodeshub-seo-skills');
console.log('  ────────────────────────────────────────────');
console.log();
