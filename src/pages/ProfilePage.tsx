import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Camera,
  Trash2,
  Download,
  Save,
  Flame,
  Clock,
  Calendar,
  Wind,
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
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePageMeta } from '@/hooks/usePageMeta';
import { fireTestReminder, requestNotificationPermission } from '@/hooks/useMeditationReminder';
import { AppShell } from '@/components/layout/AppShell';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
import { getMeditationStats, getMeditationStatsFromDb, loadMeditationSessions, type MeditationStats } from '@/lib/meditationStorage';
import { loadConversations } from '@/lib/chatStorage';
import { derivePersonalInsights, type PersonalInsight } from '@/lib/personalInsights';
import { memoryApi, type GuruMemory } from '@/lib/memoryApi';
import { MemoryManager } from '@/components/profile/MemoryManager';
import { TwoFactorSettings } from '@/components/auth/TwoFactorSettings';
import { useToast } from '@/hooks/use-toast';
import { useTheme } from '@/hooks/useTheme';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { supabase } from '@/integrations/supabase/client';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { LANGUAGES } from '@/components/chat/LanguageSelector';

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

const mayuraVoices: { value: string; label: string; hint: string }[] = [
  { value: 'deepika', label: 'Deepika', hint: 'Female · Warm, natural' },
  { value: 'ananya', label: 'Ananya', hint: 'Female · Calm, soothing' },
  { value: 'kavya', label: 'Kavya', hint: 'Female · Bright, clear' },
  { value: 'sangeetha', label: 'Sangeetha', hint: 'Female · Melodic' },
  { value: 'shubh', label: 'Shubh', hint: 'Male · Clear, composed' },
  { value: 'arvind', label: 'Arvind', hint: 'Male · Deep, authoritative' },
];

const formatTime = (mins: number): string => {
  const h = Math.floor(mins / 60).toString().padStart(2, '0');
  const m = (mins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
};

const ProfilePage = () => {
  const { loading: authLoading } = useRequireAuth();
  usePageMeta({
    title: 'Your Profile — AskMukthiGuru',
    description: 'Manage your seeker profile, preferred guru tone, language, theme, and meditation reminder settings.',
    canonical: 'https://askmukthiguru.lovable.app/profile',
  });
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const initialTab = searchParams.get('tab') || 'profile';
  const [tab, setTab] = useState(initialTab);
  const { profile, update } = useProfile();
  const { toast } = useToast();
  const { setTheme: applyThemeNow } = useTheme();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { teaching: dailyTeaching } = useDailyTeaching();

  // Local form state — only persists on Save
  const [form, setForm] = useState(profile);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setForm(profile);
    setDirty(false);
  }, [profile.id]);

  useEffect(() => {
    setSearchParams(tab === 'profile' ? {} : { tab }, { replace: true });
  }, [tab, setSearchParams]);

  const [stats, setStats] = useState<MeditationStats>(() => getMeditationStats());
  const [conversationCount, setConversationCount] = useState<number>(() => loadConversations().length);
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
      theme: form.theme,
      ttsEnabled: form.ttsEnabled,
      ttsRate: form.ttsRate,
      preferredVoice: form.preferredVoice,
      meditationReminders: form.meditationReminders,
      reminderTimeMinutes: form.reminderTimeMinutes,
    });
    setDirty(false);
    toast({ title: 'Profile saved', description: 'Your preferences are updated.' });
  };

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

  const handleDeleteEverything = () => {
    deleteAllData();
    resetProfile();
    toast({ title: 'All data cleared', description: 'A fresh profile was created.' });
  };

  const statCards = [
    { icon: Flame, label: 'Sessions', value: stats.totalSessions, color: 'text-ojas', bg: 'bg-ojas/10' },
    { icon: Clock, label: 'Minutes', value: stats.totalMinutes, color: 'text-prana', bg: 'bg-prana/10' },
    { icon: Calendar, label: 'Streak', value: `${stats.streakDays}d`, color: 'text-ojas-dark', bg: 'bg-ojas-dark/10' },
    { icon: Wind, label: 'Breaths', value: stats.totalCycles, color: 'text-prana-light', bg: 'bg-prana/10' },
  ];

  const isOnboarding = searchParams.get('onboarding') === 'true';

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 text-ojas animate-spin" />
      </div>
    );
  }

  return (
    <AppShell title={isOnboarding ? "Welcome, Seeker" : "My Profile"}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6">
        {/* Profile/Onboarding UI follows... */}
        {/* I'll stop here to avoid creating too large a chunk, but I'll continue below if needed. */}
        <div className="space-y-6">
          <Tabs value={tab} onValueChange={setTab} className="w-full">
            <TabsList className="grid w-full grid-cols-5 mb-8">
              <TabsTrigger value="profile">Profile</TabsTrigger>
              <TabsTrigger value="stats">Insights</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="memory">Memory</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

            <TabsContent value="profile" className="space-y-6 mt-0">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Personal Details</CardTitle>
                  <CardDescription>Tell the Guru about yourself.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="flex flex-col sm:flex-row items-center gap-6 pb-2">
                    <div className="relative group">
                      <Avatar className="w-24 h-24 ring-2 ring-border transition-all group-hover:ring-ojas/40">
                        {(profile.avatarDataUrl || profile.avatarUrl) ? (
                          <AvatarImage src={profile.avatarDataUrl ?? profile.avatarUrl ?? ''} />
                        ) : null}
                        <AvatarFallback className="bg-ojas/10 text-ojas text-xl font-bold">
                          {getInitials(profile.displayName)}
                        </AvatarFallback>
                      </Avatar>
                      <button
                        onClick={() => fileInputRef.current?.click()}
                        className="absolute bottom-0 right-0 p-2 rounded-full bg-ojas text-primary-foreground shadow-lg hover:scale-110 transition-transform"
                      >
                        <Camera className="w-4 h-4" />
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handleAvatarPick}
                      />
                    </div>
                    <div className="flex-1 space-y-3 w-full">
                      <div className="space-y-1.5">
                        <Label htmlFor="displayName">Display Name</Label>
                        <Input
                          id="displayName"
                          value={form.displayName}
                          onChange={(e) => patch('displayName', e.target.value)}
                          placeholder="How should I address you?"
                          maxLength={40}
                        />
                      </div>
                      {profile.avatarDataUrl && (
                        <Button variant="ghost" size="sm" onClick={handleRemoveAvatar} className="text-destructive hover:text-destructive hover:bg-destructive/10 text-xs h-8 px-2">
                          <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Remove photo
                        </Button>
                      )}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="bio">Your Path & Intention</Label>
                    <Textarea
                      id="bio"
                      value={form.bio}
                      onChange={(e) => patch('bio', e.target.value)}
                      placeholder="Share what brings you here or your current spiritual challenges..."
                      className="min-h-[120px] resize-none"
                      maxLength={280}
                    />
                    <p className="text-[11px] text-muted-foreground text-right">
                      {form.bio.length}/280 characters
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Preferred Language</Label>
                      <Select value={form.preferredLanguage} onValueChange={(v) => patch('preferredLanguage', v)}>
                        <SelectTrigger>
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
                      <Label>Guru's Tone</Label>
                      <Select value={form.guruTone} onValueChange={(v) => patch('guruTone', v as GuruTone)}>
                        <SelectTrigger>
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
                  </div>
                </CardContent>
              </Card>

              <div className="flex items-center justify-between gap-4 sticky bottom-4 z-20">
                <div className="hidden sm:block">
                  {dirty && <p className="text-xs text-ojas font-medium animate-pulse">Unsaved changes...</p>}
                </div>
                <Button
                  onClick={handleSave}
                  disabled={!dirty}
                  className="w-full sm:w-auto h-11 px-8 bg-ojas hover:bg-ojas-light text-primary-foreground shadow-lg shadow-ojas/20 gap-2"
                >
                  <Save className="w-4 h-4" />
                  {isOnboarding ? "Complete Onboarding" : "Save Changes"}
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="stats" className="space-y-6 mt-0">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                {statCards.map((s, idx) => (
                  <Card key={idx} className="border-none bg-card/40 backdrop-blur-sm">
                    <CardContent className="p-4 flex flex-col items-center text-center">
                      <div className={`w-10 h-10 rounded-full ${s.bg} flex items-center justify-center mb-2`}>
                        <s.icon className={`w-5 h-5 ${s.color}`} />
                      </div>
                      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">{s.label}</p>
                      <p className="text-xl font-bold text-foreground mt-0.5">{s.value}</p>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Activity Summary</CardTitle>
                  <CardDescription>Your interactions with the Guru.</CardDescription>
                </CardHeader>
                <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-muted/30">
                    <div className="w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center text-ojas">
                      <MessageCircle className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{conversationCount}</p>
                      <p className="text-xs text-muted-foreground">Conversations started</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 p-4 rounded-xl bg-muted/30">
                    <div className="w-12 h-12 rounded-full bg-prana/10 flex items-center justify-center text-prana">
                      <TrendingUp className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">{stats.totalSessions}</p>
                      <p className="text-xs text-muted-foreground">Meditation practices</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Wisdom of the Day */}
              {dailyTeaching && (
                <Card className="overflow-hidden border border-ojas/20 bg-card/80 backdrop-blur-lg">
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
                        <span className="text-[10px] font-semibold text-ojas uppercase tracking-widest">
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

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Recent Insights</CardTitle>
                  <CardDescription>Patterns woven from your practice, mood, and conversations.</CardDescription>
                </CardHeader>
                <CardContent>
                  {personalInsights.length > 0 ? (
                    <div className="space-y-3">
                      {personalInsights.map((insight, idx) => (
                        <div
                          key={`${insight.kind}-${idx}`}
                          className="p-4 rounded-lg bg-ojas/5 border border-ojas/10 flex gap-3"
                        >
                          <Sparkles className="w-5 h-5 text-ojas shrink-0" />
                          <p className="text-sm text-foreground/80 italic leading-relaxed">
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
                      <Button variant="outline" size="sm" onClick={() => navigate('/practices')} className="mt-2">
                        Start a practice <ArrowRight className="w-3.5 h-3.5 ml-1.5" />
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="memory" className="space-y-6 mt-0">
              <MemoryManager />
            </TabsContent>

            <TabsContent value="settings" className="space-y-6 mt-0">
              <TwoFactorSettings />
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Appearance</CardTitle>
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
                          "flex flex-col items-center gap-2 p-3 rounded-xl border transition-all",
                          form.theme === t.value
                            ? "bg-ojas/5 border-ojas text-ojas ring-1 ring-ojas/30"
                            : "bg-card border-border hover:border-border-hover text-muted-foreground"
                        )}
                      >
                        <t.icon className="w-5 h-5" />
                        <span className="text-xs font-medium">{t.label}</span>
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Voice & Audio</CardTitle>
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
                        <Select value={form.preferredVoice || 'deepika'} onValueChange={(v) => patch('preferredVoice', v)}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {mayuraVoices.map(v => (
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

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Reminders</CardTitle>
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
                        <Badge variant="outline" className="text-ojas border-ojas/30 bg-ojas/5">
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
                          className="h-8 text-[11px] gap-2"
                          onClick={() => fireTestReminder(toast)}
                        >
                          <Bell className="w-3.5 h-3.5" /> Send test reminder
                        </Button>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="border-destructive/20 bg-destructive/5">
                <CardHeader>
                  <CardTitle className="text-lg text-destructive flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" /> Danger Zone
                  </CardTitle>
                  <CardDescription>Export your data, or permanently delete your account.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-col sm:flex-row gap-3">
                    <Button variant="outline" className="flex-1 gap-2" onClick={handleExport}>
                      <Download className="w-4 h-4" /> Export Local Data
                    </Button>
                    <Button
                      variant="outline"
                      className="flex-1 gap-2"
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

                  <div className="flex flex-col sm:flex-row gap-3">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="destructive" className="flex-1 gap-2">
                          <Trash2 className="w-4 h-4" /> Clear Local Data
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Clear local data?</AlertDialogTitle>
                          <AlertDialogDescription>
                            Erases this device's profile, chat history, and meditation stats.
                            Your account remains. This cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={handleDeleteEverything} className="bg-destructive hover:bg-destructive/90">
                            Clear
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>

                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="destructive" className="flex-1 gap-2">
                          <Trash2 className="w-4 h-4" /> Delete Account
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Permanently delete your account?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This deletes your account and ALL server-side data: profile, chats,
                            meditation sessions, roles. You will be signed out immediately. This
                            cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            className="bg-destructive hover:bg-destructive/90"
                            onClick={async () => {
                              try {
                                const { error } = await supabase.functions.invoke('delete-my-account', { method: 'POST' });
                                if (error) throw error;
                                deleteAllData();
                                resetProfile();
                                await supabase.auth.signOut();
                                toast({ title: 'Account deleted' });
                                navigate('/', { replace: true });
                              } catch (e) {
                                toast({ title: 'Delete failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
                              }
                            }}
                          >
                            Permanently Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>

                  <p className="text-[11px] text-muted-foreground pt-1">
                    Need help debugging access?{' '}
                    <a href="/auth/diagnostics" className="text-ojas hover:underline">
                      Open auth diagnostics
                    </a>
                  </p>
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
