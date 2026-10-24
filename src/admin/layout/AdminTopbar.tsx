import { useState } from "react";
import { format } from "date-fns";
import { CalendarIcon, RefreshCw, FlaskConical } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useAdminFilters, type RangePreset } from "@/admin/lib/filtersStore";
import { useTranslation } from 'react-i18next';

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export function AdminTopbar() {
const { t } = useTranslation();
  const { filters, setPreset, setRange, refresh } = useAdminFilters();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-14 py-2 px-3 sm:px-6 flex flex-wrap items-center justify-between gap-2 bg-card/40 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Badge variant="outline" className="gap-1.5 border-prana/50 text-prana bg-prana/5">
          <div className="h-1.5 w-1.5 rounded-full bg-prana" />
          Role Verified
        </Badge>

      </div>

      <div className="flex items-center gap-2">
        {/* Preset chips (desktop) / preset select (mobile) */}
        <div className="hidden md:flex items-center gap-1">
          {PRESETS.map((p) => (
            <Button
              key={p.value}
              size="sm"
              variant={filters.preset === p.value ? "secondary" : "ghost"}
              onClick={() => setPreset(p.value)}
            >
              {p.label}
            </Button>
          ))}
        </div>
        <select
          className="md:hidden min-h-[44px] rounded-md border border-input bg-background px-2 text-xs"
          aria-label="Date range preset"
          value={filters.preset === "custom" ? "custom" : filters.preset}
          onChange={(e) => {
            const v = e.target.value;
            if (v !== "custom") setPreset(v as RangePreset);
          }}
        >
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
          {filters.preset === "custom" && <option value="custom">Custom range</option>}
        </select>

        {/* Custom date range */}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant={filters.preset === "custom" ? "secondary" : "outline"}
              size="sm"
              className={cn("gap-2 min-h-[44px] justify-start text-xs sm:text-sm")}
            >
              <CalendarIcon className="h-4 w-4" />
              {format(filters.from, "MMM d, HH:mm")} –{" "}
              {format(filters.to, "MMM d, HH:mm")}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <Calendar
              mode="range"
              selected={{ from: filters.from, to: filters.to }}
              onSelect={(range) => {
                if (range?.from && range?.to) {
                  setRange(range.from, range.to, "custom");
                  setOpen(false);
                }
              }}
              numberOfMonths={1}
              className={cn("p-3 pointer-events-auto")}
            />
          </PopoverContent>
        </Popover>

        <Button size="icon" variant="ghost" onClick={refresh} title="Refresh" aria-label="Refresh" className="min-h-[44px] min-w-[44px]">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
