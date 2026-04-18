import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
} from 'lucide-react';
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
} from '@/lib/profileStorage';
import { getMeditationStats } from '@/lib/meditationStorage';
import { loadConversations } from '@/lib/chatStorage';
import { useToast } from '@/hooks/use-toast';

const languages: { code: 'en' | 'hi' | 'te' | 'ml'; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिंदी (Hindi)' },
  { code: 'te', label: 'తెలుగు (Telugu)' },
  { code: 'ml', label: 'മലയാളം (Malayalam)' },
];

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

const formatTime = (mins: number): string => {
  const h = Math.floor(mins / 60).toString().padStart(2, '0');
  const m = (mins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
};

const ProfilePage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'profile';
  const [tab, setTab] = useState(initialTab);
  const { profile, update } = useProfile();
  const { toast } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const stats = useMemo(() => getMeditationStats(), [profile.updatedAt]);
  const conversationCount = useMemo(() => loadConversations().length, [profile.updatedAt]);

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

  return (
    <AppShell title="My Profile">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-10 space-y-6">
        {/* Hero card */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <Card className="overflow-hidden border-ojas/20">
            <div className="h-24 bg-gradient-to-r from-ojas/30 via-ojas-light/40 to-prana/20" />
            <CardContent className="pt-0">
              <div className="flex flex-col sm:flex-row sm:items-end gap-4 -mt-10">
                <div className="relative">
                  <Avatar className="w-24 h-24 ring-4 ring-card shadow-lg">
                    {profile.avatarDataUrl ? (
                      <AvatarImage src={profile.avatarDataUrl} alt={profile.displayName} />
                    ) : null}
                    <AvatarFallback className="bg-ojas/20 text-ojas text-2xl font-semibold">
                      {getInitials(profile.displayName)}
                    </AvatarFallback>
                  </Avatar>
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="absolute -bottom-1 -right-1 p-2 rounded-full bg-ojas text-primary-foreground shadow-md hover:scale-105 transition"
                    aria-label="Upload avatar"
                  >
                    <Camera className="w-3.5 h-3.5" />
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleAvatarPick}
                  />
                </div>
                <div className="flex-1 min-w-0 pb-2">
                  <h2 className="text-xl sm:text-2xl font-semibold text-foreground truncate">
                    {profile.displayName}
                  </h2>
                  <p className="text-sm text-muted-foreground truncate">
                    {profile.bio || 'A seeker walking the path of the Beautiful State.'}
                  </p>
                  <div className="flex flex-wrap gap-2 mt-2">
                    <Badge variant="secondary" className="bg-ojas/15 text-ojas border-ojas/30">
                      <Sparkles className="w-3 h-3 mr-1" /> {profile.guruTone}
                    </Badge>
                    <Badge variant="outline">{profile.preferredLanguage.toUpperCase()}</Badge>
                    {profile.avatarDataUrl && (
                      <button
                        onClick={handleRemoveAvatar}
                        className="text-[11px] text-muted-foreground hover:text-destructive underline"
                      >
                        Remove avatar
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid grid-cols-4 w-full sm:w-auto">
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="preferences">Preferences</TabsTrigger>
            <TabsTrigger value="stats">Stats</TabsTrigger>
            <TabsTrigger value="account">Account</TabsTrigger>
          </TabsList>

          {/* PROFILE TAB */}
          <TabsContent value="profile" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>About you</CardTitle>
                <CardDescription>How the Gurus address you.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="displayName">Display name</Label>
                  <Input
                    id="displayName"
                    value={form.displayName}
                    maxLength={40}
                    onChange={(e) => patch('displayName', e.target.value)}
                    placeholder="Seeker"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bio">Intention / bio</Label>
                  <Textarea
                    id="bio"
                    value={form.bio}
                    maxLength={280}
                    rows={3}
                    onChange={(e) => patch('bio', e.target.value)}
                    placeholder="What brings you to this practice?"
                  />
                  <p className="text-xs text-muted-foreground text-right">
                    {form.bio.length}/280
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* PREFERENCES TAB */}
          <TabsContent value="preferences" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Voice & language</CardTitle>
                <CardDescription>How the Gurus speak with you.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="space-y-2">
                  <Label>Preferred language</Label>
                  <Select
                    value={form.preferredLanguage}
                    onValueChange={(v) => patch('preferredLanguage', v as typeof form.preferredLanguage)}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {languages.map((l) => (
                        <SelectItem key={l.code} value={l.code}>{l.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>Guru tone</Label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {tones.map((t) => {
                      const active = form.guruTone === t.value;
                      return (
                        <button
                          key={t.value}
                          type="button"
                          onClick={() => patch('guruTone', t.value)}
                          className={`text-left p-3 rounded-lg border transition-all ${
                            active
                              ? 'border-ojas/50 bg-ojas/10 shadow-sm'
                              : 'border-border hover:border-ojas/30'
                          }`}
                        >
                          <p className="font-medium text-sm">{t.label}</p>
                          <p className="text-xs text-muted-foreground">{t.hint}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="tts">Read responses aloud</Label>
                    <p className="text-xs text-muted-foreground">Auto-speak guru replies in chat.</p>
                  </div>
                  <Switch
                    id="tts"
                    checked={form.ttsEnabled}
                    onCheckedChange={(v) => patch('ttsEnabled', v)}
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Speaking rate</Label>
                    <span className="text-xs text-muted-foreground">{form.ttsRate.toFixed(1)}x</span>
                  </div>
                  <Slider
                    value={[form.ttsRate]}
                    min={0.5}
                    max={1.5}
                    step={0.1}
                    onValueChange={([v]) => patch('ttsRate', v)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Meditation reminders</CardTitle>
                <CardDescription>A gentle nudge each day.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <Label htmlFor="reminders">Daily reminder</Label>
                  <Switch
                    id="reminders"
                    checked={form.meditationReminders}
                    onCheckedChange={(v) => patch('meditationReminders', v)}
                  />
                </div>
                {form.meditationReminders && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="reminderTime">Time</Label>
                      <Input
                        id="reminderTime"
                        type="time"
                        value={formatTime(form.reminderTimeMinutes)}
                        onChange={(e) => {
                          const [h, m] = e.target.value.split(':').map(Number);
                          patch('reminderTimeMinutes', (h || 0) * 60 + (m || 0));
                        }}
                      />
                    </div>

                    <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-3">
                      <div className="flex items-start gap-2">
                        <Bell className="w-4 h-4 mt-0.5 text-ojas shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">Browser notifications</p>
                          <p className="text-xs text-muted-foreground">
                            Allow desktop notifications so the reminder reaches you even
                            when this tab is in the background.
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={async () => {
                            const result = await requestNotificationPermission();
                            toast({
                              title:
                                result === 'granted'
                                  ? 'Notifications enabled'
                                  : result === 'denied'
                                  ? 'Notifications blocked'
                                  : 'Permission unchanged',
                              description:
                                result === 'denied'
                                  ? 'You can re-enable them from your browser settings.'
                                  : undefined,
                              variant: result === 'denied' ? 'destructive' : undefined,
                            });
                          }}
                        >
                          <Bell className="w-3.5 h-3.5 mr-1.5" />
                          Enable browser alerts
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => fireTestReminder(toast)}
                        >
                          <BellRing className="w-3.5 h-3.5 mr-1.5" />
                          Test reminder
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Appearance</CardTitle>
                <CardDescription>Choose how the sanctuary looks.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-2">
                  {themes.map((t) => {
                    const active = form.theme === t.value;
                    return (
                      <button
                        key={t.value}
                        type="button"
                        onClick={() => patch('theme', t.value)}
                        className={`flex flex-col items-center justify-center gap-1.5 p-4 rounded-lg border transition-all ${
                          active
                            ? 'border-ojas/50 bg-ojas/10 shadow-sm'
                            : 'border-border hover:border-ojas/30'
                        }`}
                        aria-pressed={active}
                      >
                        <t.icon className={`w-5 h-5 ${active ? 'text-ojas' : 'text-muted-foreground'}`} />
                        <span className="text-sm font-medium">{t.label}</span>
                      </button>
                    );
                  })}
                </div>
                <p className="text-xs text-muted-foreground mt-3">
                  System matches your device's appearance.
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          {/* STATS TAB */}
          <TabsContent value="stats" className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {statCards.map((s) => (
                <Card key={s.label}>
                  <CardContent className="pt-6 text-center">
                    <div className={`w-10 h-10 rounded-full ${s.bg} flex items-center justify-center mx-auto mb-2`}>
                      <s.icon className={`w-5 h-5 ${s.color}`} />
                    </div>
                    <p className="text-2xl font-semibold text-foreground">{s.value}</p>
                    <p className="text-xs text-muted-foreground">{s.label}</p>
                  </CardContent>
                </Card>
              ))}
            </div>

            <Card>
              <CardHeader>
                <CardTitle>Activity</CardTitle>
                <CardDescription>Your journey so far.</CardDescription>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground space-y-2">
                <div className="flex justify-between">
                  <span>Conversations saved</span>
                  <span className="text-foreground font-medium">{conversationCount}</span>
                </div>
                <div className="flex justify-between">
                  <span>Last meditation</span>
                  <span className="text-foreground font-medium">
                    {stats.lastSessionDate
                      ? new Date(stats.lastSessionDate).toLocaleDateString()
                      : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Profile created</span>
                  <span className="text-foreground font-medium">
                    {new Date(profile.createdAt).toLocaleDateString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* ACCOUNT TAB */}
          <TabsContent value="account" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Your data</CardTitle>
                <CardDescription>
                  Everything is stored locally in your browser. Nothing leaves your device.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button onClick={handleExport} variant="outline" className="w-full sm:w-auto">
                  <Download className="w-4 h-4 mr-2" /> Export all data (JSON)
                </Button>
              </CardContent>
            </Card>

            <Card className="border-destructive/40">
              <CardHeader>
                <CardTitle className="text-destructive flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5" /> Danger zone
                </CardTitle>
                <CardDescription>
                  Permanently remove your profile, conversations, and meditation history.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive">
                      <Trash2 className="w-4 h-4 mr-2" /> Delete all data
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete everything?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will erase your profile, all chat conversations, and meditation
                        sessions from this browser. This cannot be undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={handleDeleteEverything}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      >
                        Yes, delete everything
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Sticky save bar */}
        {dirty && (tab === 'profile' || tab === 'preferences') && (
          <motion.div
            initial={{ y: 60, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="sticky bottom-4 flex justify-center"
          >
            <div className="glass-card flex items-center gap-3 px-4 py-3 shadow-lg">
              <span className="text-sm text-muted-foreground hidden sm:inline">
                Unsaved changes
              </span>
              <Button variant="ghost" size="sm" onClick={() => { setForm(profile); setDirty(false); }}>
                Discard
              </Button>
              <Button size="sm" onClick={handleSave}>
                <Save className="w-4 h-4 mr-2" /> Save changes
              </Button>
            </div>
          </motion.div>
        )}
      </div>
    </AppShell>
  );
};

export default ProfilePage;
