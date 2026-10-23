// Shared CSV helpers for admin exports.
// Neutralizes spreadsheet formula injection: any cell whose text begins with
// =, +, -, @, tab, or carriage return is prefixed with a single quote so
// spreadsheet apps render it as text instead of executing it.

const FORMULA_PREFIX = /^[=+\-@\t\r]/;

export function csvEscape(v: unknown): string {
  if (v == null) return "";
  let s = typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : JSON.stringify(v);
  if (FORMULA_PREFIX.test(s)) s = `'${s}`;
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function rowsToCsv(headers: string[], rows: Array<Record<string, unknown>>): string {
  const head = headers.map(csvEscape).join(",");
  const safeRows = Array.isArray(rows) ? rows : [];
  const body = safeRows
    .map((r) => headers.map((h) => csvEscape(r?.[h])).join(","))
    .join("\n");
  return `${head}\n${body}`;
}

export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
