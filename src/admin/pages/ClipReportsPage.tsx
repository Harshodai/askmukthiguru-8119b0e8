import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Flag, ShieldAlert, Cpu, MoreHorizontal, ExternalLink } from "lucide-react";
import { useClipReports } from "@/admin/hooks/useAdminData";
import { AdminPageError } from "@/admin/components/AdminPageStates";
import { EmptyState } from "@/admin/components/EmptyState";
import { CorpusProvenanceModal } from "@/admin/components/CorpusProvenanceModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { fmtDateTime, truncate } from "@/admin/lib/formatters";

const PAGE_SIZE = 20;

/**
 * Decode the single level of HTML entities the API applies to free-text
 * fields (question/reason/reporter). The decoded string is rendered ONLY
 * through JSX text interpolation, so React re-escapes it on render —
 * decoding fixes display (no "&lt;" artifacts) without opening stored-XSS.
 * `&amp;` decodes last so a literal "&lt;" typed by a reporter survives
 * as visible text instead of becoming markup.
 */
function decodeEntities(s: string): string {
  return s
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function isDenied(error: unknown): boolean {
  const msg = error instanceof Error ? error.message : String(error ?? "");
  return /admin access required|session expired|not allowlisted|401|403/i.test(msg);
}

export default function ClipReportsPage() {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useClipReports(
    PAGE_SIZE,
    page * PAGE_SIZE,
  );

  const rows = Array.isArray(data) ? data : [];
  // The GET endpoint returns a bare array (no total count), so the only
  // fullness signal is a full page — a short page means the end.
  const hasMore = rows.length === PAGE_SIZE;

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{t("admin.clipReports")}</h1>
          {isFetching && !isLoading && (
            <span className="text-xs text-muted-foreground">…</span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          {t("admin.clipReportsSubtitle")}
        </p>
        <div className="mt-2 flex items-start gap-2 rounded-xl border border-border bg-card p-3 text-xs text-muted-foreground">
          <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
          <span>{t("admin.clipReportsPiiNotice")}</span>
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3" aria-busy="true" aria-label={t("admin.loading")}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex gap-3">
                  <Skeleton className="h-4 w-24 shrink-0" />
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-4 w-32 shrink-0" />
                </div>
              ))}
            </div>
          ) : isError && isDenied(error) ? (
            <div className="p-6 text-center space-y-3">
              <ShieldAlert className="h-8 w-8 mx-auto text-muted-foreground opacity-60" />
              <p className="text-sm font-medium">{t("admin.unauthorized")}</p>
              <p className="text-xs text-muted-foreground">
                {error instanceof Error ? error.message : String(error ?? "")}
              </p>
              <Button variant="outline" size="sm" asChild>
                <a href="/admin/login">{t("admin.login")}</a>
              </Button>
            </div>
          ) : isError ? (
            <div className="p-4">
              <AdminPageError
                message={error instanceof Error ? error.message : String(error ?? "")}
                onRetry={() => refetch()}
              />
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              title={t("admin.clipReportsEmpty")}
              hint={t("admin.clipReportsEmptyHint")}
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[640px]">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left px-4 py-3 font-medium w-10">
                        <span className="sr-only">{t("admin.clipReportsReport")}</span>
                        <Flag className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                      </th>
                      <th className="text-left px-4 py-3 font-medium">{t("admin.clipReportsQuestion")}</th>
                      <th className="text-left px-4 py-3 font-medium">{t("admin.clipReportsReason")}</th>
                      <th className="text-left px-4 py-3 font-medium w-40">{t("admin.clipReportsClip")}</th>
                      <th className="text-left px-4 py-3 font-medium w-32">{t("admin.clipReportsReporter")}</th>
                      <th className="text-left px-4 py-3 font-medium w-44">{t("admin.clipReportsTime")}</th>
                      <th className="text-right px-4 py-3 font-medium w-48">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {rows.map((r, index) => {
                      const videoId = (r as any)?.video_id || r?.served_point_id || "";
                      return (
                        <tr
                          key={`${r?.served_point_id ?? "report"}-${r?.ts ?? index}`}
                          className="hover:bg-muted/30 transition-colors align-top"
                        >
                          <td className="px-4 py-3">
                            <Flag className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                          </td>
                          {/* Free text renders via JSX interpolation only (React-escaped). */}
                          <td className="px-4 py-3 max-w-[220px]">
                            <span className="block truncate" title={decodeEntities(r?.question ?? "")}>
                              {decodeEntities(r?.question ?? "") || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 max-w-[220px]">
                            <span className="block truncate" title={decodeEntities(r?.reason ?? "")}>
                              {decodeEntities(r?.reason ?? "") || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                            {r?.served_point_id ? (
                              <button
                                type="button"
                                onClick={() => setSelectedPointId(r.served_point_id)}
                                className="inline-flex items-center gap-1 font-mono text-xs text-primary hover:underline hover:text-primary/80 transition-colors"
                                title={`Inspect provenance for ${r.served_point_id}`}
                              >
                                <Cpu className="h-3 w-3 shrink-0" />
                                <span className="truncate max-w-[140px]">{truncate(r.served_point_id, 18)}</span>
                              </button>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground">
                            <span className="block truncate" title={decodeEntities(r?.reporter ?? "")}>
                              {decodeEntities(r?.reporter ?? "") || "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                            {r?.ts ? fmtDateTime(r.ts) : "—"}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex items-center justify-end gap-1">
                              <Button variant="ghost" size="sm" asChild className="h-7 text-xs px-2">
                                <Link
                                  to={`/admin/ingestion?tab=attribution&videoId=${encodeURIComponent(videoId)}`}
                                  title="Inspect in Speaker Attribution"
                                >
                                  Attribution
                                </Link>
                              </Button>
                              <Button variant="ghost" size="sm" asChild className="h-7 text-xs px-2">
                                <Link
                                  to={`/admin/ingestion?tab=video-approval&videoId=${encodeURIComponent(videoId)}`}
                                  title="Inspect in Video Approval"
                                >
                                  Approval
                                </Link>
                              </Button>
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button variant="ghost" size="icon" className="h-7 w-7">
                                    <MoreHorizontal className="h-3.5 w-3.5" />
                                    <span className="sr-only">Actions</span>
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuItem asChild>
                                    <Link to={`/admin/ingestion?tab=attribution&videoId=${encodeURIComponent(videoId)}`}>
                                      Inspect in Speaker Attribution
                                    </Link>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem asChild>
                                    <Link to={`/admin/ingestion?tab=video-approval&videoId=${encodeURIComponent(videoId)}`}>
                                      Inspect in Video Approval
                                    </Link>
                                  </DropdownMenuItem>
                                  {r?.served_point_id && (
                                    <DropdownMenuItem onClick={() => setSelectedPointId(r.served_point_id)}>
                                      Inspect Provenance
                                    </DropdownMenuItem>
                                  )}
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-border">
                <span className="text-xs text-muted-foreground">
                  {t("admin.clipReportsPage", { page: page + 1 })}
                  {hasMore ? "" : ` · ${t("admin.clipReportsEnd")}`}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page === 0 || isFetching}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                  >
                    {t("admin.previous")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!hasMore || isFetching}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    {t("admin.next")}
                  </Button>
                </div>
              </div>
              <div className="px-4 pb-2">
                <Badge variant="outline" className="text-xs">
                  {t("admin.clipReportsQuarantineHint")}
                </Badge>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Corpus Point Provenance Drawer */}
      {selectedPointId && (
        <CorpusProvenanceModal
          pointId={selectedPointId}
          onClose={() => setSelectedPointId(null)}
        />
      )}
    </div>
  );
}
