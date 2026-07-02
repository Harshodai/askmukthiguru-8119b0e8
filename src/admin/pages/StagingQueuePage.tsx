import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { listStagingQueue, reviewStagingItem } from "@/admin/lib/api";
import { fmtDateTime } from "@/admin/lib/formatters";
import { toast } from "sonner";
import { ClipboardCheck, Loader2, Check, X, AlertTriangle, HelpCircle } from "lucide-react";

export default function StagingQueuePage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
  const [notes, setNotes] = useState("");
  const [actionType, setActionType] = useState<"approve" | "reject" | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadStaging();
  }, [statusFilter]);

  async function loadStaging() {
    setLoading(true);
    try {
      const data = await listStagingQueue(statusFilter);
      setItems(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load staging queue");
    } finally {
      setLoading(false);
    }
  }

  async function handleReviewSubmit() {
    if (!selectedItem || !actionType) return;
    setSubmitting(true);
    try {
      const res = await reviewStagingItem(selectedItem.id, actionType, notes);
      toast.success(res.message || `Content successfully ${actionType}d`);
      setSelectedItem(null);
      setNotes("");
      setActionType(null);
      loadStaging();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Action failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardCheck className="w-6 h-6 text-primary" /> Data Quality Staging Queue
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Iceberg-style quality staging. Content that falls below the quality threshold ({65}) is held here for manual review.
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="text-sm border rounded px-3 py-1.5 bg-background shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
          >
            <option value="pending">Pending Review</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
          <Button variant="outline" onClick={loadStaging} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Refresh"}
          </Button>
        </div>
      </div>

      <Card className="border-primary/20 bg-card">
        <CardHeader>
          <CardTitle>Staged Submissions ({items.length})</CardTitle>
          <CardDescription>
            Review the deterministic or LLM quality score and reason before manually merging into the knowledge base.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 space-y-2">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">Loading staging queue items...</p>
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-sm text-muted-foreground flex flex-col items-center justify-center gap-2">
              <HelpCircle className="w-8 h-8 text-muted-foreground/50" />
              No items in the staging queue matching status "{statusFilter}".
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Staged Time</TableHead>
                    <TableHead>Source / URL</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Fail Reasons</TableHead>
                    <TableHead>Preview</TableHead>
                    {statusFilter === "pending" && <TableHead className="text-right">Actions</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id} className="hover:bg-muted/30">
                      <TableCell className="text-xs whitespace-nowrap">{fmtDateTime(item.created_at)}</TableCell>
                      <TableCell className="text-xs font-mono max-w-[200px] truncate" title={item.source_url}>
                        {item.source_url}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            item.quality_score >= 50
                              ? "border-yellow-500 text-yellow-500 bg-yellow-500/5 font-mono"
                              : "border-red-500 text-red-500 bg-red-500/5 font-mono"
                          }
                        >
                          {item.quality_score}/100
                        </Badge>
                      </TableCell>
                      <TableCell className="max-w-[250px]">
                        <div className="flex flex-wrap gap-1">
                          {item.fail_reasons?.map((reason: string, idx: number) => (
                            <Badge key={idx} variant="secondary" className="text-[10px] py-0 px-1.5 font-normal">
                              {reason}
                            </Badge>
                          )) || <span className="text-xs text-muted-foreground">None</span>}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[300px] truncate" title={item.content_preview}>
                        {item.content_preview}
                      </TableCell>
                      {statusFilter === "pending" && (
                        <TableCell className="text-right whitespace-nowrap">
                          <div className="flex justify-end gap-1.5">
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-green-600 hover:text-green-700 hover:bg-green-500/10 h-8 px-2"
                              onClick={() => {
                                setSelectedItem(item);
                                setActionType("approve");
                                setNotes("");
                              }}
                            >
                              <Check className="w-3.5 h-3.5 mr-1" /> Approve
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-red-600 hover:text-red-700 hover:bg-red-500/10 h-8 px-2"
                              onClick={() => {
                                setSelectedItem(item);
                                setActionType("reject");
                                setNotes("");
                              }}
                            >
                              <X className="w-3.5 h-3.5 mr-1" /> Reject
                            </Button>
                          </div>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Review Dialog */}
      <Dialog open={selectedItem !== null} onOpenChange={(open) => !open && setSelectedItem(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className={actionType === "approve" ? "text-green-500" : "text-red-500"} />
              {actionType === "approve" ? "Approve Staged Content" : "Reject Staged Content"}
            </DialogTitle>
            <DialogDescription>
              {actionType === "approve"
                ? "Approving will bypass the quality gate and force-ingest this source content into Qdrant, Neo4j, and LightRAG."
                : "Rejecting will permanently flag this content and ignore it."}
            </DialogDescription>
          </DialogHeader>

          {selectedItem && (
            <div className="space-y-4 my-2">
              <div className="p-3 bg-muted rounded-lg text-xs space-y-1">
                <p><strong>Source:</strong> {selectedItem.source_url}</p>
                <p><strong>Quality Score:</strong> {selectedItem.quality_score}/100</p>
                <p><strong>Reasons:</strong> {selectedItem.fail_reasons?.join("; ")}</p>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-muted-foreground">Reviewer Notes (Optional)</label>
                <Textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Provide comments or notes on this decision..."
                  className="min-h-[80px]"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedItem(null)} disabled={submitting}>
              Cancel
            </Button>
            <Button
              variant={actionType === "approve" ? "default" : "destructive"}
              className={actionType === "approve" ? "bg-green-600 hover:bg-green-700" : ""}
              onClick={handleReviewSubmit}
              disabled={submitting}
            >
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Confirm {actionType === "approve" ? "Approval" : "Rejection"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
