import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { upsertGoldenQuestion } from "@/admin/lib/mockData";
import type { GoldenQuestion } from "@/admin/types";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onClose: () => void;
  initial?: GoldenQuestion | null;
}

const empty: GoldenQuestion = {
  id: "",
  question: "",
  expected_answer: "",
  expected_sources: [],
  tags: [],
  active: true,
};

export function GoldenQuestionDialog({ open, onClose, initial }: Props) {
  const [q, setQ] = useState<GoldenQuestion>(initial ?? empty);
  const [tagsStr, setTagsStr] = useState((initial?.tags ?? []).join(", "));
  const [sourcesStr, setSourcesStr] = useState((initial?.expected_sources ?? []).join(", "));
  const qc = useQueryClient();

  useEffect(() => {
    setQ(initial ?? empty);
    setTagsStr((initial?.tags ?? []).join(", "));
    setSourcesStr((initial?.expected_sources ?? []).join(", "));
  }, [initial, open]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Edit golden question" : "New golden question"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Question</Label>
            <Input value={q.question} onChange={(e) => setQ({ ...q, question: e.target.value })} />
          </div>
          <div>
            <Label className="text-xs">Expected answer</Label>
            <Textarea
              rows={4}
              value={q.expected_answer}
              onChange={(e) => setQ({ ...q, expected_answer: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Tags (comma)</Label>
              <Input value={tagsStr} onChange={(e) => setTagsStr(e.target.value)} />
            </div>
            <div>
              <Label className="text-xs">Expected sources (comma)</Label>
              <Input value={sourcesStr} onChange={(e) => setSourcesStr(e.target.value)} />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={q.active} onCheckedChange={(v) => setQ({ ...q, active: v })} />
            <Label className="text-xs">Active in eval runs</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button
            onClick={async () => {
              if (!q.question.trim()) { toast.error("Question is required"); return; }
              const finalQ: GoldenQuestion = {
                ...q,
                id: q.id || `gq_${Date.now()}`,
                tags: tagsStr.split(",").map((t) => t.trim()).filter(Boolean),
                expected_sources: sourcesStr.split(",").map((s) => s.trim()).filter(Boolean),
              };
              await upsertGoldenQuestion(finalQ);
              qc.invalidateQueries({ queryKey: ["admin", "golden"] });
              toast.success("Saved");
              onClose();
            }}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
