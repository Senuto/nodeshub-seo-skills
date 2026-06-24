#!/usr/bin/env node
/**
 * Fetches keyword metrics (search volume, CPC, competition) and saves to
 * knowledge/metrics/ads/. Two interchangeable paths:
 *
 *   1. Google Ads API  — pulls Keyword Plan metrics. Requires a developer
 *      token (approval can take days), so it fails gracefully with setup
 *      instructions when credentials are missing.
 *   2. Generic CSV ingest — reads an exported keyword list and normalizes it
 *      to the same shape. Works today, no API approval needed. Reusable for
 *      Google Ads, DataForSEO, Senuto, or any keyword export.
 *
 * Both paths emit the same array of { keyword, volume, cpc, competition }.
 *
 * Usage:
 *   node scripts/fetch-google-ads.js --csv keywords.csv          # CSV ingest
 *   node scripts/fetch-google-ads.js --keywords "seo tools,rank tracker"  # API path
 *   node scripts/fetch-google-ads.js --csv keywords.csv --out custom.json
 *
 * Output:
 *   knowledge/metrics/ads/ads-2026-06-11.json
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

// ESM does not expose __dirname/require; recreate them (package.json is "type": "module").
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

// Configuration — mirrors fetch-gsc.js / fetch-ga4.js style.
const CONFIG = {
  credentialsPath: path.join(__dirname, '../local/google-ads-credentials.json'),
  outputDir: path.join(__dirname, '../knowledge/metrics/ads'),
  // gl/hl drive the Google Ads geo/language constants on the API path.
  defaultGl: 'us',
  defaultHl: 'en'
};

// Header aliases for the generic CSV ingest. Lower-cased, punctuation-stripped
// header names map onto our normalized fields.
const COLUMN_ALIASES = {
  keyword: ['keyword', 'query', 'term', 'phrase', 'search term', 'keywords'],
  volume: [
    'volume', 'avg monthly searches', 'avg_monthly_searches',
    'search volume', 'searchvolume', 'monthly searches', 'searches',
    'avg. monthly searches', 'sv'
  ],
  cpc: ['cpc', 'avg cpc', 'avg_cpc', 'cost per click', 'top of page bid', 'cpc usd'],
  competition: ['competition', 'comp', 'competition index', 'competition_index', 'difficulty']
};

// Parse CLI arguments.
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    csv: null,
    keywords: [],
    out: null,
    gl: CONFIG.defaultGl,
    hl: CONFIG.defaultHl
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--csv' && args[i + 1]) options.csv = args[++i];
    else if (args[i] === '--out' && args[i + 1]) options.out = args[++i];
    else if (args[i] === '--gl' && args[i + 1]) options.gl = args[++i];
    else if (args[i] === '--hl' && args[i + 1]) options.hl = args[++i];
    else if (args[i] === '--keywords' && args[i + 1]) {
      options.keywords = args[++i].split(',').map(k => k.trim()).filter(Boolean);
    }
  }

  return options;
}

// Minimal CSV parser supporting quoted fields and embedded commas/quotes.
// Avoids a dependency; good enough for keyword exports.
function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ',') {
      row.push(field); field = '';
    } else if (c === '\n') {
      row.push(field); field = '';
      rows.push(row); row = [];
    } else if (c === '\r') {
      // ignore — handled by the following \n
    } else {
      field += c;
    }
  }
  // Flush trailing field/row.
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter(r => r.length > 1 || (r.length === 1 && r[0].trim() !== ''));
}

// Normalize a header label for alias matching.
function normalizeHeader(h) {
  return h.toLowerCase().replace(/[._-]/g, ' ').replace(/\s+/g, ' ').trim();
}

// Build a map of { field: columnIndex } from a header row.
function mapColumns(headerRow) {
  const normalized = headerRow.map(normalizeHeader);
  const map = {};
  for (const [field, aliases] of Object.entries(COLUMN_ALIASES)) {
    for (let i = 0; i < normalized.length; i++) {
      if (aliases.includes(normalized[i])) { map[field] = i; break; }
    }
  }
  return map;
}

// Parse a number that may carry separators, currency symbols, or ranges.
function toNumber(raw) {
  if (raw === undefined || raw === null) return null;
  const cleaned = String(raw).replace(/[^0-9.\-]/g, '');
  if (cleaned === '' || cleaned === '-') return null;
  const n = parseFloat(cleaned);
  return Number.isFinite(n) ? n : null;
}

// Normalize competition. Accepts numeric index (0-1 or 0-100) or text labels.
function toCompetition(raw) {
  if (raw === undefined || raw === null || raw === '') return null;
  const text = String(raw).trim().toLowerCase();
  const labels = { low: 0.2, medium: 0.5, high: 0.8 };
  if (text in labels) return labels[text];
  const n = toNumber(raw);
  if (n === null) return null;
  // Scale a 0-100 index down to 0-1 for consistency.
  return n > 1 ? Math.min(n / 100, 1) : n;
}

// CSV ingest path — returns normalized keyword rows.
function ingestCsv(csvPath) {
  if (!fs.existsSync(csvPath)) {
    console.error(`CSV file not found: ${csvPath}`);
    process.exit(1);
  }

  const rows = parseCsv(fs.readFileSync(csvPath, 'utf-8'));
  if (rows.length < 2) {
    console.error('CSV has no data rows.');
    process.exit(1);
  }

  const colMap = mapColumns(rows[0]);
  if (colMap.keyword === undefined) {
    console.error('Could not find a keyword column. Expected a header like:');
    console.error('  keyword, avg_monthly_searches (or volume), cpc, competition');
    console.error(`Found headers: ${rows[0].join(', ')}`);
    process.exit(1);
  }

  const out = [];
  const seen = new Set();
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    const keyword = (row[colMap.keyword] || '').trim();
    if (!keyword) continue;
    const key = keyword.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);

    out.push({
      keyword,
      volume: colMap.volume !== undefined ? toNumber(row[colMap.volume]) : null,
      cpc: colMap.cpc !== undefined ? toNumber(row[colMap.cpc]) : null,
      competition: colMap.competition !== undefined ? toCompetition(row[colMap.competition]) : null
    });
  }

  console.log(`CSV ingest: ${out.length} unique keywords from ${path.basename(csvPath)}`);
  return out;
}

// Google Ads API path — guarded so missing creds fail with a clear message.
async function fetchFromApi(options) {
  if (!fs.existsSync(CONFIG.credentialsPath)) {
    console.error('Google Ads API credentials not found.');
    console.error(`Expected: ${CONFIG.credentialsPath}`);
    console.error('\nThe Google Ads API needs an approved developer token, which can take');
    console.error('several days. Until then, use the CSV fallback (no approval required):');
    console.error('\n  node scripts/fetch-google-ads.js --csv your-keywords.csv');
    console.error('\nExport a keyword list from Google Ads Keyword Planner, DataForSEO, or');
    console.error('Senuto with columns: keyword, avg_monthly_searches (or volume), cpc, competition.');
    console.error('\nTo enable the API path later, save credentials JSON with:');
    console.error('  { "developer_token", "client_id", "client_secret", "refresh_token", "customer_id" }');
    console.error(`to ${CONFIG.credentialsPath} and install: npm install google-ads-api`);
    process.exit(1);
  }

  if (!options.keywords.length) {
    console.error('No keywords given. Pass --keywords "a,b,c" for the API path.');
    process.exit(1);
  }

  let GoogleAdsApi;
  try {
    ({ GoogleAdsApi } = require('google-ads-api'));
  } catch (e) {
    console.error('Missing dependency: google-ads-api');
    console.error('Install it with: npm install google-ads-api');
    console.error('Or use the CSV fallback: --csv your-keywords.csv');
    process.exit(1);
  }

  const creds = JSON.parse(fs.readFileSync(CONFIG.credentialsPath, 'utf-8'));
  const api = new GoogleAdsApi({
    client_id: creds.client_id,
    client_secret: creds.client_secret,
    developer_token: creds.developer_token
  });

  const customer = api.Customer({
    customer_id: creds.customer_id,
    refresh_token: creds.refresh_token
  });

  console.log(`Google Ads API: requesting metrics for ${options.keywords.length} keywords`);

  // generateKeywordHistoricalMetrics returns avg monthly searches, competition,
  // and bid micros. Geo/language constants depend on the account; we keep the
  // request minimal and let the account defaults apply.
  const response = await customer.keywordPlanIdeas.generateKeywordHistoricalMetrics({
    keywords: options.keywords
  });

  const results = response.results || response || [];
  return results.map(r => {
    const m = r.keyword_metrics || {};
    const lowBid = m.low_top_of_page_bid_micros;
    const highBid = m.high_top_of_page_bid_micros;
    // CPC estimate: average of the top-of-page bid range, micros -> currency.
    let cpc = null;
    if (lowBid != null && highBid != null) cpc = (Number(lowBid) + Number(highBid)) / 2 / 1e6;
    else if (highBid != null) cpc = Number(highBid) / 1e6;

    return {
      keyword: r.text || r.search_query || '',
      volume: m.avg_monthly_searches != null ? Number(m.avg_monthly_searches) : null,
      cpc: cpc != null ? Number(cpc.toFixed(2)) : null,
      competition: m.competition_index != null ? Number(m.competition_index) / 100 : null
    };
  });
}

// Output path — ads-YYYY-MM-DD.json by default.
function getOutputPath(custom) {
  if (custom) return path.resolve(custom);
  const today = new Date().toISOString().split('T')[0];
  return path.join(CONFIG.outputDir, `ads-${today}.json`);
}

// Save normalized rows to disk.
function saveData(rows, outputPath) {
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(rows, null, 2));
  console.log(`Saved to: ${outputPath}`);
}

// Print a short preview.
function printSummary(rows) {
  const withVol = rows.filter(r => r.volume != null).length;
  const withCpc = rows.filter(r => r.cpc != null).length;
  console.log('\nSummary:');
  console.log(`   Keywords:        ${rows.length}`);
  console.log(`   With volume:     ${withVol}`);
  console.log(`   With CPC:        ${withCpc}`);
  console.log('\nTop 5 by volume:');
  [...rows]
    .sort((a, b) => (b.volume || 0) - (a.volume || 0))
    .slice(0, 5)
    .forEach((r, i) => {
      const vol = r.volume != null ? r.volume.toLocaleString() : 'n/a';
      const cpc = r.cpc != null ? `$${r.cpc}` : 'n/a';
      console.log(`   ${i + 1}. ${r.keyword} - vol ${vol}, cpc ${cpc}`);
    });
}

async function main() {
  try {
    const options = parseArgs();

    const rows = options.csv
      ? ingestCsv(options.csv)
      : await fetchFromApi(options);

    const outputPath = getOutputPath(options.out);
    saveData(rows, outputPath);
    printSummary(rows);

    console.log('\nDone.');
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
