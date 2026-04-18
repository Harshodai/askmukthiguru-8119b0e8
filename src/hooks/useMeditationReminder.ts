import { useEffect, useRef } from 'react';
import { useProfile } from '@/hooks/useProfile';
import { useToast } from '@/hooks/use-toast';

const REMINDER_FIRED_KEY = 'askmukthiguru_reminder_last_fired';

const todayKey = (): string => {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
};

const hasFiredToday = (): boolean => {
  try {
    return localStorage.getItem(REMINDER_FIRED_KEY) === todayKey();
  } catch {
    return false;
  }
};

const markFiredToday = (): void => {
  try {
    localStorage.setItem(REMINDER_FIRED_KEY, todayKey());
  } catch {
    /* ignore */
  }
};

/**
 * Mounted once at the root. While the tab is open, checks every 30 seconds
 * whether the configured reminder time has passed for today and if so,
 * fires an in-app toast and (if granted) a browser Notification.
 */
export const useMeditationReminder = () => {
  const { profile } = useProfile();
  const { toast } = useToast();
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    if (!profile.meditationReminders) {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
      return;
    }

    const tick = () => {
      if (hasFiredToday()) return;
      const now = new Date();
      const minutesNow = now.getHours() * 60 + now.getMinutes();
      if (minutesNow < profile.reminderTimeMinutes) return;

      markFiredToday();

      // In-app toast (always)
      toast({
        title: '🪔 Time to pause',
        description: 'Your daily meditation is calling. A few breaths can change the day.',
      });

      // Browser notification (if permission granted)
      if (
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      ) {
        try {
          const n = new Notification('AskMukthiGuru — meditation reminder', {
            body: 'Take a few minutes for Serene Mind or Soul Sync.',
            icon: '/favicon.ico',
            tag: 'askmukthiguru-reminder',
          });
          n.onclick = () => {
            window.focus();
            window.location.href = '/practices';
            n.close();
          };
        } catch {
          /* notifications unsupported */
        }
      }
    };

    // Run once immediately, then every 30s.
    tick();
    intervalRef.current = window.setInterval(tick, 30_000);
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current);
    };
  }, [profile.meditationReminders, profile.reminderTimeMinutes, toast]);
};

/**
 * Request the OS-level Notification permission.
 * Resolves to the current permission state.
 */
export const requestNotificationPermission = async (): Promise<NotificationPermission> => {
  if (typeof Notification === 'undefined') return 'denied';
  if (Notification.permission === 'granted' || Notification.permission === 'denied') {
    return Notification.permission;
  }
  try {
    return await Notification.requestPermission();
  } catch {
    return 'denied';
  }
};

/**
 * Fire a one-off test notification + toast so users can preview reminders.
 */
export const fireTestReminder = (
  toast: ReturnType<typeof useToast>['toast'],
): void => {
  toast({
    title: '🪔 Test reminder',
    description: 'This is how your daily meditation reminder will appear.',
  });
  if (
    typeof Notification !== 'undefined' &&
    Notification.permission === 'granted'
  ) {
    try {
      new Notification('AskMukthiGuru — test reminder', {
        body: 'Daily meditation reminders look like this.',
        icon: '/favicon.ico',
      });
    } catch {
      /* ignore */
    }
  }
};
