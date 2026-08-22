import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Camera,
  Trash2,
  Download,
  Save,
  Flame,
  AlertTriangle,
  Sparkles,
  Sun,
  Moon,
  Monitor,
  Bell,
  BellRing,
  Heart,
  TrendingUp,
  Target,
  ArrowRight,
  Loader2,
  MessageCircle,
  Mail,
  ExternalLink,
  Bug,
  Clock,
  CheckCircle2,
  XCircle,
  Globe,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { normalizeSarvamVoice, SARVAM_VOICES } from '@/lib/sarvamVoices';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical } from '@/lib/domain';
import { fireTestReminder, requestNotificationPermission } from '@/hooks/useMeditationReminder';
import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import { useProfile } from '@/hooks/useProfile';
import {
  GuruTone,
  exportAllData,
  deleteAllData,
  readAvatarFile,
  getInitials,
  resetProfile,
  type PrePracticeAnswer,
} from '@/lib/profileStorage';
import { getMeditationStats, getMeditationStatsFromDb, getMeditationSessionsFromDb, loadMeditationSessions, type MeditationStats } from '@/lib/meditationStorage';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { clearLocalChatData, loadConversations, deleteConversation, getCurrentConversationId, type Conversation, getMaxConversations, getRetentionDays, setRetentionDays as saveRetentionDays, formatRelativeTime } from '@/lib/chatStorage';
import { derivePersonalInsights, type PersonalInsight } from '@/lib/personalInsights';
import { memoryApi, type GuruMemory } from '@/lib/memoryApi';
import { clearResponsePreferences } from '@/lib/chat/responsePreferences';
import { MemoryManager } from '@/components/profile/MemoryManager';
import { NotesPanel } from '@/components/profile/NotesPanel';
import { ProfileStatTiles } from '@/components/profile/ProfileStatTiles';
import { TwoFactorSettings } from '@/components/auth/TwoFactorSettings';
import { useToast } from '@/hooks/use-toast';
import { useTheme } from '@/hooks/useTheme';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { supabase } from '@/integrations/supabase/client';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { useMetrics } from '@/hooks/useMetrics';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { useTranslation } from 'react-i18next';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { CancelFlow } from '@/components/profile/CancelFlow';

const tones: { value: GuruTone; label: string; hint: string }[] = [
  { value: 'gentle', label: 'Gentle', hint: 'Soft, nurturing replies' },
  { value: 'direct', label: 'Direct', hint: 'Clear, concise teachings' },
  { value: 'poetic', label: 'Poetic', hint: 'Lyrical, metaphor-rich' },
];

const themes: { value: 'light' | 'dark' | 'system'; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

// bulbul:v3 voices — derived from shared SARVAM_VOICES singleton
const voiceOptions = SARVAM_VOICES.map((v) => ({
  value: v.id,
  label: v.label,
  hint: `${v.gender === 'female' ? 'Female' : 'Male'} · ${v.hint}`,
}));

const normalizeVoice = (voice?: string): string => normalizeSarvamVoice(voice);

const formatTime = (mins: number): string => {
  const h = Math.floor(mins / 60).toString().padStart(2, '0');
  const m = (mins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
};

const ProfilePage = () => {
  const { loading: authLoading, user } = useRequireAuth();
  usePageMeta({
    title: 'Your Profile — AskMukthiGuru',
    description: 'Manage your seeker profile, preferred guru tone, language, theme, and meditation reminder settings.',
    canonical: buildCanonical('/profile'),
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const tabParam = searchParams.get('tab');
  const initialTab = (tabParam === 'privacy' || tabParam === 'memory') ? 'memory' : (tabParam || 'profile');
  const [tab, setTab] = useState(initialTab);
  const { profile, update } = useProfile();
  const { toast } = useToast();
  const { t } = useTranslation();
  const { setTheme: applyThemeNow } = useTheme();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { teaching: dailyTeaching } = useDailyTeaching();
  const { metrics, loading: metricsLoading, error: metricsError } = useMetrics();

  // Local form state — only persists on Save
  const [form, setForm] = useState(profile);
  const [dirty, setDirty] = useState(false);

  // Support form state
  const [supportForm, setSupportForm] = useState({ name: '', email: '', subject: '', message: '', category: 'Feedback' });
  const [supportLoading, setSupportLoading] = useState(false);
  const [supportSent, setSupportSent] = useState(false);

  useEffect(() => {
    setForm(profile);
    setDirty(false);
  }, [profile]);

  const resolveName = (): string => {
    const raw = profile.displayName || user?.user_metadata?.full_name || '';
    return raw && raw !== 'Seeker' ? raw : '';
  };

  const resolveEmail = (): string => {
    return user?.email || '';
  };

  useEffect(() => {
    if (user || profile) {
      const resolvedName = resolveName();
      const resolvedEmail = resolveEmail();
      setSupportForm((prev) => ({
        ...prev,
        name: resolvedName || prev.name || '',
        email: resolvedEmail || prev.email || '',
      }));
    }
  }, [user, profile]);

  useEffect(() => {
    setSearchParams(tab === 'profile' ? {} : { tab }, { replace: true });
  }, [tab, setSearchParams]);

  const [stats, setStats] = useState<MeditationStats>(() => getMeditationStats());
  const [sessions, setSessions] = useState<NormalizedSession[]>(() =>
    loadMeditationSessions().map((s) => ({
      at: new Date(s.completedAt ?? s.startedAt),
      durationSeconds: s.durationSeconds ?? 0,
      breathCycles: s.breathCycles ?? 0,
      completed: s.completed,
    })),
  );
  const [conversationCount, setConversationCount] = useState<number>(0);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [retention, setRetention] = useState<number>(getMaxConversations());
  const [retentionDays, setRetentionDays_] = useState<number>(getRetentionDays());
  const [deleteAllConfirm, setDeleteAllConfirm] = useState<string>('');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [personalInsights, setPersonalInsights] = useState<PersonalInsight[]>([]);
  const [recalledTeachings, setRecalledTeachings] = useState<{ content: string; recall_count: number }[]>([]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const dbStats = await getMeditationStatsFromDb();
      if (!cancelled) setStats(dbStats);
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.user) {
        const { count } = await supabase
          .from('conversations')
          .select('id', { count: 'exact', head: true })
          .eq('user_id', session.user.id);
        if (!cancelled && typeof count === 'number') setConversationCount(count);
      }
      // Derive richer insights from local sessions + backend memory (if live).
      const localSessions = loadMeditationSessions();
      // Chart source: DB for signed-in seekers (works across devices), local otherwise.
      const chartSessions = await getMeditationSessionsFromDb();
      if (!cancelled) setSessions(chartSessions);
      let memories: GuruMemory[] = [];
      try {
        const list = await memoryApi.list(1, 50);
        memories = list.memories;
      } catch {
        // Memory layer not available yet — degrade gracefully.
      }
      if (!cancelled) {
        setPersonalInsights(derivePersonalInsights({ sessions: localSessions, memories }));
      }
    };
    refresh();
    const onMed = () => { refresh(); };
    window.addEventListener('askmukthiguru:meditation_completed', onMed);
    const onVis = () => { if (document.visibilityState === 'visible') refresh(); };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelled = true;
      window.removeEventListener('askmukthiguru:meditation_completed', onMed);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [profile.updatedAt]);

  const patch = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  };

  const handleSave = () => {
    update({
      displayName: form.displayName.trim().slice(0, 40) || 'Seeker',
      bio: form.bio.slice(0, 280),
      preferredLanguage: form.preferredLanguage,
      guruTone: form.guruTone,
      familiarityLevel: form.familiarityLevel || 'seeker',
      theme: form.theme,
      ttsEnabled: form.ttsEnabled,
      voiceAutoplay: form.voiceAutoplay,
      ttsRate: form.ttsRate,
      preferredVoice: normalizeVoice(form.preferredVoice),
      meditationReminders: form.meditationReminders,
      reminderTimeMinutes: form.reminderTimeMinutes,
    });
    setDirty(false);
    toast({ title: 'Profile saved', description: 'Your preferences are updated.' });
  };

  // Sync conversation list for profile UI
  useEffect(() => {
    let cancelled = false;
    const reload = async () => {
      const convs = await loadConversations();
      if (!cancelled) {
        setConversations(convs);
        setConversationCount(convs.length);
      }
    };
    reload();
    window.addEventListener('storage', reload);
    window.addEventListener('conversation:updated', reload);
    return () => {
      cancelled = true;
      window.removeEventListener('storage', reload);
      window.removeEventListener('conversation:updated', reload);
    };
  }, []);

  const handleAvatarPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const dataUrl = await readAvatarFile(file);
      update({ avatarDataUrl: dataUrl });
      toast({ title: 'Avatar updated' });
    } catch (err) {
      toast({
        title: 'Could not set avatar',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    } finally {
      e.target.value = '';
    }
  };

  const handleRemoveAvatar = () => {
    update({ avatarDataUrl: null });
  };

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(exportAllData(), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `askmukthiguru-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: 'Exported', description: 'Your data was downloaded.' });
  };

  const handleDeleteEverything = async () => {
    deleteAllData();
    resetProfile();
    clearResponsePreferences();
    try {
      await memoryApi.deleteAll();
    } catch (e) {
      // Local reset already succeeded; surface the server-side failure separately rather than
      // rolling back what already worked.
      toast({ title: 'Local data cleared, but memory erasure failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
      return;
    }
    toast({ title: 'All data cleared', description: 'A fresh profile was created and saved memories were erased.' });
  };

  const handleSupportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSupportLoading(true);
    setSupportSent(false);
    try {
      const { submitSupportForm } = await import('@/lib/supportApi');
      await submitSupportForm({
        name: supportForm.name,
        email: supportForm.email as string,
        subject: supportForm.subject,
        message: supportForm.message,
        category: supportForm.category,
      });
      setSupportSent(true);
      setSupportForm({
        name: resolveName(),
        email: resolveEmail(),
        subject: '',
        message: '',
        category: 'Feedback'
      });
      toast({ title: 'Message sent', description: 'We will get back to you within 24-48 hours.' });
    } catch (err) {
      toast({ title: 'Failed to send', description: err instanceof Error ? err.message : 'Please try again.', variant: 'destructive' });
    } finally {
      setSupportLoading(false);
    }
  };


  const supportCategories = ['Feedback', 'Bug Report', 'Feature Request', 'Other'];


  const isOnboarding = searchParams.get('onboarding') === 'true';
  const setupMfaRedirect = searchParams.get('setup_mfa') === '1' ? searchParams.get('redirect') : null;

  if (authLoading) {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 text-ojas animate-spin" />
      </div>
    );
  }

  return (
    <AppShell title={isOnboarding ? "Welcome, Seeker" : "My Profile"}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6 safe-x">
        {/* ── Profile hero: avatar, name, email, streak — calm, flat, generous ── */}
        {!isOnboarding && (
          <div className="rounded-2xl border border-hairline bg-card p-5 sm:p-6 shadow-sm flex flex-col sm:flex-row items-center sm:items-start gap-4 sm:gap-6">
            <div className="relative shrink-0">
              <Avatar className="w-20 h-20 sm:w-24 sm:h-24 ring-1 ring-border relative">
                {(profile.avatarDataUrl || profile.avatarUrl) ? (
                  <AvatarImage src={profile.avatarDataUrl ?? profile.avatarUrl ?? ''} />
                ) : null}
                <AvatarFallback className="bg-muted text-foreground text-2xl font-serif font-semibold">
                  {getInitials(profile.displayName)}
                </AvatarFallback>
              </Avatar>
              <button
                onClick={() => fileInputRef.current?.click()}
                aria-label="Change profile photo"
                className="absolute bottom-0 right-0 min-w-[44px] min-h-[44px] flex items-center justify-center p-2.5 rounded-full bg-ojas text-primary-foreground shadow-sm hover:bg-ojas-light transition-all"
              >
                <Camera className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 min-w-0 text-center sm:text-left space-y-2">
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2.5">
                <h1 className="text-2xl sm:text-3xl font-serif font-semibold text-foreground tracking-tight truncate">
                  {profile.displayName || 'Seeker'}
                </h1>
                <Badge variant="outline" className="bg-ojas/10 text-ojas border-hairline capitalize text-xs px-2.5 py-0.5">
                  <Sparkles className="w-3 h-3 mr-1 text-ojas" />
                  {profile.familiarityLevel || 'Seeker'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground truncate">
                {user?.email ?? 'Your sacred journey with Sri Preethaji & Sri Krishnaji'}
              </p>
              <div className="flex flex-wrap items-center justify-center sm:justify-start gap-3 pt-1">
                {stats && stats.streakDays > 0 && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-ojas/10 border border-hairline text-xs text-ojas font-medium">
                    <Flame className="w-3.5 h-3.5" />
                    <span>{stats.streakDays}-day streak</span>
                  </div>
                )}
                {stats && stats.totalMinutes > 0 && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-card border border-hairline text-xs text-muted-foreground font-medium">
                    <Clock className="w-3.5 h-3.5 text-ojas" />
                    <span>{stats.totalMinutes} min practiced</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="space-y-6">
          <Tabs value={tab} onValueChange={setTab} className="w-full">
            {/* ── Scrollable tab rail — generous touch targets and sacred minimal background ── */}
            <div className="-mx-4 sm:mx-0 px-4 sm:px-0 overflow-x-auto momentum-scroll no-tap-highlight">
              <TabsList className="inline-flex w-max sm:w-full sm:grid sm:grid-cols-7 gap-1.5 mb-8 bg-muted/50 ring-1 ring-border/30 p-1.5 rounded-full">
                <TabsTrigger value="conversations" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.conversations', 'Conversations')}</TabsTrigger>
                <TabsTrigger value="profile" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.profile', 'Profile')}</TabsTrigger>
                <TabsTrigger value="stats" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.insights', 'Insights')}</TabsTrigger>
                <TabsTrigger value="notes" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.notes', 'Notes')}</TabsTrigger>
                <TabsTrigger value="memory" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.memory', 'Memory')}</TabsTrigger>
                <TabsTrigger value="settings" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.settings', 'Settings')}</TabsTrigger>
                <TabsTrigger value="support" className="rounded-full min-h-[44px] text-xs sm:text-sm px-4 sm:px-5 py-2.5 data-[state=active]:bg-card data-[state=active]:text-foreground data-[state=active]:shadow-sm data-[state=active]:font-medium text-muted-foreground hover:text-foreground transition-all duration-200">{t('profile.tabs.support', 'Support')}</TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="profile" className="space-y-6 mt-0">
              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Personal Details</CardTitle>
                  <CardDescription>Tell the Guru about yourself and your spiritual focus.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6 p-5 sm:p-7">
                  <div className="space-y-3">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={handleAvatarPick}
                    />
                    <div className="space-y-1.5">
                      <Label htmlFor="displayName" className="text-sm font-medium">Display Name</Label>
                      <Input
                        id="displayName"
                        value={form.displayName}
                        onChange={(e) => patch('displayName', e.target.value)}
                        placeholder="How should I address you?"
                        maxLength={40}
                        className="min-h-[44px] rounded-xl"
                      />
                    </div>
                    {profile.avatarDataUrl && (
                      <Button variant="ghost" size="sm" onClick={handleRemoveAvatar} className="text-destructive hover:text-destructive hover:bg-destructive/10 text-xs min-h-[36px] px-2.5 rounded-lg">
                        <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Remove photo
                      </Button>
                    )}
                  </div>


                  <div className="space-y-2">
                    <Label htmlFor="bio" className="text-sm font-medium">Your Path & Intention</Label>
                    <Textarea
                      id="bio"
                      value={form.bio}
                      onChange={(e) => patch('bio', e.target.value)}
                      placeholder="Share what brings you here or your current spiritual challenges..."
                      className="min-h-[120px] resize-none rounded-xl"
                      maxLength={280}
                    />
                    <p className="text-xs text-muted-foreground text-right">
                      {form.bio.length}/280 characters
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-ojas" />
                        Preferred Language
                      </Label>
                      <Select value={form.preferredLanguage} onValueChange={(v) => patch('preferredLanguage', v)}>
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="max-h-80">
                          {LANGUAGES.map(l => (
                            <SelectItem key={l.code} value={l.code}>
                              {l.native} ({l.name})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Guru's Tone</Label>
                      <Select value={form.guruTone} onValueChange={(v) => patch('guruTone', v as GuruTone)}>
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {tones.map(t => (
                            <SelectItem key={t.value} value={t.value}>
                              <span className="font-medium">{t.label}</span>
                              <span className="ml-2 text-xs text-muted-foreground">{t.hint}</span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Guidance Depth</Label>
                      <Select
                        value={form.familiarityLevel || 'seeker'}
                        onValueChange={(v) => patch('familiarityLevel', v as 'seeker' | 'practitioner' | 'advanced')}
                      >
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="seeker">
                            <span className="font-medium">Seeker</span>
                            <span className="ml-2 text-xs text-muted-foreground">Clear Sanskrit explanations</span>
                          </SelectItem>
                          <SelectItem value="practitioner">
                            <span className="font-medium">Practitioner</span>
                            <span className="ml-2 text-xs text-muted-foreground">Balanced meditation guidance</span>
                          </SelectItem>
                          <SelectItem value="advanced">
                            <span className="font-medium">Advanced</span>
                            <span className="ml-2 text-xs text-muted-foreground">Deep philosophical terms</span>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div
                    data-testid="guidance-preview"
                    aria-live="polite"
                    className="rounded-2xl border border-hairline bg-muted/30 px-4 py-3.5"
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      <Sparkles className="h-4 w-4 text-ojas" aria-hidden="true" />
                      Your guidance preview
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                      {form.guruTone === 'direct'
                        ? 'Clear, concise guidance that comes to the practical next step quickly.'
                        : form.guruTone === 'poetic'
                          ? 'Reflective language with imagery, while keeping the teaching clear and useful.'
                          : 'Warm, steady guidance that makes room for your experience before offering a next step.'}
                      {' '}
                      {form.familiarityLevel === 'advanced'
                        ? 'It can use deeper philosophical terms when the teaching supports them.'
                        : form.familiarityLevel === 'practitioner'
                          ? 'It balances a teaching with a practical reflection or meditation cue.'
                          : 'It explains spiritual terms plainly before building on them.'}
                    </p>
                    <p className="mt-2 text-xs text-ojas/90">
                      Source-aware by design: verified quotations remain attributed; unsupported questions receive a clear limit or clarification.
                    </p>
                  </div>
                </CardContent>
              </Card>

              <div className="flex items-center justify-between gap-4 sticky bottom-[calc(1rem+env(safe-area-inset-bottom,0px))] z-20 bg-card/90 backdrop-blur-md p-3 sm:p-4 rounded-2xl border border-hairline shadow-md">
                <div className="hidden sm:block">
                  {dirty ? (
                    <p className="text-xs text-ojas font-medium flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-ojas inline-block" />
                      Unsaved changes
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">All profile details are up to date</p>
                  )}
                </div>
                <Button
                  onClick={handleSave}
                  disabled={!dirty}
                  className="w-full sm:w-auto min-h-[44px] h-11 px-8 bg-ojas hover:bg-ojas-light text-primary-foreground shadow-sm gap-2 font-medium rounded-xl"
                >
                  <Save className="w-4 h-4" />
                  {isOnboarding ? "Complete Onboarding" : "Save Changes"}
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="stats" className="space-y-6 mt-0">
              <ProfileStatTiles stats={stats} sessions={sessions} />

              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Journey Overview</CardTitle>
                  <CardDescription>Your path across conversations, practice, and healing.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {metricsLoading && !metrics && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="rounded-2xl border border-hairline bg-card px-4 py-3.5 animate-pulse">
                          <div className="h-2.5 w-16 rounded-full bg-muted mb-3" />
                          <div className="h-5 w-12 rounded-full bg-muted" />
                        </div>
                      ))}
                    </div>
                  )}
                  {!metricsLoading && metricsError && !metrics && (
                    <p className="text-xs text-muted-foreground">
                      Couldn't load journey metrics right now. They'll reappear once the Guru's memory is awake.
                    </p>
                  )}
                  {metrics && (
                    <>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div className="rounded-2xl border border-hairline bg-card px-4 py-3.5 flex flex-col gap-1">
                          <div className="flex items-center gap-1.5 text-muted-foreground">
                            <Flame className="w-3.5 h-3.5" />
                            <span className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">Conversations</span>
                          </div>
                          <p className="text-2xl font-serif font-semibold text-foreground tabular-nums leading-none mt-1">
                            {metrics.totalConversations}
                          </p>
                        </div>
                        <div className="rounded-2xl border border-hairline bg-card px-4 py-3.5 flex flex-col gap-1">
                          <div className="flex items-center gap-1.5 text-muted-foreground">
                            <MessageCircle className="w-3.5 h-3.5" />
                            <span className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">Messages</span>
                          </div>
                          <p className="text-2xl font-serif font-semibold text-foreground tabular-nums leading-none mt-1">
                            {metrics.totalMessages}
                          </p>
                        </div>
                        <div className="rounded-2xl border border-hairline bg-card px-4 py-3.5 flex flex-col gap-1">
                          <div className="flex items-center gap-1.5 text-muted-foreground">
                            <Clock className="w-3.5 h-3.5" />
                            <span className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">Meditation</span>
                          </div>
                          <p className="text-2xl font-serif font-semibold text-foreground tabular-nums leading-none mt-1">
                            {Math.round(metrics.totalMeditationMinutes)}m
                          </p>
                        </div>
                        <div className="rounded-2xl border border-hairline bg-card px-4 py-3.5 flex flex-col gap-1">
                          <div className="flex items-center gap-1.5 text-muted-foreground">
                            <Target className="w-3.5 h-3.5" />
                            <span className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">Course progress</span>
                          </div>
                          <p className="text-2xl font-serif font-semibold text-foreground tabular-nums leading-none mt-1">
                            {metrics.courseCompletionPercent}%
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                          <Heart className="w-3.5 h-3.5 text-ojas" />
                          {metrics.activeHealingCourse ?? 'No active healing course'}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <TrendingUp className="w-3.5 h-3.5" />
                          Distress {metrics.averageDistressLevel ?? '—'} · {metrics.distressTrend}
                        </span>
                        {metrics.lastActiveAt && (
                          <span className="flex items-center gap-1.5">
                            <Sparkles className="w-3.5 h-3.5" />
                            Last active {formatRelativeTime(new Date(metrics.lastActiveAt))}
                          </span>
                        )}
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Wisdom of the Day */}
              {dailyTeaching && (
                <Card className="overflow-hidden rounded-2xl border border-hairline bg-card shadow-sm">
                  <div className="flex flex-col sm:flex-row">
                    <div className="relative w-full sm:w-1/3 aspect-[16/10] sm:aspect-auto sm:min-h-[160px] overflow-hidden bg-muted/20">
                      <img
                        src={dailyTeaching.image_url}
                        alt="Daily wisdom"
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-gradient-to-t sm:bg-gradient-to-r from-card/70 via-transparent to-transparent pointer-events-none" />
                    </div>
                    <div className="flex-1 p-5 flex flex-col justify-center">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Sparkles className="w-3.5 h-3.5 text-ojas" />
                        <span className="text-[10px] font-semibold text-ojas uppercase tracking-[0.14em]">
                          Wisdom of the Day
                        </span>
                      </div>
                      {dailyTeaching.caption && (
                        <p className="text-base text-foreground/90 font-serif leading-relaxed italic">
                          &ldquo;{dailyTeaching.caption}&rdquo;
                        </p>
                      )}
                    </div>
                  </div>
                </Card>
              )}

              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Recent Insights</CardTitle>
                  <CardDescription>Patterns woven from your practice, mood, and conversations.</CardDescription>
                </CardHeader>
                <CardContent>
                  {personalInsights.length > 0 ? (
                    <div className="space-y-3">
                      {personalInsights.map((insight, idx) => (
                        <div
                          key={`${insight.kind}-${idx}`}
                          className="p-4 rounded-xl bg-muted/30 border border-hairline flex gap-3"
                        >
                          <Sparkles className="w-4 h-4 text-ojas shrink-0 mt-0.5" />
                          <p className="text-sm text-foreground/90 italic leading-relaxed">
                            {insight.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 space-y-2">
                      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
                        <Target className="w-6 h-6" />
                      </div>
                      <p className="text-sm text-muted-foreground">No insights yet. Continue your practices to reveal your spiritual patterns.</p>
                      <Button variant="outline" size="sm" onClick={() => navigate('/practices')} className="mt-2 rounded-xl border-hairline">
                        Start a practice <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="notes" className="space-y-6 mt-0">
              <NotesPanel />
            </TabsContent>

            <TabsContent value="conversations" className="space-y-6 mt-0">
              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Conversations</CardTitle>
                  <CardDescription>Manage and prune your chat history.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* ── Days-based retention control ─────────────────────── */}
                  <div className="space-y-3">
                    <Label className="text-sm font-medium">Keep conversations for</Label>
                    <div className="flex items-center gap-3">
                      <Input
                        type="number"
                        min={1}
                        max={365}
                        value={retentionDays}
                        onChange={e => setRetentionDays_(Math.max(1, Math.min(365, parseInt(e.target.value) || 90)))}
                        className="w-20 rounded-xl"
                      />
                      <span className="text-sm text-muted-foreground">days</span>
                    </div>
                    {/* Quick-select day presets */}
                    <div className="flex flex-wrap gap-2">
                      {[7, 30, 90, 180, 365].map(d => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => setRetentionDays_(d)}
                          className={`px-3 py-1 rounded-full text-xs font-medium border border-hairline transition-colors ${
                            retentionDays === d
                              ? 'bg-ojas/20 border-ojas text-ojas'
                              : 'text-muted-foreground hover:border-ojas/50'
                          }`}
                        >
                          {d === 365 ? '1 yr' : `${d}d`}
                        </button>
                      ))}
                    </div>
                    <Slider
                      value={[retentionDays]}
                      min={1}
                      max={365}
                      step={1}
                      onValueChange={([v]) => setRetentionDays_(Math.max(1, Math.min(365, v)))}
                    />
                    <Button
                      className="rounded-xl"
                      onClick={async () => {
                        saveRetentionDays(retentionDays);
                        setConversations(await loadConversations());
                        toast({ title: `Retention set to ${retentionDays} days` });
                      }}
                    >
                      Save retention
                    </Button>
                  </div>

                  {conversations.length === 0 ? (
                    <p className="text-muted-foreground">No conversations.</p>
                  ) : (
                    <ul className="space-y-2">
                      {conversations.map(conv => (
                        <li key={conv.id} className="flex items-center justify-between p-3 border border-hairline rounded-xl bg-card hover:bg-muted/20 transition-colors">
                          <div className="flex-1 min-w-0 pr-3">
                            <p className="font-medium truncate">{conv.preview || 'Untitled'}</p>
                            <p className="text-xs text-muted-foreground">{formatRelativeTime(conv.updatedAt)}</p>
                          </div>
                          <Button variant="ghost" size="sm" onClick={async () => { await deleteConversation(conv.id); setConversations(prev => prev.filter(c => c.id !== conv.id)); setConversationCount(prev => Math.max(0, prev - 1)); }} aria-label={`Delete conversation: ${conv.preview || 'Untitled'}`} className="rounded-lg">
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}

                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="destructive" className="mt-4 rounded-xl">Delete all conversations</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent className="rounded-2xl">
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete all conversations?</AlertDialogTitle>
                        <AlertDialogDescription>
                          Type <code>DELETE</code> to confirm. This action cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <div className="py-2">
                        <Input value={deleteAllConfirm} onChange={e => setDeleteAllConfirm(e.target.value)} placeholder="Type DELETE to confirm" className="rounded-xl" />
                      </div>
                      <AlertDialogFooter>
                        <AlertDialogCancel onClick={() => setDeleteAllConfirm('')} className="rounded-xl">Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={async () => {
                          if (deleteAllConfirm.trim().toUpperCase() === 'DELETE') {
                            const currentId = await getCurrentConversationId();
                            const toDelete = conversations.filter(c => c.id !== currentId);
                            for (const c of toDelete) {
                              await deleteConversation(c.id);
                            }
                            setConversations(prev => prev.filter(c => c.id === currentId));
                            setConversationCount(prev => Math.max(0, prev - toDelete.length));
                            setDeleteAllConfirm('');
                            toast({ title: 'All conversations deleted' });
                          }
                        }} disabled={deleteAllConfirm.trim().toUpperCase() !== 'DELETE'} className="rounded-xl">Confirm</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="memory" className="space-y-6 mt-0">
              <MemoryManager />
            </TabsContent>


            <TabsContent value="settings" className="space-y-6 mt-0">
              {setupMfaRedirect && (
                <Alert className="rounded-2xl border border-hairline">
                  <AlertDescription>
                    Admin access requires two-factor authentication. Set it up below, then you'll be sent back automatically.
                  </AlertDescription>
                </Alert>
              )}
              <TwoFactorSettings
                onEnrolled={setupMfaRedirect ? () => navigate(setupMfaRedirect, { replace: true }) : undefined}
              />
              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Appearance</CardTitle>
                  <CardDescription>Customize the interface theme.</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-3">
                    {themes.map(t => (
                      <button
                        key={t.value}
                        onClick={() => {
                          patch('theme', t.value);
                          applyThemeNow(t.value);
                        }}
                        className={cn(
                          "flex flex-col items-center gap-2 p-3 rounded-xl border border-hairline transition-all min-h-[44px]",
                          form.theme === t.value
                            ? "bg-ojas/5 border-ojas text-ojas ring-1 ring-ojas/30"
                            : "bg-card hover:bg-muted/30 text-muted-foreground hover:text-foreground"
                        )}
                      >
                        <t.icon className="w-5 h-5" />
                        <span className="text-xs font-medium">{t.label}</span>
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Voice & Audio</CardTitle>
                  <CardDescription>Configure Text-to-Speech playback.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <Label>Enable Guru Voice</Label>
                      <p className="text-xs text-muted-foreground">Read teachings aloud automatically</p>
                    </div>
                    <Switch
                      checked={form.ttsEnabled}
                      onCheckedChange={(v) => patch('ttsEnabled', v)}
                    />
                  </div>

                  {form.ttsEnabled && (
                    <div className="space-y-4 pt-2">
                      <div className="flex items-center justify-between gap-4">
                        <div className="space-y-0.5">
                          <Label>Auto-play Guru Responses</Label>
                          <p className="text-xs text-muted-foreground">Read each teaching aloud as it arrives</p>
                        </div>
                        <Switch
                          checked={form.voiceAutoplay ?? false}
                          onCheckedChange={(v) => patch('voiceAutoplay', v)}
                        />
                      </div>

                      <div className="flex justify-between text-xs text-muted-foreground">
                        <Label>Speech Rate</Label>
                        <span>{form.ttsRate}x</span>
                      </div>
                      <Slider
                        value={[form.ttsRate]}
                        min={0.5}
                        max={1.5}
                        step={0.1}
                        onValueChange={([v]) => patch('ttsRate', v)}
                      />

                      <div className="space-y-2 pt-2">
                        <Label>Guru Voice (Mayura)</Label>
                        <p className="text-xs text-muted-foreground">Choose the voice personality for Indic language audio.</p>
                        <Select value={normalizeVoice(form.preferredVoice)} onValueChange={(v) => patch('preferredVoice', v)}>
                          <SelectTrigger className="rounded-xl min-h-[44px]">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {voiceOptions.map(v => (
                              <SelectItem key={v.value} value={v.value}>
                                <span className="font-medium">{v.label}</span>
                                <span className="ml-2 text-xs text-muted-foreground">{v.hint}</span>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Reminders</CardTitle>
                  <CardDescription>Stay consistent with your spiritual goals.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex items-center justify-between gap-4">
                    <div className="space-y-0.5">
                      <Label className="flex items-center gap-2">
                        Meditation Reminders
                        {form.meditationReminders ? <BellRing className="w-3.5 h-3.5 text-ojas" /> : <Bell className="w-3.5 h-3.5" />}
                      </Label>
                      <p className="text-xs text-muted-foreground">Daily notification to find your center</p>
                    </div>
                    <Switch
                      checked={form.meditationReminders}
                      onCheckedChange={async (v) => {
                        if (v) {
                          const ok = await requestNotificationPermission();
                          if (!ok) {
                            toast({
                              title: "Permissions required",
                              description: "Please enable notifications in your browser settings to use reminders.",
                              variant: "destructive"
                            });
                            return;
                          }
                        }
                        patch('meditationReminders', v);
                      }}
                    />
                  </div>

                  {form.meditationReminders && (
                    <div className="space-y-4 pt-2">
                      <div className="flex justify-between items-center">
                        <Label className="text-xs text-muted-foreground uppercase tracking-wider">Scheduled for</Label>
                        <Badge variant="outline" className="text-ojas border-hairline bg-ojas/5">
                          {formatTime(form.reminderTimeMinutes)}
                        </Badge>
                      </div>
                      <Slider
                        value={[form.reminderTimeMinutes]}
                        min={0}
                        max={1439}
                        step={15}
                        onValueChange={([v]) => patch('reminderTimeMinutes', v)}
                      />
                      <div className="flex justify-end pt-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-8 text-[11px] gap-2 rounded-xl border-hairline"
                          onClick={() => fireTestReminder(toast)}
                        >
                          <Bell className="w-3.5 h-3.5" /> Send test reminder
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Demarcated Account & Data Section */}
              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="text-lg font-serif font-semibold text-foreground">Account & Data</CardTitle>
                  <CardDescription>Export your data, clear local history, or delete your account.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <h4 className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">Export Data</h4>
                    <div className="flex flex-col sm:flex-row gap-3">
                      <Button variant="outline" className="flex-1 gap-2 rounded-xl min-h-[44px] border-hairline" onClick={handleExport}>
                        <Download className="w-4 h-4" /> Export Local Data
                      </Button>
                      <Button
                        variant="outline"
                        className="flex-1 gap-2 rounded-xl min-h-[44px] border-hairline"
                        onClick={async () => {
                          try {
                            const { data: { session } } = await supabase.auth.getSession();
                            if (!session) return toast({ title: 'Sign in first', variant: 'destructive' });
                            const { data, error } = await supabase.functions.invoke('export-my-data');
                            if (error) throw error;
                            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `askmukthiguru-cloud-export-${new Date().toISOString().slice(0, 10)}.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                            toast({ title: 'Cloud data exported' });
                          } catch (e) {
                            toast({ title: 'Export failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
                          }
                        }}
                      >
                        <Download className="w-4 h-4" /> Export Cloud Data
                      </Button>
                    </div>
                  </div>

                  <div className="pt-4 border-t border-hairline space-y-3">
                    <h4 className="text-[10px] uppercase tracking-[0.14em] font-medium text-destructive/80">Danger Zone</h4>
                    <div className="flex flex-col sm:flex-row gap-3">
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button variant="outline" className="flex-1 gap-2 rounded-xl min-h-[44px] border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive">
                            <Trash2 className="w-4 h-4" /> Clear Local Data
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent className="rounded-2xl">
                          <AlertDialogHeader>
                            <AlertDialogTitle>Clear local data?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Erases this device's profile, chat history, meditation stats, response
                              preferences, and your saved memories. Your account remains. This cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel className="rounded-xl">Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={handleDeleteEverything} className="bg-destructive hover:bg-destructive/90 rounded-xl">
                              Clear
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>

                      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
                        <DialogTrigger asChild>
                          <Button variant="destructive" className="flex-1 gap-2 rounded-xl min-h-[44px]">
                            <Trash2 className="w-4 h-4" /> Delete Account
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="max-w-md rounded-2xl">
                          <DialogHeader>
                            <DialogTitle>{t('cancelFlow.dialogTitle', 'Cancel your account')}</DialogTitle>
                            <DialogDescription>
                              {t('cancelFlow.dialogDescription', 'A short retention flow before we say goodbye.')}
                            </DialogDescription>
                          </DialogHeader>
                          {cancelOpen && (
                            <CancelFlow
                              onComplete={async ({ saved, retention }) => {
                                setCancelOpen(false);
                                if (saved) {
                                  toast({ title: 'Offer applied', description: 'Glad you are staying.' });
                                  return;
                                }
                                if (retention === 'delete_immediately') {
                                  try {
                                    const { error } = await supabase.functions.invoke('delete-my-account', { method: 'POST' });
                                    if (error) throw error;
                                    await clearLocalChatData();
                                    deleteAllData();
                                    resetProfile();
                                    await supabase.auth.signOut();
                                    toast({ title: 'Account deleted' });
                                    navigate('/', { replace: true });
                                  } catch (e) {
                                    toast({ title: 'Sign-out failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
                                  }
                                } else {
                                  try {
                                    await supabase.auth.signOut();
                                    toast({
                                      title: 'Deletion scheduled',
                                      description: 'Your account is scheduled for deletion. You can reactivate anytime before the deletion date.',
                                    });
                                    navigate('/', { replace: true });
                                  } catch (e) {
                                    toast({ title: 'Sign-out failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
                                  }
                                }
                              }}
                              onClose={() => setCancelOpen(false)}
                            />
                          )}
                        </DialogContent>
                      </Dialog>
                    </div>

                    <p className="text-[11px] text-muted-foreground pt-1">
                      Need help debugging access?{' '}
                      <a href="/auth/diagnostics" className="text-ojas hover:underline">
                        Open auth diagnostics
                      </a>
                    </p>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="support" className="space-y-6 mt-0">
              <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
                <CardHeader className="pb-4">
                  <div className="flex items-center gap-3">
                    <Mail className="h-5 w-5 text-ojas" />
                    <div>
                      <CardTitle className="text-lg font-serif font-semibold text-foreground">Contact Support</CardTitle>
                      <CardDescription>
                        Have a question, feedback, or run into an issue? We are here to help.
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  {supportSent ? (
                    <div className="flex flex-col items-center justify-center py-8 text-center space-y-3">
                      <CheckCircle2 className="h-12 w-12 text-prana" />
                      <p className="text-lg font-medium font-serif">Message sent!</p>
                      <p className="text-sm text-muted-foreground max-w-sm">
                        We will get back to you within 24&ndash;48 hours. For urgent matters, please include &quot;URGENT&quot; in your subject line.
                      </p>
                      <Button variant="outline" className="mt-4 rounded-xl border-hairline" onClick={() => setSupportSent(false)}>
                        Send another message
                      </Button>
                    </div>
                  ) : (
                    <form onSubmit={handleSupportSubmit} className="space-y-4">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <Label htmlFor="s-name">Name <span className="text-muted-foreground">(optional)</span></Label>
                          <Input id="s-name" value={supportForm.name} onChange={e => setSupportForm(p => ({ ...p, name: e.target.value }))} placeholder="Your name" disabled={!!resolveName()} className="min-h-[44px] rounded-xl" />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="s-email">Your Email <span className="text-destructive">*</span></Label>
                          <Input id="s-email" type="email" value={supportForm.email} onChange={e => setSupportForm(p => ({ ...p, email: e.target.value }))} placeholder="you@example.com" required disabled={!!resolveEmail()} className="min-h-[44px] rounded-xl" />
                        </div>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="space-y-1.5">
                          <Label htmlFor="s-category">Category</Label>
                          <select id="s-category" value={supportForm.category} onChange={e => setSupportForm(p => ({ ...p, category: e.target.value }))} className="flex min-h-[44px] h-11 w-full rounded-xl border border-hairline bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                            {supportCategories.map(c => <option key={c} value={c}>{c}</option>)}
                          </select>
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="s-subject">Subject <span className="text-destructive">*</span></Label>
                          <Input id="s-subject" value={supportForm.subject} onChange={e => setSupportForm(p => ({ ...p, subject: e.target.value }))} placeholder="Brief summary" required className="min-h-[44px] rounded-xl" />
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <Label htmlFor="s-message">Message <span className="text-destructive">*</span></Label>
                        <Textarea id="s-message" value={supportForm.message} onChange={e => setSupportForm(p => ({ ...p, message: e.target.value }))} placeholder="Describe your issue, feedback, or request in detail. Include what you were doing, what you expected, and what happened." className="min-h-[140px] resize-none rounded-xl" required />
                      </div>

                      <div className="bg-muted/30 border border-hairline rounded-xl p-4 space-y-2">
                        <h4 className="text-sm font-medium flex items-center gap-2">
                          <Bug className="h-4 w-4 text-ojas" />
                          Before reaching out
                        </h4>
                        <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
                          <li>Make sure you are on the latest version (refresh the page).</li>
                          <li>Check your internet connection and try again.</li>
                          <li>If the Guru is not responding, the backend may be temporarily busy.</li>
                        </ul>
                      </div>

                      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
                        <p className="text-xs text-muted-foreground">
                          Or email us directly at <a href="mailto:kharshaengineer@gmail.com" className="underline hover:text-foreground">kharshaengineer@gmail.com</a>
                        </p>
                        <Button type="submit" disabled={supportLoading} className="w-full sm:w-auto min-h-[44px] rounded-xl bg-ojas hover:bg-ojas-light text-primary-foreground">
                          {supportLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Mail className="h-4 w-4 mr-1" />}
                          {supportLoading ? 'Sending...' : 'Send Message'}
                        </Button>
                      </div>
                    </form>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </AppShell>
  );
};

export default ProfilePage;
