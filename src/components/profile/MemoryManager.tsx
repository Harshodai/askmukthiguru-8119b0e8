import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { List, Loader2, Mic, MicOff, Plus, Trash2, Brain, Sparkles, AlertCircle, Save, BookText, Pencil, Network, Search, X } from 'lucide-react';
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
  const [consentDialogOpen, setConsentDialogOpen] = useState(false);
  const [forgettingId, setForgettingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [clearingReflections, setClearingReflections] = useState(false);
  const [editingText, setEditingText] = useState('');
  const [editingSaving, setEditingSaving] = useState(false);

  // Voice-to-text for reflection and core memory textareas
  const reflectVoice = useSpeechRecognition({
    lang: currentLang,
    useSarvam: currentLang !== 'en',
    onTranscript: (text, isFinal) => {
      if (isFinal) setNewText((prev) => (prev ? `${prev} ${text}` : text).slice(0, 500));
    },
  });
  const coreVoice = useSpeechRecognition({
    lang: currentLang,
    useSarvam: currentLang !== 'en',
    onTranscript: (text, isFinal) => {
      if (isFinal) setCoreText((prev) => (prev ? `${prev} ${text}` : text).slice(0, 2048));
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

  // Native wheel listener with passive:false so preventDefault() actually works
  // and suppresses page scroll while zooming the graph.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || viewMode !== 'graph' || kgNodes.length === 0) return;
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      setZoom((z) => Math.min(4, Math.max(0.2, z - e.deltaY * 0.001)));
    };
    svg.addEventListener('wheel', handleWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleWheel);
  }, [viewMode, kgNodes.length]);

  const handleSaveCore = async () => {
    if (coreSaving) return;
    setCoreSaving(true);
    try {
      const saved = await memoryApi.setCore(coreText);
      setCore(saved);
      toast({ title: t('memory.coreSaved'), description: t('memory.coreSavedDesc') });
    } catch (err) {
      const msg = err instanceof MemoryApiError ? err.message : 'Could not save core memory.';
      toast({ title: t('memory.couldNotSave'), description: msg, variant: 'destructive' });
    } finally {
      setCoreSaving(false);
    }
  };

  const MEMORY_CONSENT_KEY = 'askmukthiguru_memory_consent_granted';

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

  const handleAdd = async () => {
    if (!newText.trim() || adding) return;
    if (localStorage.getItem(MEMORY_CONSENT_KEY) === 'true') {
      await saveNewMemory();
      return;
    }
    setConsentDialogOpen(true);
  };

  const handleConsentConfirm = async () => {
    setConsentDialogOpen(false);
    try {
      await memoryApi.recordConsent(true);
    } catch {
      // Best-effort receipt — a failed write to the consent log must not block a save the user already approved.
    }
    localStorage.setItem(MEMORY_CONSENT_KEY, 'true');
    await saveNewMemory();
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
      <Card>
        <CardContent className="py-12 flex justify-center">
          <Loader2 className="w-6 h-6 text-ojas animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (unavailable && !isDemo) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ojas" /> {t('memory.memory')}
          </CardTitle>
          <CardDescription>{t('memory.memoryDesc')}</CardDescription>
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

  const filteredMemories = memories.filter((m) =>
    m.content.toLowerCase().includes(listSearchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* ── Statistics Bento Dashboard ─────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-ojas/10 rounded-lg text-ojas"><Brain className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statMemories')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{memories.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-prana/10 rounded-lg text-prana"><Sparkles className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statCoreStatus')}</p>
                <p className="text-xs font-bold text-white mt-1">{coreText.trim() ? t('memory.active') : t('memory.unset')}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-blue-500/10 rounded-lg text-blue-400"><Network className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statKgNodes')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{kgNodes.length}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/40 border-zinc-800/80 backdrop-blur-sm">
            <CardContent className="p-4 flex items-center gap-3">
              <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400"><BookText className="w-4 h-4" /></div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider">{t('memory.statReflections')}</p>
                <p className="text-lg font-bold text-white mt-0.5">{summaries.length}</p>
              </div>
            </CardContent>
          </Card>
        </div>

      {/* ── Core Memory Editor ─────────────────────────────────────────── */}
      <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-ojas" /> {t('memory.coreMemory')}
            </CardTitle>
            <CardDescription>
              {t('memory.coreMemoryDesc')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={coreText}
              onChange={(e) => setCoreText(e.target.value)}
              placeholder={t('memory.corePlaceholder')}
              rows={4}
              maxLength={2048}
              disabled={coreSaving}
            />
            {coreVoice.isListening && (coreVoice.transcript || coreVoice.interimTranscript) && (
              <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-md text-xs text-foreground mt-2 animate-pulse">
                {coreVoice.transcript} <span className="text-muted-foreground italic">{coreVoice.interimTranscript}</span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => coreVoice.isListening ? coreVoice.stopListening() : void coreVoice.startListening()}
                disabled={!coreVoice.isSupported || coreSaving}
                aria-label={coreVoice.isListening ? t('chat.stopRecording', 'Stop recording') : t('chat.startVoiceInput', 'Start voice input')}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40 py-1"
              >
                {coreVoice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                {coreVoice.isListening ? t('chat.inputPlaceholderListening', 'Speak now…') : t('chat.startVoiceInput', 'Start voice input')}
              </button>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">{coreText.length}/2048</span>
                <Button
                  size="sm"
                  onClick={handleSaveCore}
                  disabled={coreSaving}
                >
                  {coreSaving ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 mr-2" />
                  )}
                  {t('common.save')}
                </Button>
              </div>
            </div>
            {core?.updated_at && (
              <p className="text-xs text-muted-foreground">{t('memory.lastSaved', { date: formatDate(core.updated_at) })}</p>
            )}
          </CardContent>
        </Card>

      {/* ── Persona (L3 Self-Synthesis) ──────────────────────────────────── */}
      {persona && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-violet-400" /> {t('memory.persona', 'Persona')}
              </CardTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={regeneratePersona}
                disabled={personaLoading}
                className="h-8 px-3 font-display text-xs"
              >
                {personaLoading ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                ) : (
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                )}
                {t('memory.regenerate', 'Regenerate')}
              </Button>
            </div>
            <CardDescription>
              {t('memory.personaDesc', 'AI-synthesized self-portrait from your recent memories')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="prose prose-invert prose-sm max-w-none text-muted-foreground whitespace-pre-wrap font-sans">
              {persona}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Skills (Auto-Generated) ──────────────────────────────────────── */}
      {skills.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-emerald-400" /> {t('memory.skills', 'Skills')}
                <Badge variant="secondary" className="ml-2 font-display">{skills.length}</Badge>
              </CardTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={regenerateSkills}
                disabled={skillsLoading}
                className="h-8 px-3 font-display text-xs"
              >
                {skillsLoading ? (
                  <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                ) : (
                  <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                )}
                {t('memory.regenerate', 'Regenerate')}
              </Button>
            </div>
            <CardDescription>
              {t('memory.skillsDesc', 'Skills and techniques identified from your practice')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {skills.map((sk) => (
                <div key={sk.id ?? sk.name} className="p-3 rounded-lg bg-zinc-900/60 border border-zinc-800/80 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-white">{sk.name}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {t('memory.proficiency', 'Proficiency')}: {Math.round((sk.proficiency ?? 0) * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-2">{sk.description}</p>
                  <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-emerald-500/70 rounded-full transition-all"
                      style={{ width: `${Math.round((sk.proficiency ?? 0) * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Episodic Memories ──────────────────────────────────────────── */}
      <Card className="rounded-2xl border-hairline shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg flex items-center gap-2 font-display font-semibold tracking-tight text-white">
              <Brain className="w-5 h-5 text-ojas" /> {t('memory.memories')}
              <Badge variant="secondary" className="ml-2 font-display">
                {memories.length}
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
          <div className="space-y-2">
              <Textarea
                value={newText}
                onChange={(e) => setNewText(e.target.value)}
                placeholder={t('memory.reflectPlaceholder')}
                rows={2}
                maxLength={500}
                disabled={adding}
              />
              {reflectVoice.isListening && (reflectVoice.transcript || reflectVoice.interimTranscript) && (
                <div className="p-2 bg-emerald-500/10 border border-emerald-500/20 rounded-md text-xs text-foreground mt-2 animate-pulse">
                  {reflectVoice.transcript} <span className="text-muted-foreground italic">{reflectVoice.interimTranscript}</span>
                </div>
              )}
              <div className="flex justify-between items-center">
                <button
                  type="button"
                  onClick={() => reflectVoice.isListening ? reflectVoice.stopListening() : void reflectVoice.startListening()}
                  disabled={!reflectVoice.isSupported || adding}
                  aria-label={reflectVoice.isListening ? t('chat.stopRecording', 'Stop recording') : t('chat.startVoiceInput', 'Start voice input')}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-ojas disabled:opacity-40"
                >
                  {reflectVoice.isListening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
                  t('chat.inputPlaceholderListening', 'Speak now…')
                </button>
                <div className="flex items-center gap-2">
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
                    {t('memory.saveMemory')}
                  </Button>
                </div>
              </div>
            </div>

          {viewMode === 'graph' ? (
            renderGraph()
          ) : (
            <div className="space-y-4">
              {/* Memories List Search */}
              {memories.length > 0 && (
                <div className="relative w-full max-w-[320px]">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    type="text"
                    placeholder={t('memory.searchPlaceholder')}
                    value={listSearchQuery}
                    onChange={(e) => setListSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-7 py-1.5 rounded-md border border-zinc-800 bg-zinc-950 text-foreground text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas"
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
                <div className="text-center py-8 space-y-2">
                  <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                    <Brain className="w-6 h-6" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {listSearchQuery ? t('memory.noMatchFound') : t('memory.noMemories')}
                  </p>
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
                        className="flex gap-3 p-3 rounded-lg bg-ojas/5 border border-ojas/10 items-start"
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
                              <Badge variant="outline" className="text-xs bg-zinc-900 border-zinc-800">
                                {t('memory.youAdded')}
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="text-xs bg-zinc-800/50">
                                {t('memory.autoExtracted')}
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

      {/* ── Session Summaries ──────────────────────────────────────────── */}
      {summaries.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <BookText className="w-5 h-5 text-ojas" /> {t('memory.sessionReflections')}
              <Badge variant="secondary" className="ml-2">{summaries.length}</Badge>
            </CardTitle>
            <CardDescription>
              {t('memory.sessionReflectionsDesc')}
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
    </div>
  );
};
