import { useEffect, useState } from 'react';
import { Loader2, Plus, Trash2, Brain, Sparkles, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { useToast } from '@/hooks/use-toast';
import {
  memoryApi,
  MemoryApiError,
  type CoreMemory,
  type GuruMemory,
  type SessionSummary,
  type ConversationContinuity,
} from '@/lib/memoryApi';
import { BookText, MessagesSquare } from 'lucide-react';

const formatDate = (iso: string): string => {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
};

export const MemoryManager = () => {
  const { toast } = useToast();
  const [memories, setMemories] = useState<GuruMemory[]>([]);
  const [core, setCore] = useState<CoreMemory | null>(null);
  const [summaries, setSummaries] = useState<SessionSummary[]>([]);
  const [conversations, setConversations] = useState<ConversationContinuity[]>([]);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);
  const [forgettingId, setForgettingId] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setUnavailable(null);
    try {
      const [list, coreData, summariesData, conversationsData] = await Promise.all([
        memoryApi.list(1, 100),
        memoryApi.getCore(),
        memoryApi.getSummaries(10),
        memoryApi.getConversations(5),
      ]);
      setMemories(list.memories);
      setCore(coreData);
      setSummaries(summariesData);
      setConversations(conversationsData);
    } catch (err) {
      if (err instanceof MemoryApiError) {
        if (err.code === 'feature_disabled' || err.code === 'not_configured') {
          setUnavailable(
            "The memory layer isn't live yet. Once the backend ships, your guru will start remembering what you share.",
          );
        } else if (err.code === 'unauthorized') {
          setUnavailable('Sign in to view your memories.');
        } else {
          setUnavailable(err.message);
        }
      } else {
        setUnavailable('Could not load memories.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAdd = async () => {
    if (!newText.trim() || adding) return;
    setAdding(true);
    try {
      const created = await memoryApi.add(newText);
      setMemories((prev) => [created, ...prev]);
      setNewText('');
      toast({ title: 'Memory saved', description: 'The guru will remember this.' });
    } catch (err) {
      const msg =
        err instanceof MemoryApiError ? err.message : 'Could not save memory.';
      toast({ title: 'Could not save', description: msg, variant: 'destructive' });
    } finally {
      setAdding(false);
    }
  };

  const handleForget = async (id: string) => {
    setForgettingId(id);
    try {
      await memoryApi.forget(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      toast({ title: 'Forgotten', description: 'This memory has been released.' });
    } catch (err) {
      const msg =
        err instanceof MemoryApiError ? err.message : 'Could not forget memory.';
      toast({ title: 'Could not forget', description: msg, variant: 'destructive' });
    } finally {
      setForgettingId(null);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="w-6 h-6 text-ojas animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (unavailable) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" /> Memory
          </CardTitle>
          <CardDescription>What the guru remembers about you.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3 p-4 rounded-lg bg-muted/40 border border-border">
            <AlertCircle className="w-5 h-5 text-muted-foreground shrink-0" />
            <p className="text-sm text-muted-foreground">{unavailable}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const coreThemes = core?.profile?.dominant_themes ?? [];
  const coreLevel = core?.profile?.practice_level;

  return (
    <div className="space-y-6">
      {core && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-ojas" /> Core profile
            </CardTitle>
            <CardDescription>
              Always present in your guru's awareness. Updated nightly.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {coreLevel && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-muted-foreground">Practice level:</span>
                <Badge variant="secondary" className="capitalize">
                  {coreLevel}
                </Badge>
              </div>
            )}
            {coreThemes.length > 0 && (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Recurring themes:</p>
                <div className="flex flex-wrap gap-2">
                  {coreThemes.map((t) => (
                    <Badge key={t} variant="outline">
                      {t}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-muted-foreground pt-2">
              Last updated {formatDate(core.updated_at)}
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" /> Memories
            <Badge variant="secondary" className="ml-2">
              {memories.length}
            </Badge>
          </CardTitle>
          <CardDescription>
            Add a fact you'd like remembered, or release one that no longer fits.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Textarea
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              placeholder="e.g. I practice every morning before sunrise."
              rows={2}
              maxLength={500}
              disabled={adding}
            />
            <div className="flex justify-between items-center">
              <span className="text-xs text-muted-foreground">
                {newText.length}/500
              </span>
              <Button
                size="sm"
                onClick={handleAdd}
                disabled={!newText.trim() || adding}
              >
                {adding ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="w-4 h-4 mr-2" />
                )}
                Save memory
              </Button>
            </div>
          </div>

          {memories.length === 0 ? (
            <div className="text-center py-8 space-y-2">
              <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                <Brain className="w-6 h-6" />
              </div>
              <p className="text-sm text-muted-foreground">
                No memories yet. Continue your conversations and the guru will
                gradually learn what matters to you.
              </p>
            </div>
          ) : (
            <ul className="space-y-2">
              <AnimatePresence initial={false}>
                {memories.map((m) => (
                  <motion.li
                    key={m.id}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex gap-3 p-3 rounded-lg bg-ojas/5 border border-ojas/10 items-start"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground/90 leading-relaxed">
                        {m.claim}
                      </p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className="text-xs text-muted-foreground">
                          {formatDate(m.last_seen)}
                        </span>
                        {m.source === 'explicit' && (
                          <Badge variant="outline" className="text-xs">
                            You added
                          </Badge>
                        )}
                      </div>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="shrink-0 text-muted-foreground hover:text-destructive"
                          disabled={forgettingId === m.id}
                          aria-label="Forget this memory"
                        >
                          {forgettingId === m.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Forget this memory?</AlertDialogTitle>
                          <AlertDialogDescription>
                            "{m.claim}"
                            <br />
                            <br />
                            The guru will no longer reference this in future
                            conversations. This cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Keep</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleForget(m.id)}>
                            Forget
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ul>
          )}
        </CardContent>
      </Card>

      {summaries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <BookText className="w-5 h-5 text-ojas" /> Session reflections
              <Badge variant="secondary" className="ml-2">{summaries.length}</Badge>
            </CardTitle>
            <CardDescription>
              Distilled summaries the guru keeps from your past sessions.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {summaries.map((s) => (
                <li
                  key={s.id}
                  className="p-3 rounded-lg bg-prana/5 border border-prana/10"
                >
                  <p className="text-sm text-foreground/90 leading-relaxed italic">
                    "{s.summary}"
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {formatDate(s.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {conversations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <MessagesSquare className="w-5 h-5 text-ojas" /> Conversation continuity
            </CardTitle>
            <CardDescription>
              Recent threads the guru carries forward to maintain context.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {conversations.map((c) => (
                <li
                  key={c.session_id}
                  className="p-3 rounded-lg bg-muted/40 border border-border space-y-2"
                >
                  <p className="text-xs text-muted-foreground">
                    {formatDate(c.started_at)}
                  </p>
                  {c.key_insights && c.key_insights.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-foreground/80 mb-1">Key insights</p>
                      <ul className="list-disc list-inside text-sm text-foreground/80 space-y-0.5">
                        {c.key_insights.slice(0, 3).map((k, i) => (
                          <li key={i}>{k}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {c.follow_up_suggestions && c.follow_up_suggestions.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold text-foreground/80 mb-1">Follow-ups</p>
                      <div className="flex flex-wrap gap-1.5">
                        {c.follow_up_suggestions.slice(0, 3).map((f, i) => (
                          <Badge key={i} variant="outline" className="text-xs">{f}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
