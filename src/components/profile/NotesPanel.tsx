import { useTranslation } from 'react-i18next';
import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bookmark,
  BookmarkCheck,
  Download,
  Mic,
  MicOff,
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
  DialogDescription,
} from "@/components/ui/dialog";
import { useNotes, type Note } from "@/hooks/useNotes";
import { toast } from "@/hooks/use-toast";
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';
import { Link, useLocation } from 'react-router-dom';

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
  const { t, i18n } = useTranslation();
  const currentLang = i18n?.language || 'en';
  const location = useLocation();
  const { notes, loading, error, refresh, createNote, updateNote, deleteNote } = useNotes();
  const [query, setQuery] = useState("");
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const [editing, setEditing] = useState<Note | null>(null);
  const [composing, setComposing] = useState(false);
  const [saving, setSaving] = useState(false);

  const [draftTitle, setDraftTitle] = useState("");
  const [draftBody, setDraftBody] = useState("");
  const [draftTags, setDraftTags] = useState("");

  const voice = useSpeechRecognition({
    lang: currentLang,
    useSarvam: currentLang !== 'en',
    onTranscript: (text, isFinal) => {
      if (isFinal) setDraftBody((prev) => (prev ? `${prev} ${text}` : text).slice(0, 2000));
    },
  });

  const handleVoiceToggle = () => {
    if (voice.isListening) voice.stopListening();
    else void voice.startListening();
  };

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
    if (saving) return;
    if (!draftBody.trim()) {
      toast({ title: t('notes.emptyTitle'), description: t('notes.emptyDesc') });
      return;
    }
    const tags = draftTags
      .split(",")
      .map((t) => t.trim().replace(/^#/, ""))
      .filter(Boolean);

    setSaving(true);
    try {
      const saved = editing
        ? await updateNote(editing.id, { title: draftTitle || t('notes.untitled'), body: draftBody, tags })
        : await createNote({ title: draftTitle || undefined, body: draftBody, tags });
      if (!saved) throw new Error('Save failed');
      toast({ title: editing ? t('notes.updated') : t('notes.saved') });
      setComposing(false);
    } catch {
      toast({ title: t('notes.saveFailed', 'Could not save your note'), description: t('notes.draftKept', 'Your draft is still here. Please retry.'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      if (!await deleteNote(id)) throw new Error('Delete failed');
      toast({ title: t('notes.deleted') });
    } catch {
      toast({ title: t('notes.deleteFailed', 'Could not delete your note'), variant: 'destructive' });
    }
  };

  const toggleFavorite = async (n: Note) => {
    try {
      if (!await updateNote(n.id, { is_favorite: !n.is_favorite })) throw new Error('Update failed');
    } catch {
      toast({ title: t('notes.updateFailed', 'Could not update your note'), variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2 text-foreground">
            <StickyNote className="h-5 w-5 text-ojas" aria-hidden="true" />
            {t('notes.yourNotes', 'Your Notes')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('notes.description', 'Save teachings, insights, and your own reflections.')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => downloadMarkdown(filtered.length ? filtered : notes)}
            disabled={!notes.length}
            className="rounded-xl border-hairline min-h-[44px]"
          >
            <Download className="h-4 w-4 mr-1.5" aria-hidden="true" /> {t('notes.export', 'Export')}
          </Button>
          <Button size="sm" onClick={openCompose} className="rounded-xl min-h-[44px]">
            <Plus className="h-4 w-4 mr-1.5" aria-hidden="true" /> {t('notes.newNote', 'New Note')}
          </Button>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder={t('notes.searchPlaceholder')}
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

      {error ? (
        <div role="alert" className="space-y-3 border-y border-hairline py-6">
          <p className="text-sm text-muted-foreground">{t('notes.unavailable', 'Your notes could not be loaded. Please retry.')}</p>
          <Button variant="outline" onClick={() => void refresh()}>{t('common.retry', 'Retry')}</Button>
        </div>
      ) : loading ? (
        <div className="text-sm text-muted-foreground py-12 text-center rounded-2xl border border-hairline bg-card" role="status">
          {t('notes.loading', 'Loading your notes…')}
        </div>
      ) : filtered.length === 0 ? (
        <Card className="rounded-2xl border-hairline shadow-sm">
          <CardContent className="py-12 text-center space-y-2">
            <StickyNote className="h-10 w-10 mx-auto text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              {notes.length === 0
                ? t('notes.noNotes')
                : t('notes.noMatch')}
            </p>
            {notes.length === 0 && (
              <Button onClick={openCompose} size="sm" className="mt-2">
                <Plus className="h-4 w-4 mr-1.5" /> {t('notes.writeFirst')}
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
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
                  className="group cursor-pointer rounded-2xl border-hairline shadow-sm hover:border-ojas/30 transition-colors h-full"
                >
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <Button variant="ghost" onClick={() => openEdit(n)} className="h-auto min-h-11 p-0 text-left whitespace-normal justify-start font-medium">{n.title}</Button>
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="min-h-11 min-w-11"
                          onClick={(e) => {
                            e.stopPropagation();
                            void toggleFavorite(n);
                          }}
                          aria-label={t('common.addFavorites', 'Favorites')}
                        >
                          {n.is_favorite ? (
                            <BookmarkCheck className="h-4 w-4 text-ojas" />
                          ) : (
                            <Bookmark className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="min-h-11 min-w-11 text-destructive"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDelete(n.id);
                          }}
                          aria-label={t('common.delete', 'Delete')}
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
                          {t('notes.fromChat')}
                        </Badge>
                      )}
                    </div>
                    {n.source_conversation_id && (
                      <Button asChild variant="link" className="min-h-11 h-auto px-0">
                        <Link to={`/chat?conversation=${encodeURIComponent(n.source_conversation_id)}&returnTo=${encodeURIComponent(location.pathname + location.search)}`}>
                          {t('notes.openConversation', 'Open original conversation')}
                        </Link>
                      </Button>
                    )}
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

      <Dialog open={composing} onOpenChange={(open) => { if (!saving) setComposing(open); }}>
        <DialogContent className="max-w-xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              <span>{editing ? t('notes.editNote') : t('notes.newNote')}</span>
            </DialogTitle>
            <DialogDescription>{t('notes.description', 'Save teachings, insights, and your own reflections.')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder={t('notes.titlePlaceholder')}
              value={draftTitle}
              onChange={(e) => setDraftTitle(e.target.value)}
            />
            <Textarea
              placeholder={t('notes.bodyPlaceholder')}
              value={draftBody}
              onChange={(e) => setDraftBody(e.target.value)}
              className="min-h-[180px]"
            />
            {voice.isListening && (voice.transcript || voice.interimTranscript) && (
              <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-md text-xs text-foreground mt-2 animate-pulse">
                {voice.transcript} <span className="text-muted-foreground italic">{voice.interimTranscript}</span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <Button variant="ghost" size="sm"
                type="button"
                onClick={handleVoiceToggle}
                disabled={!voice.isSupported}
                aria-label={voice.isListening ? t('chat.stopRecording', 'Stop recording') : t('chat.startVoiceInput', 'Start voice input')}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40 py-1"
              >
                {voice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                {voice.isListening ? t('chat.inputPlaceholderListening', 'Speak now…') : t('chat.startVoiceInput', 'Start voice input')}
              </Button>
              {voice.error && (
                <span className="text-[10px] text-destructive">{voice.error}</span>
              )}
            </div>
            <Input
              placeholder={t('notes.tagsPlaceholder')}
              value={draftTags}
              onChange={(e) => setDraftTags(e.target.value)}
            />
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" disabled={saving} onClick={() => setComposing(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleSave} disabled={saving || !draftBody.trim()}>
                {editing ? t('notes.saveChanges') : t('notes.saveNote')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
