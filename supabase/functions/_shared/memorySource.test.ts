import { isMissingColumnError, sanitizeSourceConversationId } from "./memorySource.ts";

Deno.test("accepts uuid and short ids, rejects everything else", () => {
  const uuid = "3f2b8c1e-9a4d-4e6f-8a1b-2c3d4e5f6a7b";
  if (sanitizeSourceConversationId(uuid) !== uuid) throw new Error("uuid must pass");
  if (sanitizeSourceConversationId("  conv_1  ") !== "conv_1") throw new Error("id must be trimmed");
  for (const bad of [undefined, null, 5, "", " ", "a b", "../x", "x/y", "<script>", "a".repeat(201), "-lead"]) {
    if (sanitizeSourceConversationId(bad) !== null) throw new Error(`must reject ${String(bad)}`);
  }
});

Deno.test("detects a missing-column error only", () => {
  if (!isMissingColumnError({ code: "42703" })) throw new Error("42703 is a missing column");
  if (!isMissingColumnError({ code: "PGRST204" })) throw new Error("PGRST204 is a missing column");
  if (isMissingColumnError({ code: "23505" })) throw new Error("other errors must not be swallowed");
  if (isMissingColumnError(null)) throw new Error("null is not an error");
});
