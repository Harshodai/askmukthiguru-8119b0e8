import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bookmark,
  BookmarkCheck,
  Download,
  Plus,
  Search,
  Trash2,
  X,
  StickyNote,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useNotes, type Note } from "@/hooks/useNotes";
import { toast } from "@/hooks/use-toast";

function downloadMarkdown(notes: Note[]) {
  const body = notes
    .map(
      (n) =>
        `# ${n.title}\n\n_${new Date(n.created_at).toLocaleString()}_${n.tags.length ? `\n\nTags: ${n.tags.map((t) => `#${t}`).join(" ")}` : ""}\n\n${n.body}\n`,
    )
    .join("\n\n---\n\n");
  const blob = new Blob([body], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `askmukthiguru-notes-${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

export function NotesPanel() {
  const { notes, loading, createNote, updateNote, deleteNote } = useNotes();
  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [editing, setEditing] = useState<Note | null>(null);
  const [composing, setComposing] = useState(false);

  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");

  const allTags = useMemo(() => {
    const s = new Set<string>();
    notes.forEach((n) => n.tags.forEach((t) => s.add(t)));
    return Array.from(s).sort();
  }, [notes]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return notes.filter((n) => {
      if (activeTag && !n.tags.includes(activeTag)) return false;
      if (!q) return true;
      return (
        n.title.toLowerCase().includes(q) ||
        n.body.toLowerCase().includes(q) ||
        n.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [notes, query, activeTag]);

  const openCompose = () => {
    setEditing(null);
    setDraftTitle("");
    setDraftBody("");
    setDraftTags("");
    setComposing(true);
  };

  const openEdit = (n: Note) => {
    setEditing(n);
    setDraftTitle(n.title);
    setDraftBody(n.body);
    setDraftTags(n.tags.join(", "));
    setComposing(true);
  };

  const handleSave = async () => {
    if (!draftBody.trim()) {
      toast({ title: "Note is empty", description: "Add something to save." });
      return;
    }
    const tags = draftTags
      .split(",")
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean);

    if (editing) {
      await updateNote(editing.id, {
        title: draftTitle || "Untitled",
        body: draftBody,
        tags,
      });
      toast({ title: "Note updated" });
    } else {
      await createNote({ title: draftTitle || undefined, body: draftBody, tags });
      toast({ title: "Note saved" });
    }
    setComposing(false);
  };

  const handleDelete = async (id: string) => {
    await deleteNote(id);
    toast({ title: "Note deleted" });
  };

  const toggleFavorite = async (n: Note) => {
    await updateNote(n.id, { is_favorite: !n.is_favorite });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold flex items-center gap-2">
            <StickyNote className="h-5 w-5 text-primary" />
            Your Notes
          </h2>
          <p className="text-sm text-muted-foreground">
            Save teachings, insights, and your own reflections.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadMarkdown(filtered.length ? filtered : notes)}
            disabled={!notes.length}
          >
            <Download className="h-4 w-4 mr-1.5" /> Export
          </Button>
          <Button size="sm" onClick={openCompose}>
            <Plus className="h-4 w-4 mr-1.5" /> New Note
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search notes…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        {allTags.length > 0 && (
          <div className="flex gap-1.5 flex-wrap items-center">
            {allTags.map((t) => (
              <Badge
                key={t}
                variant={activeTag === t ? "default" : "outline"}
                onClick={() => setActiveTag(activeTag === t ? null : t)}
                className="cursor-pointer"
              >
                #{t}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground py-12 text-center">
          Loading your notes…
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center space-y-2">
            <StickyNote className="h-10 w-10 mx-auto text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              {notes.length === 0
                ? "No notes yet. Save a teaching from chat or write your first reflection."
                : "No notes match your search."}
            </p>
            {notes.length === 0 && (
              <Button onClick={openCompose} size="sm" className="mt-2">
                <Plus className="h-4 w-4 mr-1.5" /> Write your first note
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 grid-cols-1 md:grid-cols-2">
          <AnimatePresence initial={false}>
            {filtered.map((n) => (
              <motion.div
                key={n.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.18 }}
              >
                <Card
                  className="group cursor-pointer hover:border-primary/40 transition-colors h-full"
                  onClick={() => openEdit(n)}
                >
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-medium line-clamp-1">{n.title}</h3>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            void toggleFavorite(n);
                          }}
                          aria-label="Favorite"
                        >
                          {n.is_favorite ? (
                            <BookmarkCheck className="h-4 w-4 text-primary" />
                          ) : (
                            <Bookmark className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-7 w-7 text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDelete(n.id);
                          }}
                          aria-label="Delete"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-3 whitespace-pre-wrap">
                      {n.body}
                    </p>
                    <div className="flex flex-wrap gap-1 pt-1">
                      {n.tags.map((t) => (
                        <Badge key={t} variant="secondary" className="text-xs">
                          #{t}
                        </Badge>
                      ))}
                      {n.source_message_id && (
                        <Badge variant="outline" className="text-xs">
                          from chat
                        </Badge>
                      )}
                    </div>
                    <div className="text-[11px] text-muted-foreground pt-1">
                      {new Date(n.updated_at).toLocaleDateString()}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      <Dialog open={composing} onOpenChange={setComposing}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>{editing ? "Edit note" : "New note"}</span>
              <button
                onClick={() => setComposing(false)}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Title (optional)"
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
            />
            <Textarea
              placeholder="Write what you felt, what you want to remember…"
              value={draftBody}
              onChange={(e) => setDraftBody(e.target.value)}
              className="min-h-[180px]"
            />
            <Input
              placeholder="Tags (comma-separated, e.g. compassion, breath)"
              value={draftTags}
              onChange={(e) => setDraftTags(e.target.value)}
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={() => setComposing(false)}>
                Cancel
              </Button>
              <Button onClick={handleSave}>
                {editing ? "Save changes" : "Save note"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
