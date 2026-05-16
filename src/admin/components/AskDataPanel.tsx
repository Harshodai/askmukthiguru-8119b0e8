import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Search, Loader2 } from "lucide-react";
import { sendMessage } from "@/lib/aiService";

const ADMIN_SYSTEM_PROMPT = `You are an AI analytics assistant for the AskMukthiGuru admin dashboard.
You have access to platform metrics. Answer admin questions about query volume, latency, hallucination rates,
costs, serene mind triggers, and platform health concisely and accurately.
If you don't have specific data, say so — don't fabricate numbers.
Respond in 2-4 sentences maximum. Be direct and data-focused.`;

interface AskDataPanelProps {
  /** Optional KPI snapshot to provide as context to the LLM */
  kpiContext?: string;
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
      const { supabase } = await import("@/integrations/supabase/client");
      const { data: { session } } = await supabase.auth.getSession();

      const backendUrl = import.meta.env.VITE_BACKEND_URL || "";
      const contextBlock = kpiContext
        ? `Current platform metrics:\n${kpiContext}\n\n`
        : "";

      const res = await fetch(`${backendUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}),
        },
        body: JSON.stringify({
          messages: [
            {
              role: "system",
              content:
                "You are an AI analytics assistant for the AskMukthiGuru admin dashboard. " +
                "Answer questions about platform metrics, query volume, latency, costs, " +
                "hallucination rates and serene mind triggers. Be concise (2-4 sentences). " +
                "If data is unavailable say so — do not fabricate numbers.",
            },
            {
              role: "user",
              content: `${contextBlock}${question}`,
            },
          ],
          user_message: `${contextBlock}${question}`,
          meditation_step: 0,
        }),
      });

      if (!res.ok) {
        setError(`Backend returned ${res.status} — is Docker running?`);
        return;
      }
      const data = await res.json();
      const text = data.response || data.choices?.[0]?.message?.content || data.content;
      if (text) {
        setResult(text);
      } else {
        setError("Empty response from backend.");
      }
    } catch {
      setError("Connection failed — check that the backend is running.");
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
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
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
            Consulting Sarvam 30B…
          </div>
        )}

        {error && (
          <div className="text-xs text-destructive bg-destructive/10 rounded p-2">
            {error}
          </div>
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
