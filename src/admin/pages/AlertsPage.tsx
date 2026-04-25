import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { useAlertEvents, useAlertRules } from "@/admin/hooks/useAdminData";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fmtDateTime } from "@/admin/lib/formatters";
import { upsertAlertRule } from "@/admin/lib/mockData";
import { useQueryClient } from "@tanstack/react-query";
import { AlertRuleBuilder } from "@/admin/components/AlertRuleBuilder";

export default function AlertsPage() {
  const { data: rules } = useAlertRules();
  const { data: events } = useAlertEvents();
  const qc = useQueryClient();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <p className="text-sm text-muted-foreground">
          Rules evaluated periodically; fired events appear below.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Rules</CardTitle>
          <AlertRuleBuilder />
        </CardHeader>
        <CardContent className="space-y-2">
          {rules?.map((r) => (
            <div
              key={r.id}
              className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
            >
              <div className="flex-1">
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-muted-foreground font-mono">
                  {r.metric} {r.comparator} {r.threshold} (window {r.window_minutes}m → {r.channel}:{" "}
                  {r.target})
                </div>
              </div>
              <Switch
                checked={r.active}
                onCheckedChange={async (v) => {
                  await upsertAlertRule({ ...r, active: v });
                  qc.invalidateQueries({ queryKey: ["admin", "alert-rules"] });
                }}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Recently fired</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events?.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="text-xs">{fmtDateTime(e.fired_at)}</TableCell>
                  <TableCell>{e.rule_name}</TableCell>
                  <TableCell className="text-right tabular-nums">{e.value.toFixed(3)}</TableCell>
                  <TableCell>
                    {e.resolved_at ? (
                      <Badge variant="secondary">resolved</Badge>
                    ) : (
                      <Badge variant="destructive">firing</Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
