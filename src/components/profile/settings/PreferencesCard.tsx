import { Bell, BellRing, Monitor, Moon, Sun } from 'lucide-react';
import { cn } from '@/lib/utils';
import { normalizeSarvamVoice, SARVAM_VOICES } from '@/lib/sarvamVoices';
import { fireTestReminder, requestNotificationPermission } from '@/hooks/useMeditationReminder';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';
import type { ThemePreference, UserProfile } from '@/lib/profileStorage';

const themes: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
];

// bulbul:v3 voices — derived from shared SARVAM_VOICES singleton
const voiceOptions = SARVAM_VOICES.map((v) => ({
  value: v.id,
  label: v.label,
  gender: v.gender,
  hint: v.hint,
}));

const normalizeVoice = (voice?: string): string => normalizeSarvamVoice(voice);

const formatTime = (mins: number): string => {
  const h = Math.floor(mins / 60).toString().padStart(2, '0');
  const m = (mins % 60).toString().padStart(2, '0');
  return `${h}:${m}`;
};

interface PreferencesCardProps {
  form: UserProfile;
  patch: <K extends keyof UserProfile>(key: K, value: UserProfile[K]) => void;
  applyThemeNow: (theme: ThemePreference) => void;
}

/** Appearance + Audio + Reminders merged into one Preferences card. */
export const PreferencesCard = ({ form, patch, applyThemeNow }: PreferencesCardProps) => {
  const { t } = useTranslation();
  const { toast } = useToast();

  return (
    <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
      <CardHeader className="pb-4">
        <CardTitle className="text-lg font-serif font-semibold text-foreground">
          {t('profile.preferences.title', 'Preferences')}
        </CardTitle>
        <CardDescription>
          {t('profile.preferences.subtitle', 'Theme, voice, and meditation reminders live here.')}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-0">
        <section aria-label={t('profile.appearance.title', 'Appearance')} className="pb-6">
          <h3 className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">
            {t('profile.appearance.title', 'Appearance')}
          </h3>
          <div className="grid grid-cols-3 gap-3 mt-3">
            {themes.map(theme => (
              <button
                key={theme.value}
                onClick={() => {
                  patch('theme', theme.value);
                  applyThemeNow(theme.value);
                }}
                className={cn(
                  "flex flex-col items-center gap-2 p-3 rounded-xl border border-hairline transition-all min-h-[44px]",
                  form.theme === theme.value
                    ? "bg-ojas/5 border-ojas text-ojas ring-1 ring-ojas/30"
                    : "bg-card hover:bg-muted/30 text-muted-foreground hover:text-foreground"
                )}
              >
                <theme.icon className="w-5 h-5" />
                <span className="text-xs font-medium">{t(`profile.theme.${theme.value}`, theme.label)}</span>
              </button>
            ))}
          </div>
        </section>

        <section aria-label={t('profile.audio.title', 'Audio')} className="py-6 border-t border-hairline space-y-6">
          <h3 className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">
            {t('profile.audio.title', 'Audio')}
          </h3>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label>{t('profile.audio.enableVoice', 'Voice answers')}</Label>
              <p className="text-xs text-muted-foreground">{t('profile.audio.enableVoiceSubtitle', 'Listen to teachings read aloud')}</p>
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
                  <Label>{t('profile.audio.autoplay', 'Read answers aloud automatically')}</Label>
                  <p className="text-xs text-muted-foreground">{t('profile.audio.autoplaySubtitle', 'Read each teaching aloud as it arrives')}</p>
                </div>
                <Switch
                  checked={form.voiceAutoplay ?? false}
                  onCheckedChange={(v) => patch('voiceAutoplay', v)}
                />
              </div>

              <div className="flex justify-between text-xs text-muted-foreground">
                <Label>{t('profile.audio.speechRate', 'Speech rate')}</Label>
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
                <Label>{t('profile.audio.voiceName', 'Voice')}</Label>
                <p className="text-xs text-muted-foreground">{t('profile.audio.voiceSubtitle', 'Choose the voice that reads to you')}</p>
                <Select value={normalizeVoice(form.preferredVoice)} onValueChange={(v) => patch('preferredVoice', v)}>
                  <SelectTrigger className="rounded-xl min-h-[44px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {voiceOptions.map(v => (
                      <SelectItem key={v.value} value={v.value}>
                        <span className="font-medium">{v.label}</span>
                        <span className="ml-2 text-xs text-muted-foreground">{t(`settings.voiceGender_${v.gender}`, v.gender === 'female' ? 'Female' : 'Male')} · {t(`settings.voiceHint_${v.value}`, v.hint)}</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </section>

        <section aria-label={t('profile.reminders.title', 'Reminders')} className="pt-6 border-t border-hairline space-y-6">
          <h3 className="text-[10px] uppercase tracking-[0.14em] font-medium text-muted-foreground">
            {t('profile.reminders.title', 'Meditation reminders')}
          </h3>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label className="flex items-center gap-2">
                {t('profile.reminders.daily', 'Daily reminder')}
                {form.meditationReminders ? <BellRing className="w-3.5 h-3.5 text-ojas" /> : <Bell className="w-3.5 h-3.5" />}
              </Label>
              <p className="text-xs text-muted-foreground">{t('profile.reminders.dailySubtitle', 'A gentle nudge to sit each day')}</p>
            </div>
            <Switch
              checked={form.meditationReminders}
              onCheckedChange={async (v) => {
                if (v) {
                  const ok = await requestNotificationPermission();
                  if (!ok) {
                    toast({
                      title: t('profile.reminders.permissionsRequired', 'Permissions required'),
                      description: t('profile.reminders.permissionsDescription', 'Please enable notifications in your browser settings to use reminders.'),
                      variant: 'destructive'
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
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">{t('profile.reminders.scheduledFor', 'Scheduled for')}</Label>
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
                  <Bell className="w-3.5 h-3.5" /> {t('profile.reminders.test', 'Send test reminder')}
                </Button>
              </div>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
};
