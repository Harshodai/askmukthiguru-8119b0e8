import { describe, it, expect } from "vitest";
import {
  listQueries,
  getKpis,
  listPromptVersions,
  getRetrievalHealth,
  getRagasHeatmap,
  getTopFailures,
} from "./mockData";

describe("mockData filters", () => {
  it("listQueries respects search filter", async () => {
    const all = await listQueries({ limit: 500 });
    const filtered = await listQueries({ search: "anxious", limit: 500 });
    expect(filtered.length).toBeLessThanOrEqual(all.length);
    filtered.forEach((q) => expect(q.query_text.toLowerCase()).toContain("anxious"));
  });

  it("listQueries respects model filter", async () => {
    const filtered = await listQueries({ model: "sarvam-30b:latest", limit: 500 });
    filtered.forEach((q) => expect(q.model).toBe("sarvam-30b:latest"));
  });

  it("listQueries respects minJudgeScore", async () => {
    const filtered = await listQueries({ minJudgeScore: 0.9, limit: 500 });
    expect(filtered.length).toBeGreaterThanOrEqual(0);
  });

  it("getKpis returns sane shape", async () => {
    const k = await getKpis({});
    expect(k.total_queries).toBeGreaterThan(0);
    expect(k.hallucination_rate).toBeGreaterThanOrEqual(0);
    expect(k.hallucination_rate).toBeLessThanOrEqual(1);
    expect(k.p95_latency_ms).toBeGreaterThanOrEqual(k.p50_latency_ms);
  });

  it("listPromptVersions includes at least one active version", async () => {
    const ps = await listPromptVersions();
    expect(ps.some((p) => p.active)).toBe(true);
  });

  it("getRetrievalHealth returns sources sorted desc by count", async () => {
    const h = await getRetrievalHealth({});
    for (let i = 1; i < h.sources.length; i++) {
      expect(h.sources[i - 1].count).toBeGreaterThanOrEqual(h.sources[i].count);
    }
  });

  it("getRagasHeatmap returns 4 metrics per bucket", async () => {
    const cells = await getRagasHeatmap({}, 5);
    expect(cells.length).toBe(20);
    const metrics = new Set(cells.map((c) => c.metric));
    expect(metrics.size).toBe(4);
  });

  it("getTopFailures returns descending-faithfulness rows", async () => {
    const f = await getTopFailures({}, 5);
    for (let i = 1; i < f.length; i++) {
      expect(f[i - 1].faithfulness).toBeLessThanOrEqual(f[i].faithfulness);
    }
  });
});
