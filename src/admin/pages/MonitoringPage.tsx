import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { LineChart, ExternalLink, RefreshCw, AlertCircle } from "lucide-react";

export default function MonitoringPage() {
  const [refreshKey, setRefreshKey] = useState(0);

  // Read Grafana URL from environment variables, fallback to local development URL.
  // Add kiosk mode to hide Grafana's sidebar navigation for a cleaner embed experience.
  const baseGrafanaUrl = import.meta.env.VITE_GRAFANA_URL || "http://localhost:3000";
  const embedUrl = `${baseGrafanaUrl}/d/mukthiguru/mukthi-guru-performance-monitoring?orgId=1&kiosk=tv&theme=dark&refresh=5s&_t=${refreshKey}`;

  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <div className="space-y-6 p-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <LineChart className="h-8 w-8 text-primary" />
            Performance Monitoring
          </h1>
          <p className="text-muted-foreground mt-1">
            Real-time analytics, API latency profiles, system metrics, and cache telemetry.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            className="flex items-center gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
          <Button
            variant="default"
            size="sm"
            asChild
          >
            <a
              href={`${baseGrafanaUrl}/d/mukthiguru/mukthi-guru-performance-monitoring?orgId=1`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2"
            >
              <ExternalLink className="h-4 w-4" />
              Open in Grafana
            </a>
          </Button>
        </div>
      </div>

      {/* Main Monitoring Frame */}
      <Card className="border-border/40 bg-card/60 backdrop-blur-md overflow-hidden">
        <CardContent className="p-0">
          <div className="relative w-full" style={{ height: "680px" }}>
            <iframe
              src={embedUrl}
              title="Grafana Performance Monitoring"
              width="100%"
              height="100%"
              frameBorder="0"
              className="w-full h-full bg-card"
              allowFullScreen
            />
          </div>
        </CardContent>
      </Card>

      {/* Auxiliary Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="border-border/30 bg-card/40">
          <CardContent className="p-5 space-y-3">
            <h3 className="font-semibold text-base flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-primary" />
              Key System SLOs
            </h3>
            <ul className="text-sm space-y-2 text-muted-foreground list-disc pl-5">
              <li>
                <strong className="text-foreground">Time-to-First-Token (TTFT)</strong>: Goal &lt; 2s (P95) for fast path queries.
              </li>
              <li>
                <strong className="text-foreground">Semantic Cache Hit Rate</strong>: Target &gt; 35% overall database hit-to-miss ratio.
              </li>
              <li>
                <strong className="text-foreground">Error Rate Gating</strong>: Threshold is &lt; 1% API error count.
              </li>
              <li>
                <strong className="text-foreground">RAG Confidence Gating</strong>: Answers with scores below <code className="text-primary bg-primary/10 px-1.5 py-0.5 rounded">4.0</code> are filtered out.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="border-border/30 bg-card/40">
          <CardContent className="p-5 space-y-3">
            <h3 className="font-semibold text-base">Dashboard Details</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              This panel is fully provisioned inside the local Docker stack utilizing Prometheus to scrape
              metrics from the FastAPI <code className="text-primary bg-primary/10 px-1 py-0.5 rounded">/metrics</code> endpoint.
            </p>
            <p className="text-xs text-muted-foreground leading-relaxed">
              To configure alerting thresholds or customize panels, open Grafana directly using the top-right button
              (default credentials: <code className="bg-muted px-1.5 py-0.5 rounded text-foreground">admin / admin</code>).
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
