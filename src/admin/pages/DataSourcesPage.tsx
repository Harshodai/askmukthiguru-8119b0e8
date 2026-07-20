import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useDataStores } from "@/admin/hooks/useAdminData";
import { Database, Share2, BrainCircuit, HardDrive, AlertCircle } from "lucide-react";
import { KpiCard } from "@/admin/components/KpiCard";
import { fmtInt } from "@/admin/lib/formatters";
import type { DataStoreError, QdrantCollectionInfo, Neo4jStats, LightRAGStats } from "@/admin/types";

function isError(v: unknown): v is DataStoreError {
  return typeof v === "object" && v !== null && "error" in v;
}

function CollectionCard({ name, info }: { name: string; info: QdrantCollectionInfo }) {
  return (
    <div className="border rounded-lg p-3 space-y-1.5 bg-muted/30">
      <div className="flex items-center justify-between gap-2">
        <code className="text-xs font-mono truncate text-foreground/80">{name}</code>
        <Badge variant={info.status === "green" ? "default" : "destructive"} className="shrink-0 text-[10px] h-5">
          {info.status}
        </Badge>
      </div>
      <div className="flex gap-3 text-xs text-muted-foreground">
        <span>{fmtInt(info.points)} points</span>
        {info.indexed_vectors > 0 && <span>{fmtInt(info.indexed_vectors)} indexed</span>}
        {info.vector_size && <span>{info.vector_size}d</span>}
      </div>
    </div>
  );
}

export default function DataSourcesPage() {
  const { data, isLoading, error } = useDataStores();

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
      <div className="p-4 text-destructive flex items-center gap-2">
        <AlertCircle className="h-4 w-4" />
        Failed to load data store info
      </div>
    );
  }

  const qdrantError = isError(data.qdrant) ? data.qdrant.error : null;
  const qdrantEntries = qdrantError ? [] : Object.entries(data.qdrant as Record<string, QdrantCollectionInfo>);
  const neo4jError = isError(data.neo4j) ? data.neo4j.error : null;
  const neo4j = (neo4jError ? {} : data.neo4j) as Neo4jStats & Partial<DataStoreError>;
  const lightragError = isError(data.lightrag) ? data.lightrag.error : null;
  const lightrag = (lightragError ? {} : data.lightrag) as LightRAGStats & Partial<DataStoreError>;

  return (
    <div className="p-4 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Data Sources</h1>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="Total Points (Qdrant)"
          value={qdrantError ? "—" : fmtInt(qdrantEntries.reduce((s, [, v]) => s + v.points, 0))}
          tone={qdrantError ? "warn" : "default"}
        />
        <KpiCard
          label="Graph Nodes (Neo4j)"
          value={neo4jError ? "—" : fmtInt(neo4j.total_nodes || 0)}
          tone={neo4jError ? "warn" : "default"}
        />
        <KpiCard
          label="Graph Relations (Neo4j)"
          value={neo4jError ? "—" : fmtInt(neo4j.total_relationships || 0)}
          tone={neo4jError ? "warn" : "default"}
        />
        <KpiCard
          label="LightRAG Status"
          value={lightragError ? "—" : (lightrag.initialized ? "Active" : "Inactive")}
          tone={lightragError ? "warn" : (lightrag.initialized ? "good" : "warn")}
        />
      </div>

      {/* Qdrant */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Database className="h-4 w-4" /> Qdrant Collections
          </CardTitle>
          <CardDescription>
            {qdrantError
              ? <span className="text-destructive">{qdrantError}</span>
              : `${qdrantEntries.length} collections, ${fmtInt(qdrantEntries.reduce((s, [, v]) => s + v.points, 0))} total points`}
          </CardDescription>
        </CardHeader>
        <CardContent>
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
                : `${neo4j.total_nodes || 0} total`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!neo4jError && neo4j.nodes_by_label && Object.keys(neo4j.nodes_by_label).length > 0 ? (
              <div className="space-y-1">
                {Object.entries(neo4j.nodes_by_label).map(([label, count]) => (
                  <div key={label} className="flex justify-between text-sm py-0.5">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-mono font-medium">{fmtInt(count as number)}</span>
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
                : `${neo4j.total_relationships || 0} total`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!neo4jError && neo4j.relationships_by_type && Object.keys(neo4j.relationships_by_type).length > 0 ? (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {Object.entries(neo4j.relationships_by_type).map(([type, count]) => (
                  <div key={type} className="flex justify-between text-sm py-0.5">
                    <span className="text-muted-foreground">{type}</span>
                    <span className="font-mono font-medium">{fmtInt(count as number)}</span>
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
              : lightrag.initialized ? "Initialized and ready" : "Not initialized"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!lightragError && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold">{lightrag.initialized ? "✓" : "✗"}</div>
                <div className="text-xs text-muted-foreground mt-1">Initialized</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag.chunk_token_size || "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Chunk Token Size</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag.cache_size ?? "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Cached Queries</div>
              </div>
              <div className="border rounded-lg p-3 text-center">
                <div className="text-2xl font-bold font-mono">{lightrag.embedding_dim ?? "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Embed Dim</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
