import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Bell, BookOpen, Check, Flame, Sparkles } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { BACKEND_URL_OR_LOCAL } from '@/lib/backendUrl';
import { getAccessToken } from '@/lib/chat/auth';

/**
 * Daily ritual card — today's teaching + streak check-in + one local reminder.
 *
 * Teaching comes from GET /api/ritual/today (a deterministic pick from the
 * repo's verbatim quote clusters — no LLM, no client-side generation). The
 * card renders nothing if that request fails, so a broken backend never shows
 * a fabricated quotation.
 *
 * Reminders use setTimeout + the Web Notification API while the app is open.
 * There is deliberately no service-worker push here — the copy says so.
 */

interface RitualTeaching {
  text: string;
  speaker: string;
  attribution: string;
  source_label: string;
  url: string;
  kind: string;
}

interface RitualToday {
  date: string;
  teaching: RitualTeaching;
  streak: number | null;
  last_date: string | null;
  checked_in_today: boolean;
}

const REMINDER_ENABLED_KEY = 'askmukthiguru_ritual_reminder_enabled';
const REMINDER_TIME_KEY = 'askmukthiguru_ritual_reminder_time';
const DEFAULT_REMINDER_TIME = '08:00';
/** setTimeout max (2^31-1 ms) — anything larger silently fires immediately. */
const MAX_TIMEOUT_MS = 2_147_483_647;

const supportsNotifications = () => typeof window !== 'undefined' && 'Notification' in window;

export const DailyTeachingCard = () => {
  const { t } = useTranslation();
  const [today, setToday] = useState<RitualToday | null>(null);
  const [checking, setChecking] = useState(false);
  const [signInNeeded, setSignInNeeded] = useState(false);
  const [reminderEnabled, setReminderEnabled] = useState(
    () => localStorage.getItem(REMINDER_ENABLED_KEY) === '1',
  );
  const [reminderTime, setReminderTime] = useState(
    () => localStorage.getItem(REMINDER_TIME_KEY) || DEFAULT_REMINDER_TIME,
  );
  const [reminderFires, setReminderFires] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await getAccessToken().catch(() => undefined);
        const res = await fetch(`${BACKEND_URL_OR_LOCAL}/api/ritual/today`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!res.ok) return;
        const data = (await res.json()) as RitualToday;
        if (!cancelled && data?.teaching?.text) setToday(data);
      } catch {
        // Offline / backend unreachable — stay hidden rather than guess a teaching.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCheckin = useCallback(async () => {
    if (!today || today.checked_in_today || checking) return;
    setChecking(true);
    try {
      const token = await getAccessToken().catch(() => undefined);
      if (!token) {
        setSignInNeeded(true);
        return;
      }
      const res = await fetch(`${BACKEND_URL_OR_LOCAL}/api/ritual/checkin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) {
        setSignInNeeded(true);
        return;
      }
      if (!res.ok) return;
      const data = (await res.json()) as { streak: number | null; last_date: string | null };
      setToday((prev) =>
        prev
          ? { ...prev, streak: data.streak, last_date: data.last_date, checked_in_today: true }
          : prev,
      );
    } catch {
      // Network failure: keep the last known state, never fake a check-in.
    } finally {
      setChecking(false);
    }
  }, [today, checking]);

  const toggleReminder = useCallback(() => {
    setReminderEnabled((prev) => {
      const next = !prev;
      localStorage.setItem(REMINDER_ENABLED_KEY, next ? '1' : '0');
      if (next && supportsNotifications() && Notification.permission === 'default') {
        void Notification.requestPermission().catch(() => undefined);
      }
      return next;
    });
  }, []);

  const changeReminderTime = useCallback((value: string) => {
    setReminderTime(value);
    localStorage.setItem(REMINDER_TIME_KEY, value);
  }, []);

  // One setTimeout per enabled reminder: fires at the chosen local time while
  // the app is open, then re-arms for the next day (reminderFires in deps).
  useEffect(() => {
    if (!reminderEnabled) return;
    const [hours, minutes] = reminderTime.split(':').map(Number);
    if (Number.isNaN(hours) || Number.isNaN(minutes)) return;
    const next = new Date();
    next.setHours(hours, minutes, 0, 0);
    if (next.getTime() <= Date.now()) next.setDate(next.getDate() + 1);
    const delay = Math.min(next.getTime() - Date.now(), MAX_TIMEOUT_MS);
    const timerId = window.setTimeout(() => {
      try {
        if (supportsNotifications() && Notification.permission === 'granted') {
          new Notification(t('ritual.reminderTitle', "Today's Teaching"), {
            body: today?.teaching.text || t('ritual.reminderBody', 'A teaching is waiting for you.'),
          });
        }
      } catch {
        // Some WebViews expose Notification but reject construction.
      }
      setReminderFires((count) => count + 1);
    }, delay);
    return () => window.clearTimeout(timerId);
  }, [reminderEnabled, reminderTime, reminderFires, today, t]);

  if (!today) return null;

  const { teaching, streak, checked_in_today: checkedIn } = today;
  const isQuote = teaching.kind === 'verbatim_quote';
  const externalSource = teaching.url.startsWith('http');

  const streakLabel =
    streak === null
      ? t('ritual.streakUnknown', 'Sign in to keep a streak')
      : streak > 0
        ? t('ritual.streakCount', { count: streak, defaultValue: '{{count}}-day streak' })
        : t('ritual.streakNone', 'No streak yet — start today');

  return (
    <Card className="mb-10 overflow-hidden border border-ojas/20 bg-card/80 p-5 shadow-sm backdrop-blur-md">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-ojas" aria-hidden="true" />
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ojas">
            {t('ritual.badge', "Today's Teaching")}
          </h2>
        </div>
        <span className="flex items-center gap-1 rounded-full bg-ojas/10 px-2 py-0.5 text-[11px] font-medium text-ojas">
          <Flame className="w-3 h-3" aria-hidden="true" />
          {streakLabel}
        </span>
      </div>

      <blockquote className="mt-3">
        <p className="font-serif text-lg leading-relaxed text-foreground/90 italic">
          &ldquo;{teaching.text}&rdquo;
        </p>
        <footer className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{isQuote ? `— ${teaching.speaker || teaching.attribution}` : `— ${teaching.attribution}`}</span>
          {teaching.source_label && <span aria-hidden="true">·</span>}
          {externalSource ? (
            <a
              href={teaching.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ojas hover:underline"
            >
              {teaching.source_label}
            </a>
          ) : (
            <Link to={teaching.url} className="text-ojas hover:underline">
              {teaching.source_label}
            </Link>
          )}
        </footer>
      </blockquote>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={handleCheckin}
          disabled={checking || checkedIn}
          className="inline-flex items-center gap-1.5 rounded-full bg-ojas px-4 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-ojas-light disabled:cursor-default disabled:bg-ojas/40"
        >
          {checkedIn ? <Check className="w-3.5 h-3.5" aria-hidden="true" /> : <BookOpen className="w-3.5 h-3.5" aria-hidden="true" />}
          {checkedIn ? t('ritual.doneToday', 'Checked in for today') : t('ritual.checkIn', 'Done for today')}
        </button>
        {signInNeeded && streak === null && (
          <Link to="/auth" className="text-xs text-ojas hover:underline">
            {t('ritual.signInHint', 'Sign in to keep your streak')}
          </Link>
        )}
      </div>

      <div className="mt-4 border-t border-border/40 pt-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Bell className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{t('ritual.reminderLabel', 'Daily reminder')}</span>
            <input
              type="time"
              value={reminderTime}
              onChange={(event) => changeReminderTime(event.target.value)}
              disabled={!reminderEnabled}
              aria-label={t('ritual.reminderTime', 'Reminder time')}
              className="h-7 rounded-md border border-border/50 bg-background px-1.5 text-xs text-foreground disabled:opacity-50"
            />
          </label>
          <button
            type="button"
            role="switch"
            aria-checked={reminderEnabled}
            aria-label={t('ritual.reminderToggle', 'Toggle daily reminder')}
            onClick={toggleReminder}
            className={`relative h-5 w-9 rounded-full transition-colors ${reminderEnabled ? 'bg-ojas' : 'bg-muted'}`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all ${reminderEnabled ? 'left-4' : 'left-0.5'}`}
            />
          </button>
        </div>
        <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground/80">
          {supportsNotifications()
            ? t(
                'ritual.reminderNote',
                'Reminders work while the app is open. Push notifications coming soon.',
              )
            : t('ritual.reminderUnsupported', 'Your browser does not support notifications.')}
        </p>
      </div>
    </Card>
  );
};

export default DailyTeachingCard;
