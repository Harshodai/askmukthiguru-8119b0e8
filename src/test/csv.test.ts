import { describe, it, expect } from "vitest";
import { csvEscape, rowsToCsv } from "@/admin/lib/csv";

describe("csvEscape formula neutralization", () => {
  it("prefixes formula-leading characters with a single quote", () => {
    for (const bad of ["=1+1", "+SUM(A1)", "-2+3", "@cmd", "\t=1", "\r=1"]) {
      expect(csvEscape(bad).startsWith("'")).toBe(true);
    }
  });

  it("neutralizes and quotes a formula containing a comma", () => {
    expect(csvEscape("=HYPERLINK(\"https://evil.example\",\"x\")")).toBe(
      '"\'=HYPERLINK(""https://evil.example"",""x"")"',
    );
  });

  it("leaves ordinary values untouched", () => {
    expect(csvEscape("hello")).toBe("hello");
    expect(csvEscape(42)).toBe("42");
    expect(csvEscape(null)).toBe("");
    expect(csvEscape(undefined)).toBe("");
  });

  it("still quotes commas, quotes and newlines", () => {
    expect(csvEscape('a,"b"\nc')).toBe('"a,""b""\nc"');
  });
});

describe("rowsToCsv", () => {
  it("neutralizes user-controlled cells", () => {
    const csv = rowsToCsv(["query_text"], [{ query_text: "=cmd|'/c calc'!A1" }]);
    expect(csv).toBe("query_text\n'=cmd|'/c calc'!A1");
  });
});
