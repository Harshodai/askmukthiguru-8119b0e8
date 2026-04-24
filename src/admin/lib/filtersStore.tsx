import { createContext, useContext, useState, ReactNode, useCallback } from "react";

export type RangePreset = "1h" | "24h" | "7d" | "30d" | "custom";

export interface AdminFilters {
  from: Date;
  to: Date;
  preset: RangePreset;
}

interface Ctx {
  filters: AdminFilters;
  setRange: (from: Date, to: Date, preset?: RangePreset) => void;
  setPreset: (preset: RangePreset) => void;
  refreshKey: number;
  refresh: () => void;
}

const FiltersContext = createContext<Ctx | null>(null);

const presetToRange = (preset: RangePreset): { from: Date; to: Date } => {
  const to = new Date();
  const from = new Date();
  if (preset === "1h") from.setHours(to.getHours() - 1);
  else if (preset === "24h") from.setDate(to.getDate() - 1);
  else if (preset === "7d") from.setDate(to.getDate() - 7);
  else from.setDate(to.getDate() - 30);
  return { from, to };
};

export function AdminFiltersProvider({ children }: { children: ReactNode }) {
  const initial = presetToRange("7d");
  const [filters, setFilters] = useState<AdminFilters>({
    from: initial.from,
    to: initial.to,
    preset: "7d",
  });
  const [refreshKey, setRefreshKey] = useState(0);

  const setRange = useCallback((from: Date, to: Date, preset: RangePreset = "custom") => {
    setFilters({ from, to, preset });
  }, []);

  const setPreset = useCallback((preset: RangePreset) => {
    if (preset === "custom") return;
    const { from, to } = presetToRange(preset);
    setFilters({ from, to, preset });
  }, []);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  return (
    <FiltersContext.Provider value={{ filters, setRange, setPreset, refreshKey, refresh }}>
      {children}
    </FiltersContext.Provider>
  );
}

export function useAdminFilters() {
  const ctx = useContext(FiltersContext);
  if (!ctx) throw new Error("useAdminFilters must be used within AdminFiltersProvider");
  return ctx;
}
