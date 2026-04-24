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

const PRESETS: { value: RangePreset; label: string }[] = [
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

export function AdminTopbar() {
  const { filters, setPreset, setRange, refresh } = useAdminFilters();
  const [open, setOpen] = useState(false);

  return (
    <div className="h-14 px-6 border-b border-border flex items-center justify-between gap-3 bg-card/40 backdrop-blur">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Badge variant="secondary" className="gap-1.5">
          <FlaskConical className="h-3 w-3" />
          UI PREVIEW · mock data
        </Badge>
        <span className="hidden md:inline">
          Cloud not connected — see <code className="text-xs">docs/admin/migration-plan.md</code>
        </span>
      </div>

      <div className="flex items-center gap-2">
        {/* Preset chips */}
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

        {/* Custom date range */}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant={filters.preset === "custom" ? "secondary" : "outline"}
              size="sm"
              className={cn("gap-2 min-w-[230px] justify-start")}
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
                }
              }}
              numberOfMonths={2}
              className={cn("p-3 pointer-events-auto")}
            />
          </PopoverContent>
        </Popover>

        <Button size="sm" variant="ghost" onClick={refresh} title="Refresh">
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
