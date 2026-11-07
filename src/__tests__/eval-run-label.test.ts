// ADV-04: the admin "Run eval" button scores a general model, not the product.
// The label must stay on the page, on the button and in what the run stores.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "..", "..");
const read = (p: string) => readFileSync(resolve(root, p), "utf8");

describe("ADV-04 eval-run is labelled as model-only", () => {
  it("edge function says it does not test the product and stores the scope", () => {
    const src = read("supabase/functions/eval-run/index.ts");
    expect(src).toMatch(/NOT the product/);
    expect(src).toMatch(/scope:\s*"model_only_not_product"/);
    expect(src).toMatch(/judge_is_answerer:\s*true/);
  });

  it("admin page shows the caveat and the button names the scope", () => {
    const src = read("src/admin/pages/EvalsPage.tsx");
    expect(src).toMatch(/does not test\s+the product/i);
    expect(src).toMatch(/Run model-only eval/);
    expect(src).not.toMatch(/>\s*Run eval\s*</);
  });

  it("api helper documents the scope", () => {
    expect(read("src/admin/lib/api.ts")).toMatch(/model-only/i);
  });
});
