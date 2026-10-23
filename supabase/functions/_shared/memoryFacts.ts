/** Strictly validate extraction-model output before treating it as memory. */
export function parseExtractedFacts(raw: unknown): string[] {
  if (typeof raw !== "string" || raw.length > 16_384) return [];
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!decoded || typeof decoded !== "object") return [];
  const facts = (decoded as { facts?: unknown }).facts;
  if (!Array.isArray(facts)) return [];
  return facts
    .filter((fact: unknown): fact is string => typeof fact === "string")
    .map((fact: string) => fact.trim().slice(0, 1000))
    .filter((fact: string) => fact.length >= 10)
    .slice(0, 3);
}
