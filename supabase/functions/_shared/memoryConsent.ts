import { type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

export type MemoryConsentReceipt = {
  id: string;
  granted: boolean;
  revoked_at: string | null;
  event_sequence: number;
};

export function isActiveMemoryConsentReceipt(value: unknown): value is MemoryConsentReceipt {
  if (!value || typeof value !== "object") return false;
  const receipt = value as Partial<MemoryConsentReceipt>;
  return (
    typeof receipt.id === "string" &&
    receipt.id.length > 0 &&
    receipt.granted === true &&
    receipt.revoked_at === null &&
    Number.isFinite(receipt.event_sequence)
  );
}

/**
 * Consent is an append-only event history. Read the latest event first, then
 * decide whether it is an active grant. Filtering for granted=true before
 * ordering resurrects an older grant after a later revocation.
 *
 * Throws on datastore errors so request handlers can distinguish unavailable
 * consent infrastructure from a deliberate opt-out. Callers must fail closed.
 */
export async function getActiveMemoryConsentReceipt(
  client: SupabaseClient,
  userId: string,
  tenantId: string,
): Promise<MemoryConsentReceipt | null> {
  if (!userId || !tenantId) return null;

  const { data, error } = await client
    .from("memory_consent_receipts")
    .select("id,granted,revoked_at,event_sequence")
    .eq("user_id", userId)
    .eq("tenant_id", tenantId)
    .eq("consent_version", "memory-v1")
    .order("event_sequence", { ascending: false })
    .limit(1);

  if (error) throw new Error("memory_consent_lookup_failed");
  if (!Array.isArray(data) || data.length === 0) return null;

  const latest = data[0];
  return isActiveMemoryConsentReceipt(latest) ? (latest as MemoryConsentReceipt) : null;
}
