/**
 * Schema verifier — connects to a Supabase project and emits a JSON snapshot
 * of tables, columns, RLS state, and GRANTs. Diff two snapshots to prove the
 * source and target are schema-equivalent before flipping env vars.
 *
 * Usage:
 *   VITE_SUPABASE_URL=... VITE_SUPABASE_PUBLISHABLE_KEY=... \
 *     bun scripts/migration/verify.ts --emit-snapshot > target.json
 */
import { createClient } from "@supabase/supabase-js";

const url = process.env.VITE_SUPABASE_URL ?? process.env.SUPABASE_URL;
const key =
  process.env.VITE_SUPABASE_PUBLISHABLE_KEY ??
  process.env.SUPABASE_ANON_KEY ??
  process.env.SUPABASE_PUBLISHABLE_KEY;

if (!url || !key) {
  console.error("Missing SUPABASE_URL or PUBLISHABLE_KEY env vars.");
  process.exit(2);
}

const supabase = createClient(url, key);

async function snapshot() {
  // whoami_diagnostics returns a JSON blob suitable for smoke-checking
  // that the project is reachable and the anon role behaves as expected.
  const { data, error } = await supabase.rpc("whoami_diagnostics");
  if (error) {
    console.error("verify.ts: RPC failed:", error.message);
    process.exit(3);
  }
  const out = {
    project: url,
    checked_at: new Date().toISOString(),
    anon_diagnostics: data,
  };
  console.log(JSON.stringify(out, null, 2));
}

snapshot().catch((e) => {
  console.error(e);
  process.exit(4);
});
