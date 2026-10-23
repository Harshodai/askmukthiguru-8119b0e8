import type { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";
import { getActiveMemoryConsentReceipt } from "./memoryConsent.ts";

type Receipt = {
  id: string;
  granted: boolean;
  revoked_at: string | null;
  event_sequence: number;
};

function fakeClient(data: Receipt[] | null, error: unknown = null) {
  const calls: Array<[string, unknown?]> = [];
  const result = {
    data,
    error,
  };
  const query = {
    select(columns: string) { calls.push(["select", columns]); return this; },
    eq(column: string, value: string) { calls.push([column, value]); return this; },
    order(column: string, opts: { ascending: boolean }) { calls.push(["order", column, opts.ascending]); return this; },
    limit(value: number) { calls.push(["limit", value]); return Promise.resolve(result); },
  };
  const client = {
    from(table: string) { calls.push(["from", table]); return query; },
  };
  return { client: client as unknown as SupabaseClient, calls };
}

Deno.test("latest revocation denies consent even when an older grant exists", async () => {
  const fake = fakeClient([{
    id: "receipt-revoked",
    granted: false,
    revoked_at: "2026-10-21T10:00:00Z",
    event_sequence: 2,
  }]);
  const current = await getActiveMemoryConsentReceipt(fake.client, "user-1", "tenant-1");
  if (current !== null) throw new Error("latest revocation must deny consent");
  const orderIndex = fake.calls.findIndex(([method]) => method === "order");
  const limitIndex = fake.calls.findIndex(([method]) => method === "limit");
  if (orderIndex < 0 || orderIndex > limitIndex) {
    throw new Error("query must order consent events before limiting to latest");
  }
  if (fake.calls[orderIndex][1] !== "event_sequence" || fake.calls[orderIndex][2] !== false) {
    throw new Error("consent lookup must order event_sequence descending");
  }
});

Deno.test("latest active grant returns its exact receipt identity", async () => {
  const receipt = {
    id: "new-grant",
    granted: true,
    revoked_at: null,
    event_sequence: 3,
  };
  const fake = fakeClient([receipt]);
  const current = await getActiveMemoryConsentReceipt(fake.client, "user-1", "tenant-1");
  if (current?.id !== "new-grant") throw new Error("expected latest active receipt");
});

Deno.test("consent lookup errors fail closed by throwing", async () => {
  const fake = fakeClient(null, { code: "NETWORK_ERROR" });
  let threw = false;
  try {
    await getActiveMemoryConsentReceipt(fake.client, "user-1", "tenant-1");
  } catch (error) {
    threw = error instanceof Error && error.message === "memory_consent_lookup_failed";
  }
  if (!threw) throw new Error("consent datastore failure must not be treated as a grant");
});
