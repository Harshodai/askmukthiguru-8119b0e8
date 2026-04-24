import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useModelPricing } from "@/admin/hooks/useAdminData";

export default function SettingsPage() {
  const [retention, setRetention] = useState([90]);
  const [redactPii, setRedactPii] = useState(true);
  const { data: pricing } = useModelPricing();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Retention, redaction, and model cost configuration.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Retention & privacy</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <div className="flex justify-between mb-2">
              <span>Telemetry retention (days)</span>
              <span className="tabular-nums font-medium">{retention[0]}</span>
            </div>
            <Slider value={retention} onValueChange={setRetention} min={7} max={365} step={1} />
          </div>
          <div className="flex items-center justify-between">
            <span>PII redaction before persistence</span>
            <Switch checked={redactPii} onCheckedChange={setRedactPii} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model pricing (USD per 1k tokens)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Input</TableHead>
                <TableHead className="text-right">Output</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pricing?.map((p) => (
                <TableRow key={p.model}>
                  <TableCell className="font-mono text-xs">{p.model}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    ${p.input_per_1k.toFixed(4)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    ${p.output_per_1k.toFixed(4)}
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
