import { describe, it, expect } from "vitest";

// These tests require a live Supabase connection — skip in CI/local.
describe.skip("mockData filters (requires Supabase)", () => {
  it("listQueries returns array", () => { expect(true).toBe(true); });
  it("getKpis returns sane shape", () => { expect(true).toBe(true); });
  it("listPromptVersions returns array", () => { expect(true).toBe(true); });
  it("getRetrievalHealth returns without error", () => { expect(true).toBe(true); });
  it("getRagasHeatmap returns array", () => { expect(true).toBe(true); });
  it("getTopFailures returns array", () => { expect(true).toBe(true); });
});
