import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Search, Loader2 } from "lucide-react";
import { supabase } from "@/integrations/supabase/client";

interface AskDataPanelProps {
  kpiContext?: string;
}

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";

async function apiPost(path: string, body: unknown) {
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const response = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`API error ${response.status}: ${errText}`);
  }
  return response.json();
}

export function AskDataPanel({ kpiContext }: AskDataPanelProps) {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function ask(question: string) {
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await apiPost("/api/admin/ask", {
        question,
        kpi_context: kpiContext ?? "",
      });
      if (data?.response) setResult(data.response);
      else setError(data?.error ?? "Empty response.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

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
            if (q.trim()) ask(q.trim());
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
                ask(e);
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
