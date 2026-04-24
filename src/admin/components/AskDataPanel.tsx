import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sparkles, Search } from "lucide-react";
import { askData } from "@/admin/lib/mockData";

export function AskDataPanel() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ summary: string; rows: any[] } | null>(null);

  async function ask(question: string) {
    setLoading(true);
    const r = await askData(question);
    setResult(r);
    setLoading(false);
  }

  const examples = [
    "Hallucination rate by prompt version",
    "Slowest queries",
    "Serene Mind triggers by day",
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
            placeholder="e.g. hallucination rate by prompt"
          />
          <Button type="submit" size="icon" disabled={loading}>
            <Search className="h-4 w-4" />
          </Button>
        </form>
        <div className="flex flex-wrap gap-1.5">
          {examples.map((e) => (
            <Button
              key={e}
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => {
                setQ(e);
                ask(e);
              }}
            >
              {e}
            </Button>
          ))}
        </div>

        {result && (
          <div className="text-xs space-y-2">
            <div className="text-muted-foreground">{result.summary}</div>
            {result.rows.length > 0 && (
              <div className="border border-border rounded overflow-hidden">
                <table className="w-full">
                  <thead className="bg-muted text-muted-foreground">
                    <tr>
                      {Object.keys(result.rows[0]).map((k) => (
                        <th key={k} className="text-left px-2 py-1 font-medium">
                          {k}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((r, i) => (
                      <tr key={i} className="border-t border-border">
                        {Object.keys(result.rows[0]).map((k) => (
                          <td key={k} className="px-2 py-1 tabular-nums">
                            {String(r[k])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
