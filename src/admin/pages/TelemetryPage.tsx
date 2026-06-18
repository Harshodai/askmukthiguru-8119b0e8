import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ExternalLink, AlertCircle } from "lucide-react";
import { useState } from "react";

export default function TelemetryPage() {
  const jaegerUrl = import.meta.env.VITE_JAEGER_UI_URL || "http://localhost:16686";
  const [iframeError, setIframeError] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">System Telemetry</h1>
          <p className="text-sm text-muted-foreground">
            Real-time distributed tracing, token usage, and LangChain execution paths via Jaeger.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <a href={jaegerUrl} target="_blank" rel="noreferrer">
            <ExternalLink className="h-4 w-4" />
            Open Jaeger
          </a>
        </Button>
      </div>

      <Card className="overflow-hidden border-2 border-primary/20 shadow-xl rounded-xl">
        <div className="border-b border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
          If the embedded view is unavailable, open Jaeger directly at{" "}
          <a href={jaegerUrl} target="_blank" rel="noreferrer" className="text-primary underline">
            {jaegerUrl}
          </a>.
        </div>
        <CardContent className="p-0 h-[75vh] min-h-[600px] relative">
          {iframeError ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-6">
              <AlertCircle className="w-10 h-10 text-muted-foreground/60" />
              <div>
                <h3 className="text-lg font-medium">Jaeger UI unavailable</h3>
                <p className="text-sm text-muted-foreground mt-1 max-w-md">
                  Jaeger does not allow iframe embedding (X-Frame-Options). Click below to open it in a new tab.
                </p>
              </div>
              <Button asChild>
                <a href={jaegerUrl} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-4 w-4 mr-2" />
                  Open Jaeger in new tab
                </a>
              </Button>
            </div>
          ) : (
            <iframe
              src={jaegerUrl}
              className="w-full h-full border-0"
              title="Jaeger Telemetry"
              sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
              onError={() => setIframeError(true)}
            />
          )}
        </CardContent>
      </Card>

      <div className="bg-primary/5 p-4 rounded-lg border border-primary/10">
        <h3 className="text-sm font-medium text-primary flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary"></span>
          </span>
          Observability Note
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Traces are captured automatically for all RAG pipeline nodes. Use the Jaeger UI above to inspect latency,
          provider calls, and token consumption for each seeker's query.
        </p>
      </div>
    </div>
  );
}
