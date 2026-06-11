#!/usr/bin/env node
/**
 * Fetches data from Google Search Console and saves to knowledge/metrics/
 *
 * Usage:
 *   node scripts/fetch-gsc.js                    # all languages
 *   node scripts/fetch-gsc.js --lang en          # English only
 *   node scripts/fetch-gsc.js --lang all         # each language separately
 *   node scripts/fetch-gsc.js --days 14          # last 14 days
 *   node scripts/fetch-gsc.js --start 2026-01-01 --end 2026-01-31
 *
 * Output:
 *   knowledge/metrics/gsc-2026-02-05.json        # combined
 *   knowledge/metrics/gsc-en-2026-02-05.json     # English
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { google } = require('googleapis');

// Configuration
const CONFIG = {
  siteUrl: 'sc-domain:example.com',  // Set your GSC property (e.g. sc-domain:yourdomain.com)
  credentialsPath: path.join(__dirname, '../local/gsc-credentials.json'),
  outputDir: path.join(__dirname, '../knowledge/metrics/seo'),
  defaultDays: 28,
  limits: {
    queries: 5000,
    pages: 2000,
    daily: 100,
    queryPages: 5000
  },
  languages: ['en']
};

// Parse CLI arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    days: CONFIG.defaultDays,
    lang: null  // null = all together, 'all' = per language, 'pl'/'en'/'ro' = specific
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--days' && args[i + 1]) {
      options.days = parseInt(args[i + 1]);
    }
    if (args[i] === '--start' && args[i + 1]) {
      options.startDate = args[i + 1];
    }
    if (args[i] === '--end' && args[i + 1]) {
      options.endDate = args[i + 1];
    }
    if (args[i] === '--lang' && args[i + 1]) {
      options.lang = args[i + 1];
    }
  }

  if (!options.startDate) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - options.days);
    options.startDate = start.toISOString().split('T')[0];
    options.endDate = end.toISOString().split('T')[0];
  }

  return options;
}

// Authentication
async function authenticate() {
  if (!fs.existsSync(CONFIG.credentialsPath)) {
    console.error(`Missing credentials file: ${CONFIG.credentialsPath}`);
    console.error('\nSetup:');
    console.error('1. Go to Google Cloud Console → APIs & Services → Credentials');
    console.error('2. Create a Service Account');
    console.error('3. Download the JSON key and save as local/gsc-credentials.json');
    console.error('4. Add the Service Account email to GSC as a user');
    process.exit(1);
  }

  const auth = new google.auth.GoogleAuth({
    keyFile: CONFIG.credentialsPath,
    scopes: ['https://www.googleapis.com/auth/webmasters.readonly']
  });

  return auth;
}

// Build language filter
function buildLanguageFilter(lang) {
  if (!lang) return null;

  return {
    dimensionFilterGroups: [{
      filters: [{
        dimension: 'page',
        operator: 'contains',
        expression: `/${lang}/`
      }]
    }]
  };
}

// Fetch search analytics data
async function fetchSearchAnalytics(auth, options, lang = null) {
  const searchconsole = google.searchconsole({ version: 'v1', auth });
  const langLabel = lang ? ` [${lang.toUpperCase()}]` : '';

  console.log(`Fetching data${langLabel}: ${options.startDate} → ${options.endDate}`);

  const filter = buildLanguageFilter(lang);
  const baseRequest = {
    siteUrl: CONFIG.siteUrl,
    requestBody: {
      startDate: options.startDate,
      endDate: options.endDate,
      ...(filter || {})
    }
  };

  // Overall stats (by date)
  const overallResponse = await searchconsole.searchanalytics.query({
    ...baseRequest,
    requestBody: {
      ...baseRequest.requestBody,
      dimensions: ['date'],
      rowLimit: CONFIG.limits.daily
    }
  });

  // Top queries
  const queriesResponse = await searchconsole.searchanalytics.query({
    ...baseRequest,
    requestBody: {
      ...baseRequest.requestBody,
      dimensions: ['query'],
      rowLimit: CONFIG.limits.queries
    }
  });

  // Top pages
  const pagesResponse = await searchconsole.searchanalytics.query({
    ...baseRequest,
    requestBody: {
      ...baseRequest.requestBody,
      dimensions: ['page'],
      rowLimit: CONFIG.limits.pages
    }
  });

  // Query x page pairs (needed for cannibalization detection)
  const queryPagesResponse = await searchconsole.searchanalytics.query({
    ...baseRequest,
    requestBody: {
      ...baseRequest.requestBody,
      dimensions: ['query', 'page'],
      rowLimit: CONFIG.limits.queryPages
    }
  });

  // Summary totals
  const totals = (overallResponse.data.rows || []).reduce((acc, row) => {
    acc.clicks += row.clicks || 0;
    acc.impressions += row.impressions || 0;
    return acc;
  }, { clicks: 0, impressions: 0 });

  const avgPosition = (overallResponse.data.rows || []).reduce((sum, row) =>
    sum + (row.position || 0), 0) / (overallResponse.data.rows?.length || 1);

  const avgCtr = totals.impressions > 0 ? (totals.clicks / totals.impressions) * 100 : 0;

  return {
    meta: {
      siteUrl: CONFIG.siteUrl,
      language: lang || 'all',
      startDate: options.startDate,
      endDate: options.endDate,
      fetchedAt: new Date().toISOString()
    },
    summary: {
      totalClicks: totals.clicks,
      totalImpressions: totals.impressions,
      avgCtr: avgCtr.toFixed(2) + '%',
      avgPosition: avgPosition.toFixed(1)
    },
    daily: (overallResponse.data.rows || []).map(row => ({
      date: row.keys[0],
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: ((row.ctr || 0) * 100).toFixed(2) + '%',
      position: row.position?.toFixed(1)
    })),
    topQueries: (queriesResponse.data.rows || []).map(row => ({
      query: row.keys[0],
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: ((row.ctr || 0) * 100).toFixed(2) + '%',
      position: row.position?.toFixed(1)
    })),
    topPages: (pagesResponse.data.rows || []).map(row => ({
      page: row.keys[0].replace(CONFIG.siteUrl, '/'),
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: ((row.ctr || 0) * 100).toFixed(2) + '%',
      position: row.position?.toFixed(1)
    })),
    queryPages: (queryPagesResponse.data.rows || []).map(row => ({
      query: row.keys[0],
      page: row.keys[1].replace(CONFIG.siteUrl, '/'),
      clicks: row.clicks,
      impressions: row.impressions,
      ctr: ((row.ctr || 0) * 100).toFixed(2) + '%',
      position: row.position?.toFixed(1)
    }))
  };
}

// Generate output file path
function getOutputPath(lang = null) {
  const today = new Date().toISOString().split('T')[0];
  const langSuffix = lang ? `-${lang}` : '';
  return path.join(CONFIG.outputDir, `gsc${langSuffix}-${today}.json`);
}

// Save data to file
function saveData(data, outputPath) {
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  fs.writeFileSync(outputPath, JSON.stringify(data, null, 2));
  console.log(`Saved to: ${outputPath}`);
}

// Print summary to console
function printSummary(data, lang = null) {
  const langLabel = lang ? ` [${lang.toUpperCase()}]` : '';
  console.log(`\nSummary${langLabel}:`);
  console.log(`   Clicks:      ${data.summary.totalClicks.toLocaleString()}`);
  console.log(`   Impressions: ${data.summary.totalImpressions.toLocaleString()}`);
  console.log(`   CTR:         ${data.summary.avgCtr}`);
  console.log(`   Avg Position: ${data.summary.avgPosition}`);
  console.log(`\n🔍 Top 5 queries:`);
  data.topQueries.slice(0, 5).forEach((q, i) => {
    console.log(`   ${i + 1}. "${q.query}" - ${q.clicks} clicks, pos ${q.position}`);
  });
}

// Main
async function main() {
  try {
    const options = parseArgs();
    const auth = await authenticate();

    if (options.lang === 'all') {
      // Fetch per language
      for (const lang of CONFIG.languages) {
        const data = await fetchSearchAnalytics(auth, options, lang);
        const outputPath = getOutputPath(lang);
        saveData(data, outputPath);
        printSummary(data, lang);
      }
      // Plus overall
      const dataAll = await fetchSearchAnalytics(auth, options, null);
      const outputPathAll = getOutputPath(null);
      saveData(dataAll, outputPathAll);
      printSummary(dataAll, null);
    } else if (options.lang && CONFIG.languages.includes(options.lang)) {
      // Fetch for one language
      const data = await fetchSearchAnalytics(auth, options, options.lang);
      const outputPath = getOutputPath(options.lang);
      saveData(data, outputPath);
      printSummary(data, options.lang);
    } else {
      // Fetch all together
      const data = await fetchSearchAnalytics(auth, options, null);
      const outputPath = getOutputPath(null);
      saveData(data, outputPath);
      printSummary(data, null);
    }

    console.log('\nDone.');
  } catch (error) {
    console.error('Error:', error.message);
    if (error.code === 403) {
      console.error('\nEnsure the Service Account has access in GSC.');
    }
    process.exit(1);
  }
}

main();
