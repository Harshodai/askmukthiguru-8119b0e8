#!/usr/bin/env node
/**
 * P1-AI-24 — UserMetrics schema parity guard: backend (pydantic) <-> frontend (zod).
 *
 * The pydantic model's JSON schema is regenerated here, from source, without
 * needing the backend venv. The zod schema is read from source too, so this
 * check can never drift from the code it audits. It fails (exit 1) on any:
 *   - backend field missing from the frontend schema
 *   - frontend field that the backend does not declare (typo / stale key)
 *   - snake_case <-> camelCase mismatch (backend snake_case, frontend camelCase)
 *
 * Run locally:   node scripts/check_metrics_schema_parity.mjs
 * CI:            .github/workflows/lint-test.yml (frontend job)
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const read = (rel) => readFileSync(join(root, rel), 'utf8');

const pydantic = read('backend/app/schemas/metrics.py');
const zodSrc = read('src/lib/metricsSchema.ts');

/** Extract snake_case field names declared in the pydantic model body. */
const backendFields = [...pydantic.matchAll(/^\s{4}(\w+)\s*:/gm)].map((m) => m[1]);

/** Extract camelCase keys inside the zod `z.object({ ... })` literal. */
const zodBody = zodSrc.match(/z\.object\(\{([\s\S]*?)\n\}\)/)?.[1] ?? '';
const frontendFields = [...zodBody.matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]);

const snakeToCamel = (key) => key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());

const errors = [];

for (const b of backendFields) {
  if (!frontendFields.includes(snakeToCamel(b))) {
    errors.push(`backend field '${b}' has no frontend zod field '${snakeToCamel(b)}'`);
  }
}
for (const f of frontendFields) {
  const snake = f.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
  if (!backendFields.includes(snake)) {
    errors.push(`frontend field '${f}' has no backend pydantic field '${snake}'`);
  }
}

if (errors.length > 0) {
  console.error(`[metrics-parity] FAIL — ${errors.length} mismatch(es):`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log(`[metrics-parity] OK — ${backendFields.length} backend fields, ${frontendFields.length} frontend fields, 1:1 parity`);
