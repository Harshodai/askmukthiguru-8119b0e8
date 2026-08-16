export const fmtPct = (v?: number | null, digits = 1) => {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '0%';
  return `${(v * 100).toFixed(digits)}%`;
};

export const fmtMs = (v?: number | null) => {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '0ms';
  return v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`;
};

export const fmtUsd = (v?: number | null) => {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '$0.00';
  return v >= 1
    ? `$${v.toFixed(2)}`
    : v >= 0.01
      ? `$${v.toFixed(3)}`
      : `$${v.toFixed(5)}`;
};

export const fmtInr = (v?: number | null) => {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '₹0.00';
  return v >= 1
    ? `₹${v.toFixed(2)}`
    : v >= 0.01
      ? `₹${v.toFixed(3)}`
      : `₹${v.toFixed(5)}`;
};

export const fmtInt = (v?: number | null) => {
  if (v == null || typeof v !== 'number' || Number.isNaN(v)) return '0';
  return v.toLocaleString();
};

export const fmtDateTime = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export const fmtDate = (iso?: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "2-digit",
    year: "numeric",
  });
};

export const truncate = (s?: string | null, max = 80) => {
  if (s == null) return '';
  const str = typeof s === 'string' ? s : String(s);
  return str.length > max ? `${str.slice(0, max - 1)}…` : str;
};

