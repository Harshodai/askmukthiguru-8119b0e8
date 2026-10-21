import { useTranslation } from 'react-i18next';
import { useEffect, useRef, useState } from 'react';
import { List, Loader2, Mic, MicOff, Plus, Trash2, Brain, Sparkles, AlertCircle, Save, BookText, Pencil, Network, RotateCcw, Search, X } from 'lucide-react';
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
  type UserSkill,
} from '@/lib/memoryApi';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';
import { KGConceptMap } from '@/components/kg/KGConceptMap';

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
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const currentLang = i18n?.language || 'en';
  const [memories, setMemories] = useState<GuruMemory[]>([]);
  const [core, setCore] = useState<CoreMemory | null>(null);
  const [coreText, setCoreText] = useState('');
  const [coreSaving, setCoreSaving] = useState(false);
  const [summaries, setSummaries] = useState<SessionSummary[]>([]);
  const [conversations, setConversations] = useState<ConversationContinuity[]>([]);
  const [persona, setPersona] = useState<string>('');
  const [personaLoading, setPersonaLoading] = useState(false);
  const [skills, setSkills] = useState<UserSkill[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [isDemo, setIsDemo] = useState(false);
  const [newText, setNewText] = useState('');
  const [adding, setAdding] = useState(false);
  const [pinAsCore, setPinAsCore] = useState(false);
  const [consentDialogOpen, setConsentDialogOpen] = useState(false);
  const [forgettingId, setForgettingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [clearingReflections, setClearingReflections] = useState(false);
  const [editingText, setEditingText] = useState('');
  const [editingSaving, setEditingSaving] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // Voice-to-text for the single memory composer.
  const composerLimit = pinAsCore ? 2048 : 500;
  const reflectVoice = useSpeechRecognition({
    lang: currentLang,
    useSarvam: currentLang !== 'en',
    onTranscript: (text, isFinal) => {
      if (isFinal) setNewText((prev) => (prev ? `${prev} ${text}` : text).slice(0, composerLimit));
    },
  });

  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');

  const [listSearchQuery, setListSearchQuery] = useState('');

  const refresh = async () => {
    setLoading(true);
    setUnavailable(null);
    const [listResult, coreResult, summariesResult, conversationsResult, personaResult, skillsResult] = await Promise.allSettled([
      memoryApi.list(1, 100),
      memoryApi.getCore(),
      memoryApi.getSummaries(10),
      memoryApi.getConversations(5),
      memoryApi.getPersona(),
      memoryApi.getSkills(),
    ]);
    if (listResult.status === 'fulfilled') {
      setMemories(listResult.value.memories);
      setIsDemo(false);
    } else {
      setMemories([]);
      setIsDemo(false);
      setUnavailable(t('memory.unavailable', 'Your saved memories are unavailable right now. Please try again.'));
    }
    if (coreResult.status === 'fulfilled') {
      setCore(coreResult.value);
      setCoreText(coreResult.value?.content ?? '');
    }
    if (summariesResult.status === 'fulfilled') {
      setSummaries(summariesResult.value);
    }
    if (conversationsResult.status === 'fulfilled') {
      setConversations(conversationsResult.value);
    }
    if (personaResult.status === 'fulfilled') {
      setPersona(personaResult.value.content ?? '');
    }
    if (skillsResult.status === 'fulfilled') {
      setSkills(skillsResult.value ?? []);
    }
    setLoading(false);
  };

  const regeneratePersona = async () => {
    setPersonaLoading(true);
    try {
      const res = await memoryApi.regeneratePersona();
      setPersona(res.content ?? '');
      toast({ title: t('memory.personaRegenerated', 'Persona refreshed') });
    } catch {
      toast({ title: t('memory.personaRegenerateFailed', 'Could not refresh persona'), variant: 'destructive' });
    } finally {
      setPersonaLoading(false);
    }
  };

  const regenerateSkills = async () => {
    setSkillsLoading(true);
    try {
      const updated = await memoryApi.regenerateSkills();
      setSkills(updated ?? []);
      toast({ title: t('memory.skillsRegenerated', 'Skills refreshed') });
    } catch {
      toast({ title: t('memory.skillsRegenerateFailed', 'Could not refresh skills'), variant: 'destructive' });
    } finally {
      setSkillsLoading(false);
    }
  };

  useEffect(() => {
    refresh();

  }, []);

  const saveNewMemory = async () => {
    setAdding(true);
    try {
      const created = await memoryApi.add(newText);
      setMemories((prev) => [created, ...prev]);
      setNewText('');
      toast({ title: t('memory.memorySaved'), description: t('memory.memorySavedDesc') });
      memoryApi.reflect().then((res) => {
        if (res.status === 'ok') {
          setPersona(res.persona ?? '');
          setSkills(res.skills ?? []);
        }
      });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save memory.';
      toast({ title: t('memory.couldNotSave'), description: msg, variant: 'destructive' });
    } finally {
      setAdding(false);
    }
  };

  const saveGuidingNote = async () => {
    setCoreSaving(true);
    try {
      const saved = await memoryApi.setCore(newText.trim().slice(0, 2048));
      setCore(saved);
      setCoreText(saved?.content ?? newText.trim());
      setNewText('');
      setPinAsCore(false);
      toast({ title: t('memory.coreSaved'), description: t('memory.coreSavedDesc') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save core memory.';
      toast({ title: t('memory.couldNotSave'), description: msg, variant: 'destructive' });
    } finally {
      setCoreSaving(false);
    }
  };

  const handleComposerSave = async () => {
    if (!newText.trim() || adding || coreSaving) return;
    // The backend receipt is authoritative for both a normal memory and the
    // core guiding note. Neither UI path may bypass the same consent contract.
    try {
      if (await memoryApi.hasConsent()) {
        if (pinAsCore) await saveGuidingNote();
        else await saveNewMemory();
        return;
      }
    } catch (err) {
      const msg = err instanceof MemoryApiError
        ? err.message
        : 'Could not verify memory consent. Please try again.';
      toast({ title: t('memory.couldNotSave', 'Could not save memory'), description: msg, variant: 'destructive' });
      return;
    }
    setConsentDialogOpen(true);
  };

  const handleConsentConfirm = async () => {
    setConsentDialogOpen(false);
    try {
      // Do not persist the memory unless the server confirms consent. The chat
      // extraction pipeline reads this same receipt and fails closed without it.
      await memoryApi.recordConsent(true);
    } catch (err) {
      const msg = err instanceof MemoryApiError
        ? err.message
        : 'Could not record memory consent. Please try again.';
      toast({ title: t('memory.couldNotSave', 'Could not save memory'), description: msg, variant: 'destructive' });
      return;
    }
    if (pinAsCore) await saveGuidingNote();
    else await saveNewMemory();
  };

  const handleEdit = async (id: string) => {
    if (isDemo || !editingText.trim() || editingSaving) return;
    setEditingSaving(true);
    try {
      await memoryApi.edit(id, editingText.trim());
      setMemories((prev) => prev.map((m) => m.id === id ? { ...m, content: editingText.trim() } : m));
      setEditingId(null);
      setEditingText('');
      toast({ title: t('memory.updated', 'Memory updated') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not update memory.';
      toast({ title: t('memory.couldNotUpdate', 'Could not update memory'), description: msg, variant: 'destructive' });
    } finally {
      setEditingSaving(false);
    }
  };

  const handleForget = async (id: string) => {
    if (isDemo) return;
    setForgettingId(id);
    try {
      await memoryApi.forget(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
      toast({ title: t('memory.forgotten'), description: t('memory.forgottenDesc') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not forget memory.';
      toast({ title: t('memory.couldNotForget'), description: msg, variant: 'destructive' });
    } finally {
      setForgettingId(null);
    }
  };

  const handleForgetAllReflections = async () => {
    if (isDemo || clearingReflections) return;
    setClearingReflections(true);
    try {
      await memoryApi.forgetAllReflections();
      setMemories([]);
      toast({ title: t('memory.reflectionsCleared', 'Reflections cleared') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not clear reflections.';
      toast({ title: t('memory.couldNotClear', 'Could not clear reflections'), description: msg, variant: 'destructive' });
    } finally {
      setClearingReflections(false);
    }
  };

  const renderGraph = () => (
    <div className="overflow-hidden rounded-2xl border border-hairline bg-card">
      <KGConceptMap initialQuery="" embedded />
    </div>
  );

  if (loading) {
    return (
      <Card className="rounded-2xl border-hairline shadow-sm">
        <CardContent className="py-12 flex flex-col items-center justify-center gap-3" role="status" aria-label={t('common.loading', 'Loading…')}>
          <Loader2 className="w-6 h-6 text-ojas animate-spin" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">{t('memory.loading', 'Loading your memories…')}</p>
        </CardContent>
      </Card>
    );
  }

  if (unavailable) {
    return (
      <Card className="rounded-2xl border-hairline shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" aria-hidden="true" /> {t('memory.memory', 'Memory')}
          </CardTitle>
          <CardDescription>{t('memory.memoryDesc', 'Your saved reflections and personal context.')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3 p-4 rounded-2xl bg-muted/30 border border-hairline">
            <AlertCircle className="w-5 h-5 text-muted-foreground shrink-0" aria-hidden="true" />
            <p className="text-sm text-muted-foreground">{unavailable}</p>
          </div>
          <Button variant="outline" size="sm" className="mt-4 rounded-xl" onClick={() => void refresh()}>
            {t('common.retry', 'Retry')}
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Owner rule: user-added ("explicit") memories never render in the memory
  // section — this tab shows auto-extracted teachings context only. Explicit
  // saves still persist server-side (Second Brain owns them).
  const filteredMemories = memories.filter(
    (m) =>
      m.source !== 'explicit' &&
      m.content.toLowerCase().includes(listSearchQuery.toLowerCase())
  );
  const visibleCount = filteredMemories.length;
  const hasStats = visibleCount > 0 || summaries.length > 0 || coreText.trim().length > 0;
  const showRemembers = persona.trim().length > 0 || skills.length > 0 || summaries.length > 0;

  const focusComposer = () => {
    composerRef.current?.focus();
    composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <div className="space-y-6">
      {/* ── Statistics (hidden until there is something to count) ───────── */}
      {hasStats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Card className="rounded-2xl border-hairline bg-card shadow-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-ojas/10 rounded-xl text-ojas"><Brain className="w-4 h-4" aria-hidden="true" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statMemories', 'Memories')}</p>
                <p className="text-lg font-bold text-foreground mt-0.5">{visibleCount}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-hairline bg-card shadow-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-prana/10 rounded-xl text-prana"><Sparkles className="w-4 h-4" aria-hidden="true" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statCoreStatus', 'Core Status')}</p>
                <p className="text-xs font-bold text-foreground mt-1">{coreText.trim() ? t('memory.active', 'Active') : t('memory.unset', 'Unset')}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="rounded-2xl border-hairline bg-card shadow-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-emerald-500/10 rounded-xl text-emerald-600 dark:text-emerald-400"><BookText className="w-4 h-4" aria-hidden="true" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statReflections', 'Reflections')}</p>
                <p className="text-lg font-bold text-foreground mt-0.5">{summaries.length}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ── What the guru remembers (persona + skills + reflections, merged) */}
      {showRemembers && (
        <Card className="rounded-2xl border-hairline shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-ojas" aria-hidden="true" /> {t('memory.guruRemembers', 'What the guru remembers')}
            </CardTitle>
            <CardDescription>
              {t('memory.guruRemembersDesc', 'A living portrait drawn from your saved memories — refreshed as you share more.')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {persona.trim() && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{t('memory.persona', 'Persona')}</h3>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={regeneratePersona}
                    disabled={personaLoading}
                    className="h-8 px-3 rounded-xl text-xs"
                  >
                    {personaLoading ? (
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <RotateCcw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
                    )}
                    {t('memory.regenerate', 'Regenerate')}
                  </Button>
                </div>
                <div className="prose prose-sm max-w-none text-muted-foreground whitespace-pre-wrap font-sans dark:prose-invert">
                  {persona}
                </div>
              </div>
            )}

            {skills.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {t('memory.skills', 'Skills')} · {skills.length}
                  </h3>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={regenerateSkills}
                    disabled={skillsLoading}
                    className="h-8 px-3 rounded-xl text-xs"
                  >
                    {skillsLoading ? (
                      <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <RotateCcw className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
                    )}
                    {t('memory.regenerate', 'Regenerate')}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">{t('memory.skillsDesc', 'Skills and techniques identified from your practice')}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {skills.map((sk) => (
                    <div key={sk.id ?? sk.name} className="p-3 rounded-2xl bg-muted/30 border border-hairline space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">{sk.name}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {t('memory.proficiency', 'Proficiency')}: {Math.round((sk.proficiency ?? 0) * 100)}%
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground line-clamp-2">{sk.description}</p>
                      <div className="w-full h-1 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500/70 rounded-full transition-all"
                          style={{ width: `${Math.round((sk.proficiency ?? 0) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {summaries.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {t('memory.sessionReflections', 'Session reflections')} · {summaries.length}
                </h3>
                <ul className="space-y-3">
                  {summaries.map((s) => (
                    <li
                      key={s.id}
                      className="p-3 rounded-2xl bg-prana/5 border border-prana/10"
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
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ── Composer: one box for remembering (memory or guiding note) ───── */}
      <Card className="rounded-2xl border-hairline shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" aria-hidden="true" /> {t('memory.rememberThis', 'What should the guru remember?')}
          </CardTitle>
          <CardDescription>
            {t('memory.rememberThisDesc', 'Share a reflection to save it. Pin it to also keep it as your guiding note.')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {coreText.trim() && (
            <p className="text-xs text-muted-foreground rounded-2xl border border-hairline bg-muted/30 px-4 py-2.5 line-clamp-2">
              <span className="font-semibold text-foreground/80">{t('memory.guidingNote', 'Guiding note')}: </span>
              {coreText.trim()}
            </p>
          )}
          <Textarea
            ref={composerRef}
            value={newText}
            onChange={(e) => setNewText(e.target.value.slice(0, composerLimit))}
            placeholder={t('memory.reflectPlaceholder', 'Share a reflection to save it…')}
            rows={3}
            maxLength={composerLimit}
            disabled={adding || coreSaving}
          />
          {reflectVoice.isListening && (reflectVoice.transcript || reflectVoice.interimTranscript) && (
            <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-md text-xs text-foreground mt-2 animate-pulse">
              {reflectVoice.transcript} <span className="text-muted-foreground italic">{reflectVoice.interimTranscript}</span>
            </div>
          )}
          <div className="flex flex-wrap justify-between items-center gap-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => reflectVoice.isListening ? reflectVoice.stopListening() : void reflectVoice.startListening()}
                disabled={!reflectVoice.isSupported || adding || coreSaving}
                aria-label={reflectVoice.isListening ? t('chat.stopRecording', 'Stop recording') : t('chat.startVoiceInput', 'Start voice input')}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40 min-h-[36px]"
              >
                {reflectVoice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                {reflectVoice.isListening ? t('chat.inputPlaceholderListening', 'Speak now…') : t('chat.startVoiceInput', 'Start voice input')}
              </button>
              <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer min-h-[36px]">
                <input
                  type="checkbox"
                  checked={pinAsCore}
                  onChange={(e) => setPinAsCore(e.target.checked)}
                  disabled={adding || coreSaving}
                  className="w-4 h-4 rounded accent-ojas"
                />
                {t('memory.pinAsGuidingNote', 'Pin as guiding note')}
              </label>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {newText.length}/{composerLimit}
              </span>
              <Button
                size="sm"
                onClick={handleComposerSave}
                disabled={!newText.trim() || adding || coreSaving}
                className="rounded-xl min-h-[40px]"
              >
                {(adding || coreSaving) ? (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Plus className="w-4 h-4 mr-2" />
                )}
                {t('memory.saveMemory', 'Save memory')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Episodic Memories ──────────────────────────────────────────── */}
      <Card className="rounded-2xl border-hairline shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2 font-display font-semibold tracking-tight text-foreground">
              <Brain className="w-5 h-5 text-ojas" aria-hidden="true" /> {t('memory.memories', 'Memories')}
              <Badge variant="secondary" className="ml-2 font-display">
                {visibleCount}
              </Badge>
              {isDemo && (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-400 border-amber-500/30 text-[10px] tracking-wide">
                  DEMO
                </Badge>
              )}
            </CardTitle>
            {!isDemo && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 px-2 text-muted-foreground hover:text-destructive" disabled={clearingReflections}>
                    {clearingReflections ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                    <span className="sr-only">{t('memory.clearReflections', 'Clear reflections')}</span>
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>{t('memory.clearReflections', 'Clear reflections')}</AlertDialogTitle>
                    <AlertDialogDescription>{t('memory.clearReflectionsWarning', 'This permanently removes episodic reflections while preserving your core memory.')}</AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={() => void handleForgetAllReflections()}>{t('memory.clearReflectionsConfirm', 'Clear reflections')}</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
            <div className="flex gap-1">
              <Button
                  variant={viewMode === 'list' ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setViewMode('list')}
                  className="h-8 px-2 font-display"
                  title={t('memory.listView')}
                >
                  <List className="w-4 h-4" />
                </Button>
              <Button
                variant={viewMode === 'graph' ? 'default' : 'outline'}
                size="sm"
                onClick={() => setViewMode('graph')}
                className="h-8 px-2 font-display"
                title={t('memory.graphView')}
              >
                <Network className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <CardDescription className="font-sans text-xs">
            {t('memory.graphDesc')}
            {isDemo && (
              <span className="block mt-1 text-amber-400/80">
                {t('memory.demoMode', 'Service unavailable — showing sample memories')}
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {viewMode === 'graph' ? (
            renderGraph()
          ) : (
            <div className="space-y-4">
              {/* Memories List Search */}
              {visibleCount > 0 && (
                <div className="relative w-full max-w-[320px]">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder={t('memory.searchPlaceholder', 'Search memories...')}
                    value={listSearchQuery}
                    onChange={(e) => setListSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-7 py-1.5 rounded-xl border border-hairline bg-background text-foreground text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas"
                  />
                  {listSearchQuery && (
                    <button
                      onClick={() => setListSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}

              {filteredMemories.length === 0 ? (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 rounded-2xl border border-dashed border-hairline px-4 py-5">
                  <p className="text-sm text-muted-foreground">
                    {listSearchQuery
                      ? t('memory.noMatchFound', 'No memories match your search.')
                      : t('memory.noMemoriesYet', 'Nothing saved yet — add your first memory above.')}
                  </p>
                  {!listSearchQuery && (
                    <Button variant="outline" size="sm" className="rounded-xl shrink-0 min-h-[40px]" onClick={focusComposer}>
                      <Plus className="w-4 h-4 mr-1.5" />
                      {t('memory.addFirstMemory', 'Add a memory')}
                    </Button>
                  )}
                </div>
              ) : (
                <ul className="space-y-2">
                  <AnimatePresence initial={false}>
                    {filteredMemories.map((m) => (
                      <motion.li
                        key={m.id}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, height: 0 }}
                        className="flex gap-3 p-3 rounded-2xl bg-ojas/5 border border-ojas/10 items-start"
                      >
                        <div className="flex-1 min-w-0">
                          {editingId === m.id ? (
                            <div className="space-y-2">
                              <Textarea
                                value={editingText}
                                onChange={(e) => setEditingText(e.target.value.slice(0, 2048))}
                                maxLength={2048}
                                rows={3}
                                aria-label={t('memory.editAria', 'Correct memory')}
                              />
                              <div className="flex gap-2">
                                <Button size="sm" onClick={() => handleEdit(m.id)} disabled={editingSaving || !editingText.trim()}>
                                  {editingSaving ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Save className="w-3 h-3 mr-1" />}
                                  {t('common.save')}
                                </Button>
                                <Button size="sm" variant="ghost" onClick={() => { setEditingId(null); setEditingText(''); }}>
                                  {t('common.cancel', 'Cancel')}
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <p className="text-sm text-foreground/90 leading-relaxed font-serif">
                              "{m.content}"
                            </p>
                          )}
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            <span className="text-xs text-muted-foreground">
                              {formatDate(m.created_at)}
                            </span>
                            {m.source === 'explicit' ? (
                              // Unreachable by owner rule (explicit filtered
                              // above); kept as a labeled dead-end so a future
                              // regression shows "You added" instead of lying.
                              <Badge variant="outline" className="text-xs">
                                {t('memory.youAdded', 'You added')}
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="text-xs">
                                {t('memory.autoExtracted', 'Auto-extracted')}
                              </Badge>
                            )}
                            {typeof m.decay_score === 'number' && (
                              <span
                                className="text-xs text-muted-foreground"
                                title={t('memory.retentionTooltip', 'Fades from memory over time unless reinforced')}
                              >
                                {t('memory.retention', 'Retention')}: {Math.round(m.decay_score * 100)}%
                              </span>
                            )}
                          </div>
                        </div>
                        {!isDemo && editingId !== m.id && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="shrink-0 text-muted-foreground hover:text-foreground"
                            onClick={() => { setEditingId(m.id); setEditingText(m.content); }}
                            aria-label={t('memory.editAria', 'Correct memory')}
                          >
                            <Pencil className="w-4 h-4" />
                          </Button>
                        )}
                        {!isDemo && (
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="shrink-0 text-muted-foreground hover:text-destructive"
                              disabled={forgettingId === m.id}
                              aria-label={t('memory.forgetAria')}
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
                              <AlertDialogTitle>{t('memory.forgetTitle')}</AlertDialogTitle>
                              <AlertDialogDescription>
                                "{m.content}"
                                <br />
                                <br />
                                {t('memory.forgetWarning')}
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>{t('common.keep')}</AlertDialogCancel>
                              <AlertDialogAction onClick={() => handleForget(m.id)}>
                                {t('memory.forgetBtn')}
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                        )}
                      </motion.li>
                    ))}
                  </AnimatePresence>
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Consent dialog for first-time memory saves */}
      <AlertDialog open={consentDialogOpen} onOpenChange={setConsentDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('memory.consentTitle', 'Save this memory?')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('memory.consentDesc', 'Saved memories help personalize your guidance. You can review or forget them anytime from this page.')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel', 'Cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleConsentConfirm()}>
              {t('memory.consentConfirm', 'Save memory')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
