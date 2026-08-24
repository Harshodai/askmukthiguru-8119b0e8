#!/usr/bin/env node
/**
 * Bundle Size Budget Guard
 *
 * Checks production build assets in `dist/assets` against defined budgets:
 * 1. Max individual JS chunk size: < 800 kB (0.8 MB)
 * 2. Total eager/core application JS size: < 3 MB. This is the JS referenced
 *    by dist/index.html, excluding locale chunks and route-lazy code.
 * 3. Total overall JS size (including all lazy routes and localized dictionaries): < 5 MB
 *
 * Exits with non-zero code if any budget is exceeded or if dist/assets is missing.
 *
 * Usage:
 *   npm run build
 *   node scripts/check-bundle-budget.mjs
 */

import { readdirSync, statSync, existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'dist');
const assetsDir = join(distDir, 'assets');

function parseBudgetValue(raw, defaultValue, name, unitMultiplier) {
  const parsed = Number(raw ?? defaultValue);
  if (!Number.isFinite(parsed) || Number.isNaN(parsed) || parsed <= 0) {
    console.error(
      `[bundle-budget] ERROR: ${name} must be a finite positive number, got "${raw ?? defaultValue}".`
    );
    process.exit(1);
  }
  return parsed * unitMultiplier;
}

// Configurable budgets (in bytes)
const MAX_CHUNK_BYTES = parseBudgetValue(
  process.env.BUNDLE_MAX_CHUNK_KB,
  800,
  'BUNDLE_MAX_CHUNK_KB',
  1024
);
const MAX_CORE_TOTAL_BYTES = parseBudgetValue(
  process.env.BUNDLE_MAX_CORE_MB,
  3.0,
  'BUNDLE_MAX_CORE_MB',
  1024 * 1024
);
const MAX_TOTAL_BYTES = parseBudgetValue(
  process.env.BUNDLE_MAX_TOTAL_MB,
  5.0,
  'BUNDLE_MAX_TOTAL_MB',
  1024 * 1024
);

if (!existsSync(distDir) || !existsSync(assetsDir)) {
  console.error('[bundle-budget] ERROR: dist/assets not found. Run "npm run build" first.');
  process.exit(1);
}

function getAllJsFiles(dir) {
  let files = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) {
      files = files.concat(getAllJsFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith('.js')) {
      const stats = statSync(fullPath);
      files.push({
        name: entry.name,
        relPath: relative(distDir, fullPath),
        size: stats.size,
      });
    }
  }
  return files;
}

const jsFiles = getAllJsFiles(assetsDir);

if (jsFiles.length === 0) {
  console.error('[bundle-budget] ERROR: No JS files found in dist/assets.');
  process.exit(1);
}

// Sort by size descending
jsFiles.sort((a, b) => b.size - a.size);

// Locale chunk identifier (e.g., te-*.js, hi-*.js, mr-*.js)
const isLocaleChunk = (name) => /^(hi|te|kn|ta|mr|bn|gu|ml|ur|or|pa|as|sa)-[A-Za-z0-9_-]+\.js$/.test(name);
const indexHtml = readFileSync(join(distDir, 'index.html'), 'utf8');
const eagerAssetNames = new Set(
  [...indexHtml.matchAll(/assets\/js\/([A-Za-z0-9_-]+\.js)/g)].map((match) => match[1]),
);
const isEagerCoreChunk = (file) => eagerAssetNames.has(file.name) && !isLocaleChunk(file.name);

let totalJsBytes = 0;
let coreJsBytes = 0;
const chunkViolations = [];

for (const file of jsFiles) {
  totalJsBytes += file.size;
  if (isEagerCoreChunk(file)) {
    coreJsBytes += file.size;
  }
  if (file.size >= MAX_CHUNK_BYTES) {
    chunkViolations.push(file);
  }
}

const formatKB = (bytes) => `${(bytes / 1024).toFixed(2)} kB`;
const formatMB = (bytes) => `${(bytes / (1024 * 1024)).toFixed(2)} MB`;

console.log('====================================================');
console.log('         AskMukthiGuru Frontend Bundle Budget       ');
console.log('====================================================');
console.log(`Total JS Files:       ${jsFiles.length}`);
console.log(`Largest Chunk:        ${jsFiles[0].name} (${formatKB(jsFiles[0].size)})`);
console.log(`Max Chunk Budget:     < ${formatKB(MAX_CHUNK_BYTES)}`);
console.log(`Core JS Size:         ${formatMB(coreJsBytes)} (Budget: < ${formatMB(MAX_CORE_TOTAL_BYTES)})`);
console.log(`Total JS Size:        ${formatMB(totalJsBytes)} (Budget: < ${formatMB(MAX_TOTAL_BYTES)})`);
console.log('----------------------------------------------------');
console.log('Top 10 Largest Chunks:');
for (const file of jsFiles.slice(0, 10)) {
  const isLocale = isLocaleChunk(file.name) ? ' [locale]' : '';
  const isEager = isEagerCoreChunk(file) ? ' [eager-core]' : '';
  console.log(`  - ${formatKB(file.size).padStart(10)}  ${file.relPath}${isLocale}${isEager}`);
}
console.log('====================================================');

let hasError = false;

if (chunkViolations.length > 0) {
  hasError = true;
  console.error(`\n[bundle-budget] FAIL — ${chunkViolations.length} chunk(s) exceeded max chunk size (${formatKB(MAX_CHUNK_BYTES)}):`);
  for (const v of chunkViolations) {
    console.error(`  - ${v.relPath}: ${formatKB(v.size)} (exceeded by ${formatKB(v.size - MAX_CHUNK_BYTES)})`);
  }
}

if (coreJsBytes >= MAX_CORE_TOTAL_BYTES) {
  hasError = true;
  console.error(`\n[bundle-budget] FAIL — Core JS total (${formatMB(coreJsBytes)}) reached/exceeded budget of ${formatMB(MAX_CORE_TOTAL_BYTES)}.`);
}

if (totalJsBytes >= MAX_TOTAL_BYTES) {
  hasError = true;
  console.error(`\n[bundle-budget] FAIL — Total JS size (${formatMB(totalJsBytes)}) reached/exceeded budget of ${formatMB(MAX_TOTAL_BYTES)}.`);
}

if (hasError) {
  console.error('\n[bundle-budget] Bundle budget check FAILED.');
  process.exit(1);
}

console.log(`\n[bundle-budget] OK — all JS chunks and totals within budget limits.`);
process.exit(0);
