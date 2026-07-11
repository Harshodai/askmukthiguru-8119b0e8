import { useState, useEffect, useMemo } from "react";
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
import { Search, X, Info } from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface QueryItem {
  id: string;
  created_at: string;
  query_text: string;
  model?: string;
  prompt_version_id?: string;
  latency_ms?: number;
  status: string;
  spans?: any[];
}

export default function QueriesPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [promptVersionId, setPromptVersionId] = useState<string | undefined>(
    params.get("prompt") ?? undefined,
  );
  const [model, setModel] = useState<string | undefined>(params.get("model") ?? undefined);
  const [minScore, setMinScore] = useState(Number(params.get("min") ?? 0));
  const [openId, setOpenId] = useState<string | null>(params.get("trace"));
  const [sortField, setSortField] = useState<string>(params.get("sort") ?? "created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">((params.get("dir") as "asc" | "desc") ?? "desc");

  useEffect(() => {
    const next = new URLSearchParams();
    if (search) next.set("search", search);
    if (promptVersionId) next.set("prompt", promptVersionId);
    if (model) next.set("model", model);
    if (minScore) next.set("min", String(minScore));
    if (openId) next.set("trace", openId);
    next.set("sort", sortField);
    next.set("dir", sortDir);
    setParams(next, { replace: true });
  }, [search, promptVersionId, model, minScore, openId, sortField, sortDir, setParams]);


  const { data: prompts } = usePromptVersions();
  const { data: models } = useModels();
  const { data, isLoading } = useQueries({
    search,
    promptVersionId,
    model,
    minJudgeScore: minScore > 0 ? minScore : undefined,
    limit: 200,
  });

  const sortedData = useMemo(() => {
    if (!data) return [];
    return [...data].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "created_at":
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
        case "latency_ms":
          cmp = (a.latency_ms ?? 0) - (b.latency_ms ?? 0);
          break;
        case "query_text":
          cmp = a.query_text.localeCompare(b.query_text);
          break;
        case "model":
          cmp = (a.model ?? "unknown").localeCompare(b.model ?? "unknown");
          break;
        case "status":
          cmp = a.status.localeCompare(b.status);
          break;
        default:
          cmp = 0;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortField, sortDir]);

  const promptLabel = (id: string | null | undefined) => {
    if (!id) return "v0 (default)";
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
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Queries</h1>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button className="text-muted-foreground hover:text-foreground">
                  <Info className="h-4 w-4" />
                </button>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs p-2">
                Inspect all chat queries. Use the search input, prompt version select, model dropdown, and judge score slider to filter the traces. Click any row to view the full waterfall timeline of step durations, cost, and safety alerts.
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
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
                {models?.map((m) => {
                  interface ModelObject {
                    id?: string;
                    name?: string;
                    provider?: string;
                  }
                  const val = typeof m === 'string' ? m : (m as ModelObject).id ?? String(m);
                  const label = typeof m === 'string' ? m : `${(m as ModelObject).name ?? val} (${(m as ModelObject).provider ?? ''})`.trim();
                  return (
                    <SelectItem key={val} value={val}>
                      {label}
                    </SelectItem>
                  );
                })}
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

          <div className="md:col-span-12 flex items-center gap-2 pt-3 border-t mt-1">
            <label className="text-xs text-muted-foreground whitespace-nowrap">Sort by</label>
            <Select value={sortField} onValueChange={setSortField}>
              <SelectTrigger className="h-8 text-xs w-[140px]">
                <SelectValue placeholder="Sort field" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at">Time</SelectItem>
                <SelectItem value="query_text">Query</SelectItem>
                <SelectItem value="model">Model</SelectItem>
                <SelectItem value="latency_ms">Latency</SelectItem>
                <SelectItem value="status">Status</SelectItem>
              </SelectContent>
            </Select>
            <Select value={sortDir} onValueChange={(v) => setSortDir(v as "asc" | "desc")}>
              <SelectTrigger className="h-8 text-xs w-[130px]">
                <SelectValue placeholder="Direction" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">Ascending</SelectItem>
                <SelectItem value="desc">Descending</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading…</div>
          ) : !sortedData.length ? (
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
                {sortedData.map((q) => (
                  <TableRow
                    key={q.id}
                    className="cursor-pointer"
                    onClick={() => setOpenId(q.id)}
                  >
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {fmtDateTime(q.created_at)}
                    </TableCell>
                    <TableCell>{truncate(q.query_text, 60)}</TableCell>
                    <TableCell className="text-xs font-mono">{q.model?.split("/").pop() || "unknown"}</TableCell>
                    <TableCell className="text-xs">{promptLabel(q.prompt_version_id)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span className="tabular-nums text-xs font-mono">{fmtMs(q.latency_ms)}</span>
                        {q.spans && q.spans.length > 0 && (
                          <div className="flex h-1.5 w-24 rounded-full overflow-hidden bg-muted">
                            {q.spans.map((span: any) => {
                              const colors: Record<string, string> = {
                                guardrails_in: "bg-slate-400",
                                embed: "bg-sky-400",
                                vector_search: "bg-orange-400",
                                rerank: "bg-violet-500",
                                llm: "bg-emerald-500",
                                judge: "bg-amber-500",
                                guardrails_out: "bg-slate-400",
                              };
                              const pct = Math.max(2, (span.duration_ms / (q.latency_ms || 1)) * 100);
                              return (
                                <div
                                  key={span.id}
                                  className={colors[span.name] || "bg-gray-400"}
                                  style={{ width: `${pct}%` }}
                                  title={`${span.name}: ${span.duration_ms}ms`}
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
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
