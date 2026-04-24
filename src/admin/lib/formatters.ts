export const fmtPct = (v: number, digits = 1) =>
  `${(v * 100).toFixed(digits)}%`;

export const fmtMs = (v: number) =>
  v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`;

export const fmtUsd = (v: number) =>
  v >= 1
    ? `$${v.toFixed(2)}`
    : v >= 0.01
      ? `$${v.toFixed(3)}`
      : `$${v.toFixed(5)}`;

export const fmtInt = (v: number) => v.toLocaleString();

export const fmtDateTime = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
};

export const truncate = (s: string, max = 80) =>
  s.length > max ? `${s.slice(0, max - 1)}…` : s;
