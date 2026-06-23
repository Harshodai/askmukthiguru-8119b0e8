import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Search, Loader2 } from "lucide-react";
import { useAskData } from "@/admin/hooks/useAskData";

interface AskDataPanelProps {
  kpiContext?: string;
}

export function AskDataPanel({ kpiContext }: AskDataPanelProps) {
  const [q, setQ] = useState("");
  const { result, error, loading, ask } = useAskData();

  const examples = [
    "What is the current p95 latency?",
    "Serene Mind triggers this week",
    "How much has the platform cost today?",
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-primary" />
          Ask the data
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) ask(q.trim(), kpiContext);
          }}
          className="flex gap-2"
        >
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="e.g. What is the current hallucination rate?"
            disabled={loading}
          />
          <Button type="submit" size="icon" disabled={loading || !q.trim()}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
          </Button>
        </form>

        <div className="flex flex-wrap gap-1.5">
          {examples.map((e) => (
            <Button
              key={e}
              variant="outline"
              size="sm"
              className="text-xs h-7"
              disabled={loading}
              onClick={() => {
                setQ(e);
                ask(e, kpiContext);
              }}
            >
              {e}
            </Button>
          ))}
        </div>

        {loading && (
          <div className="text-xs text-muted-foreground flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            Thinking…
          </div>
        )}

        {error && (
          <div className="text-xs text-destructive bg-destructive/10 rounded p-2">{error}</div>
        )}

        {result && !loading && (
          <div className="text-sm text-foreground bg-muted/40 rounded-lg p-3 leading-relaxed border border-border/40">
            {result}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
