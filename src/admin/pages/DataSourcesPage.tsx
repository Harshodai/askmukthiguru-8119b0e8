import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDataStores, useQdrantHealth } from "@/admin/hooks/useAdminData";
import { optimizeQdrant } from "@/admin/lib/api";
import { Database, Share2, BrainCircuit, HardDrive, AlertCircle, RefreshCw } from "lucide-react";
import { KpiCard } from "@/admin/components/KpiCard";
import { fmtInt } from "@/admin/lib/formatters";
import { toast } from "sonner";
import type { DataStoreError, QdrantCollectionInfo, Neo4jStats, LightRAGStats } from "@/admin/types";

function isError(v: unknown): v is DataStoreError {
  return typeof v === "object" && v !== null && "error" in v;
}

function CollectionCard({ name, info }: { name: string; info?: QdrantCollectionInfo | null }) {
  const status = info?.status ?? "unknown";
  const points = info?.points ?? 0;
  const indexed = info?.indexed_vectors ?? 0;
  const vectorSize = info?.vector_size;

  return (
    <div className="border rounded-lg p-3 space-y-1.5 bg-muted/30">
      <div className="flex items-center justify-between gap-2">
        <code className="text-xs font-mono truncate text-foreground/80">{name || "unnamed"}</code>
        <Badge variant={status === "green" ? "default" : "destructive"} className="shrink-0 text-[10px] h-5">
          {status}
        </Badge>
      </div>
      <div className="flex gap-3 text-xs text-muted-foreground">
        <span>{fmtInt(points)} points</span>
        {indexed > 0 && <span>{fmtInt(indexed)} indexed</span>}
        {vectorSize ? <span>{vectorSize}d</span> : null}
      </div>
    </div>
  );
}

export default function DataSourcesPage() {
  const { data, isLoading, error, refetch } = useDataStores();
  const { data: qdrantHealth, refetch: refetchHealth } = useQdrantHealth();
  const [optimizing, setOptimizing] = useState(false);

  const handleOptimize = async () => {
    setOptimizing(true);
    try {
      const res = await optimizeQdrant();
      toast.success(
        `Optimization completed: ${res?.actions?.join(", ") || "Segments compacted"}`
      );
      await Promise.all([refetch(), refetchHealth()]);
    } catch (err) {
      toast.error(`Optimization failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setOptimizing(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-32" />)}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>
        <Card className="border-destructive/30">
          <CardContent className="flex flex-col items-center justify-center py-12 gap-3 text-center">
            <div className="flex items-center gap-2 text-destructive font-medium">
              <AlertCircle className="h-5 w-5" />
              Failed to load data store information
            </div>
            <p className="text-xs text-muted-foreground max-w-md">
              Unable to connect to vector and graph databases. Ensure Qdrant and Neo4j services are operational.
            </p>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  const qdrantError = isError(data?.qdrant) ? (data.qdrant as DataStoreError).error : null;
  const qdrantEntries = qdrantError || !data?.qdrant || typeof data.qdrant !== "object"
    ? []
    : Object.entries(data.qdrant as Record<string, QdrantCollectionInfo>);
  const neo4jError = isError(data?.neo4j) ? (data.neo4j as DataStoreError).error : null;
  const neo4j = (neo4jError || !data?.neo4j || typeof data.neo4j !== "object" ? {} : data.neo4j) as Neo4jStats & Partial<DataStoreError>;
  const lightragError = isError(data?.lightrag) ? (data.lightrag as DataStoreError).error : null;
  const lightrag = (lightragError || !data?.lightrag || typeof data.lightrag !== "object" ? {} : data.lightrag) as LightRAGStats & Partial<DataStoreError>;

  const totalQdrantPoints = qdrantEntries.reduce((s, [, v]) => s + (v?.points ?? 0), 0);

  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="Total Points (Qdrant)"
          value={qdrantError ? "—" : fmtInt(totalQdrantPoints)}
          tone={qdrantError ? "warn" : "default"}
        />
        <KpiCard
          label="Graph Nodes (Neo4j)"
          value={neo4jError ? "—" : fmtInt(neo4j?.total_nodes || 0)}
          tone={neo4jError ? "warn" : "default"}
        />
        <KpiCard
          label="Graph Relations (Neo4j)"
          value={neo4jError ? "—" : fmtInt(neo4j?.total_relationships || 0)}
          tone={neo4jError ? "warn" : "default"}
        />
        <KpiCard
          label="LightRAG Status"
          value={lightragError ? "—" : (lightrag?.initialized ? "Active" : "Inactive")}
          tone={lightragError ? "warn" : (lightrag?.initialized ? "good" : "warn")}
        />
      </div>

      {/* Qdrant */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Database className="h-4 w-4" /> Qdrant Vector Index & Segments
              </CardTitle>
              <CardDescription>
                {qdrantError
                  ? <span className="text-destructive">{qdrantError}</span>
                  : `${qdrantEntries.length} collections, ${fmtInt(totalQdrantPoints)} total points`}
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={optimizing}
              onClick={handleOptimize}
              className="gap-1.5 self-start sm:self-auto shrink-0"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${optimizing ? "animate-spin" : ""}`} />
              {optimizing ? "Optimizing…" : "Optimize Vector Index"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Health & Segments Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 rounded-lg border bg-muted/20 text-xs">
            <div>
              <span className="text-muted-foreground block mb-0.5">Health Status</span>
              <div className="flex items-center gap-1.5 font-medium">
                <span className={`inline-block h-2 w-2 rounded-full ${
                  qdrantHealth?.status === "green" ? "bg-emerald-500" :
                  qdrantHealth?.status === "yellow" ? "bg-amber-500" :
                  qdrantHealth?.status === "red" ? "bg-rose-500" : "bg-muted-foreground"
                }`} />
                <span className="capitalize">{qdrantHealth?.status ?? "unknown"}</span>
              </div>
            </div>
            <div>
              <span className="text-muted-foreground block mb-0.5">Segment Count</span>
              <span className="font-mono font-medium text-foreground">
                {qdrantHealth?.segments_count != null ? fmtInt(qdrantHealth.segments_count) : "—"}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground block mb-0.5">Fragmentation</span>
              <span className="font-mono font-medium text-foreground">
                {qdrantHealth?.fragmentation_pct != null ? `${qdrantHealth.fragmentation_pct}%` : "—"}
              </span>
            </div>
            <div>
              <span className="text-muted-foreground block mb-0.5">Optimizer Status</span>
              <span className="font-mono font-medium text-foreground truncate block" title={qdrantHealth?.optimizer_status}>
                {qdrantHealth?.optimizer_status ?? "idle"}
              </span>
            </div>
          </div>

          {qdrantEntries.length === 0 && !qdrantError && (
            <p className="text-sm text-muted-foreground">No collections found.</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {qdrantEntries.map(([name, info]) => (
              <CollectionCard key={name} name={name} info={info} />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Neo4j */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <BrainCircuit className="h-4 w-4" /> Neo4j — Nodes
            </CardTitle>
            <CardDescription>
              {neo4jError
                ? <span className="text-destructive">{neo4jError}</span>
                : `${neo4j?.total_nodes || 0} total`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!neo4jError && typeof neo4j?.nodes_by_label === "object" && neo4j.nodes_by_label !== null && Object.keys(neo4j.nodes_by_label).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(neo4j.nodes_by_label).map(([label, count]) => (
                  <div key={label} className="flex justify-between text-sm py-0.5">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-mono font-medium">{fmtInt(typeof count === 'number' ? count : Number(count) || 0)}</span>
                  </div>
                ))}
              </div>
            ) : (!neo4jError && <p className="text-sm text-muted-foreground">No nodes found.</p>)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Share2 className="h-4 w-4" /> Neo4j — Relationships
            </CardTitle>
            <CardDescription>
              {neo4jError
                ? <span className="text-destructive">{neo4jError}</span>
                : `${neo4j?.total_relationships || 0} total`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!neo4jError && typeof neo4j?.relationships_by_type === "object" && neo4j.relationships_by_type !== null && Object.keys(neo4j.relationships_by_type).length > 0 ? (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {Object.entries(neo4j.relationships_by_type).map(([type, count]) => (
                  <div key={type} className="flex justify-between text-sm py-0.5">
                    <span className="text-muted-foreground">{type}</span>
                    <span className="font-mono font-medium">{fmtInt(typeof count === 'number' ? count : Number(count) || 0)}</span>
                  </div>
                ))}
              </div>
            ) : (!neo4jError && <p className="text-sm text-muted-foreground">No relationships found.</p>)}
          </CardContent>
        </Card>
      </div>

      {/* LightRAG */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <HardDrive className="h-4 w-4" /> LightRAG
          </CardTitle>
          <CardDescription>
            {lightragError
              ? <span className="text-destructive">{lightragError}</span>
              : lightrag?.initialized ? "Initialized and ready" : "Not initialized"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!lightragError && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold">{lightrag?.initialized ? "✓" : "✗"}</div>
                <div className="text-xs text-muted-foreground mt-1">Initialized</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag?.chunk_token_size || "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Chunk Token Size</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag?.cache_size ?? "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Cached Queries</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag?.embedding_dim ?? "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Embed Dim</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
