import { useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link } from "react-router-dom";
import { BookOpen, Plus, Trash2, X, Loader2, ChevronDown, ChevronUp, Bookmark, Hash } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useStudyNotebooks, type NotebookItem } from "@/hooks/useStudyNotebooks";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import { useTranslation } from 'react-i18next';

export default function StudyNotebookPage() {
  const { notebooks, loading, error, createNotebook, deleteNotebook, addItem, listItems } = useStudyNotebooks();
  const { toast } = useToast();
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [itemsMap, setItemsMap] = useState<Record<string, NotebookItem[]>>({});
  const [loadingItems, setLoadingItems] = useState<Record<string, boolean>>({});
  const createRef = useRef<HTMLInputElement>(null);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    const nb = await createNotebook(newTitle.trim());
    if (nb) {
      setNewTitle("");
      setShowCreate(false);
      toast({ title: "Notebook created", description: nb.title });
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await deleteNotebook(id);
    if (ok) toast({ title: "Notebook deleted" });
  };

  const toggleExpand = async (id: string) => {
    if (expanded === id) {
      setExpanded(null);
      return;
    }
    setExpanded(id);
    if (!itemsMap[id]) {
      setLoadingItems((p) => ({ ...p, [id]: true }));
      const items = await listItems(id);
      setItemsMap((p) => ({ ...p, [id]: items }));
      setLoadingItems((p) => ({ ...p, [id]: false }));
    }
  };

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <BookOpen className="w-6 h-6 text-ojas" />
              Study Notebooks
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Save and organize your favorite teachings for deeper study
            </p>
          </div>
          <Button onClick={() => { setShowCreate(true); setTimeout(() => createRef.current?.focus(), 50); }} className="bg-ojas hover:bg-ojas/90">
            <Plus className="w-4 h-4 mr-1" /> New Notebook
          </Button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>
        )}

        {loading && notebooks.length === 0 && (
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            <Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading notebooks...
          </div>
        )}

        {!loading && notebooks.length === 0 && !error && (
          <div className="text-center py-16 text-muted-foreground">
            <BookOpen className="w-12 h-12 mx-auto mb-4 text-muted-foreground/40" />
            <p className="text-lg font-medium">No notebooks yet</p>
            <p className="text-sm mt-1">Create your first study notebook to save teachings</p>
          </div>
        )}

        <div className="space-y-4">
          {notebooks.map((nb) => (
            <motion.div
              key={nb.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
            >
              <Card
                className={cn(
                  "p-5 transition-all cursor-pointer",
                  expanded === nb.id ? "ring-2 ring-ojas/30" : "hover:shadow-md hover:-translate-y-0.5"
                )}
                onClick={() => toggleExpand(nb.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-ojas" />
                      <h3 className="font-semibold text-foreground truncate">{nb.title}</h3>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Created {new Date(nb.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDelete(nb.id); }}
                      className="p-1.5 rounded-full hover:bg-red-50 text-muted-foreground hover:text-red-600 transition-colors"
                      title="Delete notebook"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    {expanded === nb.id ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                  </div>
                </div>

                <AnimatePresence>
                  {expanded === nb.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25 }}
                      className="overflow-hidden"
                    >
                      <div className="pt-4 border-t mt-4">
                        {loadingItems[nb.id] ? (
                          <div className="flex items-center justify-center py-8 text-muted-foreground">
                            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading items...
                          </div>
                        ) : (itemsMap[nb.id]?.length ?? 0) === 0 ? (
                          <div className="text-center py-8 text-muted-foreground">
                            <Bookmark className="w-8 h-8 mx-auto mb-2 text-muted-foreground/30" />
                            <p className="text-sm">No items saved yet</p>
                            <p className="text-xs mt-1">Save teachings from chat messages to this notebook</p>
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {(itemsMap[nb.id] ?? []).map((item) => (
                              <Card key={item.id} className="p-3 bg-muted/30">
                                <div className="flex items-start gap-2">
                                  <Hash className="w-3.5 h-3.5 text-ojas mt-1 shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <p className="font-medium text-sm text-foreground line-clamp-2">{item.query}</p>
                                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{item.answer}</p>
                                    {item.citations?.length > 0 && (
                                      <p className="text-[10px] text-ojas mt-1">{item.citations.length} source(s)</p>
                                    )}
                                  </div>
                                </div>
                              </Card>
                            ))}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </Card>
            </motion.div>
          ))}
        </div>

        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create New Notebook</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-2">
              <Input
                ref={createRef}
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g., Morning Meditations"
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
                <Button onClick={handleCreate} disabled={!newTitle.trim()} className="bg-ojas hover:bg-ojas/90">
                  Create
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </AppShell>
  );
}
