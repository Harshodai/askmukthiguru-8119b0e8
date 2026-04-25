import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus } from "lucide-react";
import type { AlertRule } from "@/admin/types";
import { upsertAlertRule } from "@/admin/lib/mockData";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

const METRICS: AlertRule["metric"][] = [
  "hallucination_rate",
  "p95_latency_ms",
  "error_rate",
  "cost_burn_usd",
  "retrieval_hit_rate",
];

const COMPARATORS: AlertRule["comparator"][] = [">", ">=", "<", "<="];

export function AlertRuleBuilder() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [rule, setRule] = useState<AlertRule>({
    id: "",
    name: "",
    metric: "hallucination_rate",
    comparator: ">",
    threshold: 0.15,
    window_minutes: 60,
    channel: "email",
    target: "",
    active: true,
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <Plus className="h-4 w-4" />
          New rule
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New alert rule</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Name</Label>
            <Input
              value={rule.name}
              onChange={(e) => setRule({ ...rule, name: e.target.value })}
              placeholder="High hallucination rate"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-xs">Metric</Label>
              <Select value={rule.metric} onValueChange={(v) => setRule({ ...rule, metric: v as AlertRule["metric"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {METRICS.map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Comparator</Label>
              <Select value={rule.comparator} onValueChange={(v) => setRule({ ...rule, comparator: v as AlertRule["comparator"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {COMPARATORS.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Threshold</Label>
              <Input
                type="number"
                step="0.01"
                value={rule.threshold}
                onChange={(e) => setRule({ ...rule, threshold: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-xs">Window (min)</Label>
              <Input
                type="number"
                value={rule.window_minutes}
                onChange={(e) => setRule({ ...rule, window_minutes: Number(e.target.value) })}
              />
            </div>
            <div>
              <Label className="text-xs">Channel</Label>
              <Select value={rule.channel} onValueChange={(v) => setRule({ ...rule, channel: v as AlertRule["channel"] })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="email">email</SelectItem>
                  <SelectItem value="webhook">webhook</SelectItem>
                  <SelectItem value="slack">slack</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Target</Label>
              <Input
                value={rule.target}
                onChange={(e) => setRule({ ...rule, target: e.target.value })}
                placeholder="oncall@org"
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            onClick={async () => {
              if (!rule.name) { toast.error("Name is required"); return; }
              const finalRule = { ...rule, id: rule.id || `rule_${Date.now()}` };
              await upsertAlertRule(finalRule);
              qc.invalidateQueries({ queryKey: ["admin", "alert-rules"] });
              toast.success("Rule saved");
              setOpen(false);
            }}
          >
            Save rule
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
