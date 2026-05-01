import { describe, it, expect } from "vitest";

// These tests require a live Supabase connection — skip in CI/local.
// Re-enable when running against a real backend.
const describeWithDb = describe.skip;

describeWithDb("mockData filters (requires Supabase)", () => {
  const {
    listQueries,
    getKpis,
    listPromptVersions,
    getRetrievalHealth,
    getRagasHeatmap,
    getTopFailures,
  } = await import("./mockData");
  getKpis,
  listPromptVersions,
  getRetrievalHealth,
  getRagasHeatmap,
  getTopFailures,
} from "./mockData";

describe("mockData filters", () => {
  it("listQueries returns array", async () => {
    const all = await listQueries({ limit: 500 });
    expect(Array.isArray(all)).toBe(true);
  });

  it("listQueries respects search filter without error", async () => {
    const filtered = await listQueries({ search: "anxious", limit: 500 });
    expect(Array.isArray(filtered)).toBe(true);
  });

  it("getKpis returns sane shape", async () => {
    const k = await getKpis({});
    expect(k.total_queries).toBeGreaterThanOrEqual(0);
    expect(k.hallucination_rate).toBeGreaterThanOrEqual(0);
    expect(k.hallucination_rate).toBeLessThanOrEqual(1);
  });

  it("listPromptVersions returns array", async () => {
    const ps = await listPromptVersions();
    expect(Array.isArray(ps)).toBe(true);
  });

  it("getRetrievalHealth returns without error", async () => {
    const h = await getRetrievalHealth({});
    expect(h === null || typeof h === "object").toBe(true);
  });

  it("getRagasHeatmap returns array", async () => {
    const cells = await getRagasHeatmap({}, 5);
    expect(Array.isArray(cells)).toBe(true);
  });

  it("getTopFailures returns array", async () => {
    const f = await getTopFailures({}, 5);
    expect(Array.isArray(f)).toBe(true);
  });
});
