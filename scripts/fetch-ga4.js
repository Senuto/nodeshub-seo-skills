#!/usr/bin/env node
/**
 * Fetches data from Google Analytics 4 and saves to knowledge/metrics/
 *
 * Usage:
 *   node scripts/fetch-ga4.js                    # default metrics, last 28 days
 *   node scripts/fetch-ga4.js --days 14          # last 14 days
 *   node scripts/fetch-ga4.js --start 2026-01-01 --end 2026-01-31
 *
 * Output:
 *   knowledge/metrics/analytics/ga4-2026-02-24.json
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createRequire } from 'module';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { google } = require('googleapis');

// Configuration — update propertyId after running /connect-ga4
const CONFIG = {
  propertyId: '492555629',
  credentialsPath: path.join(__dirname, '../local/ga4-credentials.json'),
  outputDir: path.join(__dirname, '../knowledge/metrics/analytics'),
  defaultDays: 28,
  limits: {
    rows: 10000
  }
};

// Parse CLI arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    days: CONFIG.defaultDays
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
    console.error('3. Download the JSON key and save as local/ga4-credentials.json');
    console.error('4. Add the Service Account email to GA4 as a Viewer');
    console.error('\nOr run: /connect-ga4');
    process.exit(1);
  }

  const auth = new google.auth.GoogleAuth({
    keyFile: CONFIG.credentialsPath,
    scopes: ['https://www.googleapis.com/auth/analytics.readonly']
  });

  return auth;
}

// Fetch daily overview (sessions, users, pageviews by date)
async function fetchDailyOverview(analyticsdata, options) {
  console.log(`Fetching daily overview: ${options.startDate} → ${options.endDate}`);

  const response = await analyticsdata.properties.runReport({
    property: `properties/${CONFIG.propertyId}`,
    requestBody: {
      dateRanges: [{ startDate: options.startDate, endDate: options.endDate }],
      metrics: [
        { name: 'sessions' },
        { name: 'totalUsers' },
        { name: 'screenPageViews' },
        { name: 'bounceRate' },
        { name: 'averageSessionDuration' }
      ],
      dimensions: [{ name: 'date' }],
      orderBys: [{ dimension: { dimensionName: 'date' } }],
      limit: CONFIG.limits.rows
    }
  });

  return (response.data.rows || []).map(row => ({
    date: row.dimensionValues[0].value.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3'),
    sessions: parseInt(row.metricValues[0].value),
    users: parseInt(row.metricValues[1].value),
    pageviews: parseInt(row.metricValues[2].value),
    bounceRate: (parseFloat(row.metricValues[3].value) * 100).toFixed(1) + '%',
    avgSessionDuration: parseFloat(row.metricValues[4].value).toFixed(1) + 's'
  }));
}

// Fetch top pages
async function fetchTopPages(analyticsdata, options) {
  console.log('Fetching top pages...');

  const response = await analyticsdata.properties.runReport({
    property: `properties/${CONFIG.propertyId}`,
    requestBody: {
      dateRanges: [{ startDate: options.startDate, endDate: options.endDate }],
      metrics: [
        { name: 'screenPageViews' },
        { name: 'totalUsers' },
        { name: 'averageSessionDuration' }
      ],
      dimensions: [{ name: 'pagePath' }],
      orderBys: [{ metric: { metricName: 'screenPageViews' }, desc: true }],
      limit: 500
    }
  });

  return (response.data.rows || []).map(row => ({
    page: row.dimensionValues[0].value,
    pageviews: parseInt(row.metricValues[0].value),
    users: parseInt(row.metricValues[1].value),
    avgSessionDuration: parseFloat(row.metricValues[2].value).toFixed(1) + 's'
  }));
}

// Fetch traffic sources
async function fetchTrafficSources(analyticsdata, options) {
  console.log('Fetching traffic sources...');

  const response = await analyticsdata.properties.runReport({
    property: `properties/${CONFIG.propertyId}`,
    requestBody: {
      dateRanges: [{ startDate: options.startDate, endDate: options.endDate }],
      metrics: [
        { name: 'sessions' },
        { name: 'totalUsers' }
      ],
      dimensions: [
        { name: 'sessionDefaultChannelGroup' },
        { name: 'sessionSource' }
      ],
      orderBys: [{ metric: { metricName: 'sessions' }, desc: true }],
      limit: 200
    }
  });

  return (response.data.rows || []).map(row => ({
    channel: row.dimensionValues[0].value,
    source: row.dimensionValues[1].value,
    sessions: parseInt(row.metricValues[0].value),
    users: parseInt(row.metricValues[1].value)
  }));
}

// Generate output file path
function getOutputPath() {
  const today = new Date().toISOString().split('T')[0];
  return path.join(CONFIG.outputDir, `ga4-${today}.json`);
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
function printSummary(data) {
  console.log('\nSummary:');
  console.log(`   Sessions:     ${data.summary.totalSessions.toLocaleString()}`);
  console.log(`   Users:        ${data.summary.totalUsers.toLocaleString()}`);
  console.log(`   Pageviews:    ${data.summary.totalPageviews.toLocaleString()}`);
  console.log(`   Bounce Rate:  ${data.summary.avgBounceRate}`);

  console.log('\nTop 5 pages:');
  data.topPages.slice(0, 5).forEach((p, i) => {
    console.log(`   ${i + 1}. ${p.page} - ${p.pageviews} views, ${p.users} users`);
  });

  console.log('\nTop 5 traffic sources:');
  data.trafficSources.slice(0, 5).forEach((s, i) => {
    console.log(`   ${i + 1}. ${s.channel} / ${s.source} - ${s.sessions} sessions`);
  });
}

// Main
async function main() {
  try {
    if (CONFIG.propertyId === 'YOUR_GA4_PROPERTY_ID') {
      console.error('GA4 Property ID not configured.');
      console.error('Edit scripts/fetch-ga4.js and set CONFIG.propertyId to your GA4 property ID.');
      console.error('\nOr run: /connect-ga4');
      process.exit(1);
    }

    const options = parseArgs();
    const auth = await authenticate();
    const analyticsdata = google.analyticsdata({ version: 'v1beta', auth });

    const daily = await fetchDailyOverview(analyticsdata, options);
    const topPages = await fetchTopPages(analyticsdata, options);
    const trafficSources = await fetchTrafficSources(analyticsdata, options);

    // Compute totals
    const totals = daily.reduce((acc, d) => {
      acc.sessions += d.sessions;
      acc.users += d.users;
      acc.pageviews += d.pageviews;
      return acc;
    }, { sessions: 0, users: 0, pageviews: 0 });

    const avgBounceRate = daily.length > 0
      ? (daily.reduce((sum, d) => sum + parseFloat(d.bounceRate), 0) / daily.length).toFixed(1) + '%'
      : '0%';

    const data = {
      meta: {
        propertyId: CONFIG.propertyId,
        startDate: options.startDate,
        endDate: options.endDate,
        fetchedAt: new Date().toISOString()
      },
      summary: {
        totalSessions: totals.sessions,
        totalUsers: totals.users,
        totalPageviews: totals.pageviews,
        avgBounceRate
      },
      daily,
      topPages,
      trafficSources
    };

    const outputPath = getOutputPath();
    saveData(data, outputPath);
    printSummary(data);

    console.log('\nDone.');
  } catch (error) {
    console.error('Error:', error.message);
    if (error.code === 403) {
      console.error('\nEnsure the Service Account has Viewer access in GA4.');
    }
    process.exit(1);
  }
}

main();
