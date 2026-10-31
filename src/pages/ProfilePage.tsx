import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import {
  Camera,
  Trash2,
  Save,
  Loader2,
  Globe,
  Compass,
  SlidersHorizontal,
  BookOpen,
  Brain,
  Settings,
} from 'lucide-react';
import { profileTabParams } from '@/lib/workspaceNavigation';
import { usePageMeta } from '@/hooks/usePageMeta';
import { buildCanonical } from '@/lib/domain';
import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useProfile } from '@/hooks/useProfile';
import {
  GuruTone,
  readAvatarFile,
  getInitials,
} from '@/lib/profileStorage';
import {
  getMeditationStats,
  getMeditationStatsFromDb,
  getMeditationSessionsFromDb,
  loadMeditationSessions,
  toNormalized,
  type MeditationStats,
} from '@/lib/meditationStorage';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { loadConversations, type Conversation } from '@/lib/chatStorage';
import { derivePersonalInsights, type PersonalInsight } from '@/lib/personalInsights';
import { memoryApi, type GuruMemory } from '@/lib/memoryApi';
import { NotesPanel } from '@/components/profile/NotesPanel';
import { MemoryManager } from '@/components/profile/MemoryManager';
import { JourneyOverview } from '@/components/profile/JourneyOverview';
import { PreferencesCard } from '@/components/profile/settings/PreferencesCard';
import { SecurityCard } from '@/components/profile/settings/SecurityCard';
import { AccountDataCard } from '@/components/profile/settings/AccountDataCard';
import { SupportCard } from '@/components/profile/settings/SupportCard';
import { useToast } from '@/hooks/use-toast';
import { useTheme } from '@/hooks/useTheme';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { useMetrics } from '@/hooks/useMetrics';
import { LANGUAGES } from '@/components/chat/LanguageSelector';
import { useTranslation } from 'react-i18next';
import { changeUiLanguage } from '@/i18n';

const formatLanguageOption = (l: { code: string; native: string; name: string }) => {
  if (l.native.toLowerCase() === 'english') {
    return l.name;
  }
  if (l.name.toLowerCase().startsWith(l.native.toLowerCase())) {
    return l.name;
  }
  return `${l.native} (${l.name})`;
};

const tones: { value: GuruTone; label: string; hint: string }[] = [
  { value: 'gentle', label: 'Gentle', hint: 'Soft, nurturing replies' },
  { value: 'direct', label: 'Direct', hint: 'Clear, concise teachings' },
  { value: 'poetic', label: 'Poetic', hint: 'Lyrical, metaphor-rich' },
];

const ProfilePage = () => {
  const reduceMotion = useReducedMotion();
  const { loading: authLoading, user } = useRequireAuth();
  usePageMeta({
    title: 'Your Profile — AskMukthiGuru',
    description: 'Manage your seeker profile, preferred guru tone, language, theme, and meditation reminder settings.',
    canonical: buildCanonical('/profile'),
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const tabParam = searchParams.get('tab');
  const isOnboarding = searchParams.get('onboarding') === 'true';
  const PROFILE_TABS = ['journey', 'profile', 'memory', 'settings'] as const;
  type ProfileTab = typeof PROFILE_TABS[number];
  const normalizedTab = tabParam === 'stats' || tabParam === 'conversations' ? 'journey' : tabParam;
  const initialTab: ProfileTab = isOnboarding
    ? 'profile'
    : PROFILE_TABS.includes(normalizedTab as ProfileTab)
      ? (normalizedTab as ProfileTab)
      : 'journey';
  const tab = initialTab;
  const setTab = (next: ProfileTab) => {
    const params = profileTabParams(searchParams, next);
    setSearchParams(params, { replace: true });
  };
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
  const [memorySubTab, setMemorySubTab] = useState<'notes' | 'guru'>('notes');

  useEffect(() => {
    if (!dirty) setForm(profile);
  }, [profile, dirty]);

  const resolveName = useCallback((): string => {
    const raw = profile.displayName || user?.user_metadata?.full_name || '';
    return raw && raw !== 'Seeker' ? raw : '';
  }, [profile.displayName, user?.user_metadata?.full_name]);

  const resolveEmail = useCallback((): string => {
    return user?.email || '';
  }, [user?.email]);

  const [stats, setStats] = useState<MeditationStats>(() => getMeditationStats());
  const [sessions, setSessions] = useState<NormalizedSession[]>(() =>
    loadMeditationSessions().map(toNormalized),
  );
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [personalInsights, setPersonalInsights] = useState<PersonalInsight[]>([]);

  useEffect(() => {
    if (window.location.hash === '#security' && tab === 'settings') {
      const el = document.getElementById('security');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }, [tab]);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const dbStats = await getMeditationStatsFromDb();
      if (!cancelled) setStats(dbStats);
      const dbSessions = await getMeditationSessionsFromDb();
      if (!cancelled) setSessions(dbSessions);
      // Derive richer insights from local sessions + backend memory (if live).
      const localSessions = loadMeditationSessions();
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

  const handleSave = async () => {
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
      preferredVoice: form.preferredVoice,
      meditationReminders: form.meditationReminders,
      reminderTimeMinutes: form.reminderTimeMinutes,
    });
    setDirty(false);
    if (form.bio && form.bio.trim()) {
      try {
        await memoryApi.setCore(form.bio.trim());
      } catch (err) {
        // Fallback gracefully if backend memory API is offline
        console.warn('Could not sync core memory to backend:', err);
      }
    }
    toast({ title: t('profile.personalDetails.saved', 'Profile saved'), description: t('profile.personalDetails.savedOnDevice', 'Saved on this device.') });
    if (isOnboarding) navigate('/chat', { replace: true });
  };

  // Sync conversation list for profile UI
  useEffect(() => {
    let cancelled = false;
    const reload = async () => {
      const convs = await loadConversations();
      if (!cancelled) {
        setConversations(convs);
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
      toast({ title: t('profile.personalDetails.avatarUpdated', 'Avatar updated') });
    } catch (err) {
      toast({
        title: t('profile.personalDetails.avatarError', 'Could not set avatar'),
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

  const setupMfaRedirect = searchParams.get('setup_mfa') === '1' ? searchParams.get('redirect') : null;

  if (authLoading) {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-background" role="status" aria-label={t('common.loading', 'Loading…')}>
        <Loader2 className="w-6 h-6 text-ojas animate-spin" aria-hidden="true" />
        <span className="sr-only">{t('common.loading', 'Loading…')}</span>
      </div>
    );
  }

  return (
    <AppShell title={isOnboarding ? t('profile.page.welcome', 'Welcome, Seeker') : t('profile.page.title', 'My Profile')}>
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.2, 0.8, 0.2, 1] }}
        className="max-w-5xl mx-auto px-4 sm:px-8 py-6 sm:py-10 space-y-6 safe-x safe-bottom profile-focus-flow"
      >
        {/* ── Profile hero: avatar, name, email, streak — calm, flat, generous ── */}
        {!isOnboarding && (
          <section className="border-b border-hairline pb-6 sm:pb-8 flex items-center gap-5 sm:gap-6" aria-labelledby="profile-name">
            <div className="relative shrink-0">
              <Avatar className="w-16 h-16 sm:w-20 sm:h-20 ring-1 ring-ojas/20">
                {(profile.avatarDataUrl || profile.avatarUrl) ? (
                  <AvatarImage src={profile.avatarDataUrl ?? profile.avatarUrl ?? ''} />
                ) : (
                  <AvatarImage src="/images/ekam-golden-orb-lotus-square.png" alt="Ekam Golden Orb" />
                )}
                <AvatarFallback className="bg-ojas/10 text-ojas text-xl font-semibold">
                  {getInitials(profile.displayName)}
                </AvatarFallback>
              </Avatar>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleAvatarPick}
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                aria-label={t('profile.personalDetails.changePhoto', 'Change profile photo')}
                className="absolute -bottom-1 -right-1 min-w-[44px] min-h-[44px] flex items-center justify-center rounded-full bg-card border border-hairline text-ojas shadow-sm hover:bg-ojas/10 transition-colors no-tap-highlight"
              >
                <Camera className="w-4 h-4" />
              </Button>
            </div>
            <div className="flex-1 min-w-0 text-left space-y-1.5">
              <p className="text-[11px] uppercase tracking-normal font-medium text-muted-foreground">
                {profile.familiarityLevel ? t(`profile.personalDetails.${profile.familiarityLevel}`, profile.familiarityLevel) : t('profile.personalDetails.seeker', 'Seeker')}
              </p>
              <h1 id="profile-name" className="text-xl sm:text-2xl font-semibold text-foreground tracking-normal leading-tight truncate">
                {resolveName() || t('profile.personalDetails.seeker', 'Seeker')}
              </h1>
              <p className="text-sm text-muted-foreground/80 truncate">
                {user?.email ?? 'Your sacred journey with Sri Preethaji & Sri Krishnaji'}
              </p>

            </div>
          </section>

        )}

        <div className="space-y-6">
          <Tabs
              value={tab}
              onValueChange={(value) => {
                if (PROFILE_TABS.includes(value as ProfileTab)) setTab(value as ProfileTab);
              }}
              className="w-full"
            >
            {/* Sacred floating tab dock */}
            <div className="sticky top-14 z-20 py-2 sm:py-3 bg-background/90 backdrop-blur-xl">
              <TabsList
                aria-label={t('layout.navigate', 'Navigate')}
                className="w-full max-w-2xl mx-auto grid grid-cols-4 gap-1 sm:gap-2 p-1.5 sm:p-2 h-auto min-h-[52px] sm:min-h-[56px] items-center bg-card/85 backdrop-blur-xl border border-hairline/80 rounded-2xl shadow-xs"
              >
                <TabsTrigger
                  value="journey"
                  className="group relative flex items-center justify-center gap-1.5 sm:gap-2 rounded-xl h-10 sm:h-11 px-2 sm:px-3 text-xs sm:text-sm font-medium text-muted-foreground/80 transition-all duration-200 hover:text-foreground hover:bg-muted/40 active:scale-[0.98] border border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:font-semibold data-[state=active]:border-ojas/30 data-[state=active]:shadow-xs"
                >
                  <Compass className="w-4 h-4 shrink-0 transition-colors group-data-[state=active]:text-ojas text-muted-foreground/60 group-hover:text-foreground" aria-hidden="true" />
                  <span className="truncate">{t('profile.tabs.journey', 'Journey')}</span>
                </TabsTrigger>
                <TabsTrigger
                  value="profile"
                  className="group relative flex items-center justify-center gap-1.5 sm:gap-2 rounded-xl h-10 sm:h-11 px-2 sm:px-3 text-xs sm:text-sm font-medium text-muted-foreground/80 transition-all duration-200 hover:text-foreground hover:bg-muted/40 active:scale-[0.98] border border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:font-semibold data-[state=active]:border-ojas/30 data-[state=active]:shadow-xs"
                >
                  <SlidersHorizontal className="w-4 h-4 shrink-0 transition-colors group-data-[state=active]:text-ojas text-muted-foreground/60 group-hover:text-foreground" aria-hidden="true" />
                  <span className="truncate">{t('profile.tabs.personalise', 'Personalise')}</span>
                </TabsTrigger>
                <TabsTrigger
                  value="memory"
                  className="group relative flex items-center justify-center gap-1.5 sm:gap-2 rounded-xl h-10 sm:h-11 px-2 sm:px-3 text-xs sm:text-sm font-medium text-muted-foreground/80 transition-all duration-200 hover:text-foreground hover:bg-muted/40 active:scale-[0.98] border border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:font-semibold data-[state=active]:border-ojas/30 data-[state=active]:shadow-xs"
                >
                  <BookOpen className="w-4 h-4 shrink-0 transition-colors group-data-[state=active]:text-ojas text-muted-foreground/60 group-hover:text-foreground" aria-hidden="true" />
                  <span className="truncate">{t('profile.tabs.memory', 'Memory')}</span>
                </TabsTrigger>
                <TabsTrigger
                  value="settings"
                  className="group relative flex items-center justify-center gap-1.5 sm:gap-2 rounded-xl h-10 sm:h-11 px-2 sm:px-3 text-xs sm:text-sm font-medium text-muted-foreground/80 transition-all duration-200 hover:text-foreground hover:bg-muted/40 active:scale-[0.98] border border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:font-semibold data-[state=active]:border-ojas/30 data-[state=active]:shadow-xs"
                >
                  <Settings className="w-4 h-4 shrink-0 transition-colors group-data-[state=active]:text-ojas text-muted-foreground/60 group-hover:text-foreground" aria-hidden="true" />
                  <span className="truncate">{t('profile.tabs.settings', 'Settings')}</span>
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="journey" className="space-y-6 mt-0" aria-busy={metricsLoading}>
              {metricsError && (
                <p className="text-xs text-muted-foreground rounded-2xl border border-hairline bg-card px-4 py-2.5" role="note">
                  {t('profile.journey.metricsUnavailable', 'Live totals are unavailable right now — showing your on-device totals instead.')}
                </p>
              )}
              <JourneyOverview
                displayName={profile.displayName || 'Seeker'}
                email={user?.email || ''}
                familiarityLevel={form.familiarityLevel || 'Seeker'}
                languageLabel={LANGUAGES.find((language) => language.code === form.preferredLanguage)?.name ?? form.preferredLanguage}
                toneLabel={form.guruTone.charAt(0).toUpperCase() + form.guruTone.slice(1)}
                avatarDataUrl={profile.avatarDataUrl}
                avatarUrl={profile.avatarUrl}
                stats={stats}
                sessions={sessions}
                conversations={conversations}
                personalInsights={personalInsights}
                metrics={metrics}
                dailyWisdom={dailyTeaching}
                onNavigate={setTab}
                onContinueChat={(conversationId) => {
                  navigate(conversationId ? `/chat?conversation=${conversationId}` : '/chat');
                }}
                onPractice={() => navigate('/practices')}
                onKnowledgeGraph={() => setTab('memory')}
              />
            </TabsContent>

            <TabsContent value="profile" className="space-y-6 mt-0">
              <Card className="border-0 rounded-none bg-transparent shadow-none">
                <CardHeader className="px-0 pb-2">
                  <CardTitle className="text-lg font-semibold text-foreground">{t("profile.personalDetails.title", "Personal Details")}</CardTitle>
                  <CardDescription>{t("profile.personalDetails.subtitle", "Share a little about yourself so answers can meet you where you are.")}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6 px-0 py-4 sm:py-6">
                  <div className="space-y-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="displayName" className="text-sm font-medium">{t("profile.personalDetails.displayName", "Display Name")}</Label>
                      <Input
                        id="displayName"
                        value={form.displayName}
                        onChange={(e) => patch('displayName', e.target.value)}
                        placeholder={t("profile.personalDetails.displayNamePlaceholder", "How should I address you?")}
                        maxLength={40}
                        className="min-h-[44px] rounded-xl"
                      />
                    </div>
                    {profile.avatarDataUrl && (
                      <Button variant="ghost" size="sm" onClick={handleRemoveAvatar} className="text-destructive hover:text-destructive hover:bg-destructive/10 text-xs min-h-[36px] px-2.5 rounded-lg">
                        <Trash2 className="w-3.5 h-3.5 mr-1.5" /> {t("profile.personalDetails.removePhoto", "Remove photo")}
                      </Button>
                    )}
                  </div>


                  <div className="space-y-2">
                    <Label htmlFor="bio" className="text-sm font-medium">{t("profile.personalDetails.bio", "Your Path & Intention")}</Label>
                    <Textarea
                      id="bio"
                      value={form.bio}
                      onChange={(e) => patch('bio', e.target.value)}
                      placeholder={t("profile.personalDetails.bioPlaceholder", "Share what brings you here or your current spiritual challenges...")}
                      className="min-h-[120px] resize-none rounded-xl"
                      maxLength={280}
                    />
                    <p className="text-xs text-muted-foreground text-right">
                      {form.bio.length}/280 characters
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-ojas" aria-hidden="true" />
                        {t('profile.personalDetails.language', 'Preferred Language')}
                      </Label>
                      <Select
                        value={form.preferredLanguage}
                        onValueChange={(v) => {
                          patch('preferredLanguage', v);
                          void changeUiLanguage(v).catch(() => {
                            toast({
                              title: t('common.error', 'Could not switch language'),
                              description: t('profile.personalDetails.languageSwitchFailed', 'Your preference was saved, but some interface text could not be translated.'),
                              variant: 'destructive',
                            });
                          });
                        }}
                      >
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="max-h-80">
                          {LANGUAGES.map(l => (
                            <SelectItem key={l.code} value={l.code}>
                              {formatLanguageOption(l)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">{t('profile.personalDetails.tone', 'Answer tone')}</Label>
                      <Select value={form.guruTone} onValueChange={(v) => patch('guruTone', v as GuruTone)}>
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {tones.map(tone => (
                            <SelectItem key={tone.value} value={tone.value}>
                              <span className="font-medium">{t(`profile.tone.${tone.value}`, tone.label)}</span>
                              <span className="ml-2 text-xs text-muted-foreground">{t(`profile.tone.${tone.value}Hint`, tone.hint)}</span>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">{t("profile.personalDetails.guidanceDepth", "Guidance depth")}</Label>
                      <Select
                        value={form.familiarityLevel || 'seeker'}
                        onValueChange={(v) => patch('familiarityLevel', v as 'seeker' | 'practitioner' | 'advanced')}
                      >
                        <SelectTrigger className="min-h-[44px] rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="seeker">
                            <span className="font-medium">{t("profile.personalDetails.seeker", "Seeker")}</span>
                            <span className="ms-2 text-xs text-muted-foreground">{t("profile.personalDetails.seekerHint", "Clear Sanskrit explanations")}</span>
                          </SelectItem>
                          <SelectItem value="practitioner">
                            <span className="font-medium">{t("profile.personalDetails.practitioner", "Practitioner")}</span>
                            <span className="ms-2 text-xs text-muted-foreground">{t("profile.personalDetails.practitionerHint", "Balanced meditation guidance")}</span>
                          </SelectItem>
                          <SelectItem value="advanced">
                            <span className="font-medium">{t("profile.personalDetails.advanced", "Advanced")}</span>
                            <span className="ms-2 text-xs text-muted-foreground">{t("profile.personalDetails.advancedHint", "Deep philosophical terms")}</span>
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div
                    data-testid="guidance-preview"
                    aria-live="polite"
                    className="rounded-xl border border-hairline bg-muted/30 px-4 py-3.5"
                  >
                    <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                      {t('profile.personalDetails.guidancePreview', 'Your guidance preview')}
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                      {form.guruTone === 'direct'
                        ? t('profile.personalDetails.toneDirectPreview', 'Clear, concise guidance that comes to the practical next step quickly.')
                        : form.guruTone === 'poetic'
                          ? t('profile.personalDetails.tonePoeticPreview', 'Reflective language with imagery, while keeping the teaching clear and useful.')
                          : t('profile.personalDetails.toneGentlePreview', 'Warm, steady guidance that makes room for your experience before offering a next step.')}
                      {' '}
                      {form.familiarityLevel === 'advanced'
                        ? t('profile.personalDetails.advancedPreview', 'It can use deeper philosophical terms when the teaching supports them.')
                        : form.familiarityLevel === 'practitioner'
                          ? t('profile.personalDetails.practitionerPreview', 'It balances a teaching with a practical reflection or meditation cue.')
                          : t('profile.personalDetails.seekerPreview', 'It explains spiritual terms plainly before building on them.')}
                    </p>
                    <p className="mt-2 text-xs text-ojas/90">
                      {t('profile.personalDetails.sourceAware', 'Source-aware by design: verified quotations remain attributed; unsupported questions receive a clear limit or clarification.')}
                    </p>
                  </div>
                </CardContent>
              </Card>


            </TabsContent>

            <TabsContent value="memory" className="space-y-6 mt-0">
              {/* Segmented Sub-Navigation: Private Reflections vs Guru's Living Memory & Graph */}
              <div className="flex items-center justify-center pt-1 pb-2">
                <div className="inline-flex items-center gap-1.5 p-1 rounded-xl bg-card/85 backdrop-blur-md border border-hairline/80 shadow-xs">
                  <button
                    type="button"
                    onClick={() => setMemorySubTab('notes')}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                      memorySubTab === 'notes'
                        ? 'bg-background text-foreground font-semibold shadow-xs border border-ojas/30'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <BookOpen className="w-3.5 h-3.5 text-ojas" />
                    <span>{t('profile.memory.personalNotes', 'Personal Reflections & Notes')}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setMemorySubTab('guru')}
                    className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium transition-all ${
                      memorySubTab === 'guru'
                        ? 'bg-background text-foreground font-semibold shadow-xs border border-ojas/30'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Brain className="w-3.5 h-3.5 text-ojas" />
                    <span>{t('profile.memory.guruMemory', "Guru's Living Memory & Graph")}</span>
                  </button>
                </div>
              </div>

              {memorySubTab === 'notes' ? (
                <NotesPanel />
              ) : (
                <MemoryManager />
              )}
            </TabsContent>


            <TabsContent value="settings" className="space-y-6 mt-0">
              <SecurityCard setupMfaRedirect={setupMfaRedirect} />
              <PreferencesCard form={form} patch={patch} applyThemeNow={applyThemeNow} />
              <AccountDataCard />
              <SupportCard defaultName={resolveName()} defaultEmail={resolveEmail()} />
            </TabsContent>

            {(tab === 'profile' || tab === 'settings') && (
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 sticky bottom-[calc(1rem+env(safe-area-inset-bottom,0px))] z-20 bg-background/95 backdrop-blur-md py-3 sm:py-4 border-t border-hairline">
                <div>
                  {dirty ? (
                    <p className="text-xs text-ojas font-medium flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full bg-ojas inline-block" aria-hidden="true" />
                      {t('profile.personalDetails.unsavedChanges', 'Unsaved changes...')}
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">{t('profile.personalDetails.savedOnDevice', 'Saved on this device.')}</p>
                  )}
                </div>
                <Button
                  onClick={handleSave}
                  disabled={!dirty}
                  className="w-full sm:w-auto min-h-[44px] h-11 px-8 bg-ojas hover:bg-ojas-light text-primary-foreground shadow-sm gap-2 font-medium rounded-xl"
                >
                  <Save className="w-4 h-4" />
                  {isOnboarding ? t("profile.personalDetails.completeOnboarding", "Complete Onboarding") : t("profile.personalDetails.saveChanges", "Save Changes")}
                </Button>
              </div>
            )}
          </Tabs>
        </div>
      </motion.div>
    </AppShell>
  );
};

export default ProfilePage;
