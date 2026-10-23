import { parseExtractedFacts } from "./memoryFacts.ts";

Deno.test("rejects malformed model output and non-string facts", () => {
  if (parseExtractedFacts("{not-json").length !== 0) throw new Error("malformed JSON must be ignored");
  const facts = parseExtractedFacts(JSON.stringify({
    facts: ["I practice meditation daily", { content: "not a string" }, "tiny", "I prefer quiet guidance"],
  }));
  if (facts.length !== 2) throw new Error("only meaningful string facts should survive");
  if (facts.some((fact) => fact.length > 1000)) throw new Error("facts must be bounded");
});

Deno.test("limits extracted facts to three", () => {
  const facts = parseExtractedFacts(JSON.stringify({
    facts: [
      "I practice meditation daily",
      "I prefer quiet guidance",
      "I am working on patience",
      "I want to improve gratitude",
    ],
  }));
  if (facts.length !== 3) throw new Error("at most three facts may be stored per turn");
});

Deno.test("rejects oversized raw model output", () => {
  if (parseExtractedFacts("x".repeat(16_385)).length !== 0) {
    throw new Error("oversized model output must be ignored");
  }
});
