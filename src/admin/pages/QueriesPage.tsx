import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { useQueries, usePromptVersions, useModels } from "@/admin/hooks/useAdminData";
import { fmtDateTime, fmtMs, truncate } from "@/admin/lib/formatters";
import { TraceDrawer } from "@/admin/components/TraceDrawer";
import { EmptyState } from "@/admin/components/EmptyState";
import { Search, X } from "lucide-react";

export default function QueriesPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [promptVersionId, setPromptVersionId] = useState<string | undefined>(
    params.get("prompt") ?? undefined,
  );
  const [model, setModel] = useState<string | undefined>(params.get("model") ?? undefined);
  const [minScore, setMinScore] = useState(Number(params.get("min") ?? 0));
  const [openId, setOpenId] = useState<string | null>(params.get("trace"));

  useEffect(() => {
    const next = new URLSearchParams();
    if (search) next.set("search", search);
    if (promptVersionId) next.set("prompt", promptVersionId);
    if (model) next.set("model", model);
    if (minScore) next.set("min", String(minScore));
    if (openId) next.set("trace", openId);
    setParams(next, { replace: true });
  }, [search, promptVersionId, model, minScore, openId, setParams]);


  const { data: prompts } = usePromptVersions();
  const { data: models } = useModels();
  const { data, isLoading } = useQueries({
    search,
    promptVersionId,
    model,
    minJudgeScore: minScore > 0 ? minScore : undefined,
    limit: 200,
  });

  const promptLabel = (id: string) => {
    const p = prompts?.find((p) => p.id === id);
    return p ? `${p.name} v${p.version}` : id.slice(0, 8);
  };

  const clearFilters = () => {
    setSearch("");
    setPromptVersionId(undefined);
    setModel(undefined);
    setMinScore(0);
  };

  const hasFilters = !!search || !!promptVersionId || !!model || minScore > 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Queries</h1>
        <p className="text-sm text-muted-foreground">
          Inspect every chat query, its retrieval, judge scores, and full trace.
        </p>
      </div>

      {/* Filter bar */}
      <Card>
        <CardContent className="p-4 grid md:grid-cols-12 gap-3 items-end">
          <div className="md:col-span-4">
            <label className="text-xs text-muted-foreground">Search query text</label>
            <div className="relative mt-1">
              <Search className="h-4 w-4 absolute left-2 top-2.5 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8"
                placeholder="anxious, beautiful state, …"
              />
            </div>
          </div>

          <div className="md:col-span-3">
            <label className="text-xs text-muted-foreground">Prompt version</label>
            <Select
              value={promptVersionId ?? "__all__"}
              onValueChange={(v) => setPromptVersionId(v === "__all__" ? undefined : v)}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="All prompts" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All prompts</SelectItem>
                {prompts?.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name} v{p.version} {p.active && "·active"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2">
            <label className="text-xs text-muted-foreground">Model</label>
            <Select
              value={model ?? "__all__"}
              onValueChange={(v) => setModel(v === "__all__" ? undefined : v)}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="All models" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All models</SelectItem>
                {models?.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="md:col-span-2">
            <label className="text-xs text-muted-foreground">
              Min judge score: <span className="tabular-nums">{minScore.toFixed(2)}</span>
            </label>
            <Slider
              value={[minScore]}
              min={0}
              max={1}
              step={0.05}
              onValueChange={(v) => setMinScore(v[0])}
              className="mt-3"
            />
          </div>

          <div className="md:col-span-1 flex justify-end">
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="h-4 w-4" /> Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading…</div>
          ) : !data?.length ? (
            <EmptyState title="No queries match your filters" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Query</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Prompt</TableHead>
                  <TableHead className="text-right">Latency</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((q) => (
                  <TableRow
                    key={q.id}
                    className="cursor-pointer"
                    onClick={() => setOpenId(q.id)}
                  >
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {fmtDateTime(q.created_at)}
                    </TableCell>
                    <TableCell>{truncate(q.query_text, 60)}</TableCell>
                    <TableCell className="text-xs font-mono">{q.model.split("/").pop()}</TableCell>
                    <TableCell className="text-xs">{promptLabel(q.prompt_version_id)}</TableCell>
                    <TableCell className="text-right tabular-nums text-xs">
                      {fmtMs(q.latency_ms)}
                    </TableCell>
                    <TableCell>
                      {q.status === "ok" ? (
                        <Badge variant="secondary">ok</Badge>
                      ) : q.status === "error" ? (
                        <Badge variant="destructive">error</Badge>
                      ) : (
                        <Badge>blocked</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <TraceDrawer queryId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
