import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Loader2, RefreshCw, FileText, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { listOkfEntries, compileOkfIndex, type OkfEntry } from "@/admin/lib/api";

const TYPES = ["teaching", "practice", "glossary", "qa", "reflection"];

export default function OkfManagerPage() {
  const [entries, setEntries] = useState<OkfEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [compiling, setCompiling] = useState(false);
  const [typeFilter, setTypeFilter] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const res = await listOkfEntries(typeFilter || undefined);
      setEntries(res.entries);
      setTotal(res.total);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load OKF entries");
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  async function compile() {
    setCompiling(true);
    try {
      const res = await compileOkfIndex();
      toast.success(`OKF compiled → ${res.path}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Compile failed");
    } finally {
      setCompiling(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BookOpen className="w-6 h-6" /> OKF Knowledge Manager
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Open Knowledge Format entries — markdown + YAML frontmatter, compiled to an embedded index.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />}
            Refresh
          </Button>
          <Button onClick={compile} disabled={compiling} className="bg-ojas hover:bg-ojas/90">
            {compiling ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <FileText className="w-4 h-4 mr-1" />}
            Compile Index
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Entries ({total})</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="text-sm border rounded px-2 py-1 bg-background"
            >
              <option value="">All types</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {entries.length === 0 && !loading ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No entries loaded. Click Refresh.
            </p>
          ) : (
            <div className="space-y-3">
              {entries.map((e) => (
                <div key={e.title} className="border rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant="secondary">{e.type}</Badge>
                    <span className="font-medium">{e.title}</span>
                  </div>
                  {e.source && <p className="text-xs text-muted-foreground">{e.source}</p>}
                  {e.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {e.tags.map((t) => (
                        <span key={t} className="text-[10px] px-1.5 py-0.5 bg-muted rounded">{t}</span>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{e.body_preview}</p>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}