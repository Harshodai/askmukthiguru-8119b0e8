import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, BookOpen } from 'lucide-react';
import type { MessageError, MessageErrorKind } from '@/lib/chatStorage';
import { greetingPrefix } from '@/lib/greeting';
import { derivePrePracticeInsights } from '@/lib/profileStorage';

export const OptimisticPlaceholder = () => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0 }}
    className="flex items-start gap-3 w-full"
  >
    <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5 animate-pulse">
      <Sparkles className="w-3.5 h-3.5 text-ojas/60" />
    </div>
    <div className="flex-1 flex flex-col gap-2 max-w-[85%] sm:max-w-[75%]">
      <div className="border-l-[3px] border-ojas/10 pl-4 py-2 space-y-3 w-full bg-gradient-to-r from-ojas/5 to-transparent rounded-r-xl">
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[90%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[85%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[95%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[60%]" />
      </div>
      <div className="w-full rounded-xl border border-ojas/10 bg-card/30 p-3 space-y-2.5">
        <div className="flex items-center gap-2">
          <BookOpen className="w-3 h-3 text-ojas/40 animate-pulse" />
          <div className="h-2.5 bg-muted-foreground/10 rounded animate-pulse w-24" />
        </div>
        <div className="space-y-1.5 pl-5">
          <div className="h-2 bg-muted-foreground/10 rounded animate-pulse w-2/3" />
          <div className="h-2 bg-muted-foreground/10 rounded animate-pulse w-1/2" />
        </div>
      </div>
    </div>
  </motion.div>
);

export const SlowResponseHint = ({ visible }: { visible: boolean }) => {
  const [phase, setPhase] = useState<'normal' | 'slow' | 'verySlow'>('normal');
  useEffect(() => {
    if (!visible) {
      setPhase('normal');
      return;
    }
    const t1 = window.setTimeout(() => setPhase('slow'), 6000);
    const t2 = window.setTimeout(() => setPhase('verySlow'), 15000);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [visible]);
  const text =
    phase === 'verySlow'
      ? 'Still drawing from the teachings — long answers take a moment.'
      : phase === 'slow'
        ? 'Drawing from the teachings…'
        : 'Delving deep into ancient wisdom for your answer';
  return <p className="text-[11px] text-muted-foreground/70 pl-1">{text}</p>;
};

// Build a user-facing MessageError from an internal error code / details.
export const buildMessageError = (
  code: MessageErrorKind | string | undefined,
  rawMessage?: string,
  status?: number,
): MessageError => {
  const detail = status ? `${rawMessage ?? ''} (HTTP ${status})`.trim() : rawMessage;
  switch (code) {
    case 'unauthorized':
      return {
        kind: 'unauthorized',
        title: 'Your session expired',
        description: 'Please sign in again to continue your conversation with the Guru.',
        actionLabel: 'sign_in',
        detail,
      };
    case 'rate_limited':
      return {
        kind: 'rate_limited',
        title: 'Too many requests',
        description: 'Please pause for a few seconds, then try again.',
        actionLabel: 'retry',
        detail,
      };
    case 'network':
      return {
        kind: 'network',
        title: 'Cannot reach the Guru',
        description: 'Network or backend is unreachable. Check your connection and retry.',
        actionLabel: 'retry',
        detail,
      };
    case 'timeout':
      return {
        kind: 'timeout',
        title: 'The response timed out',
        description: 'The Guru took too long to respond. Please retry your question.',
        actionLabel: 'retry',
        detail,
      };
    case 'server_error':
      return {
        kind: 'server_error',
        title: 'Service unavailable',
        description: 'Our backend returned an error. Please retry in a moment.',
        actionLabel: 'retry',
        detail,
      };
    case 'circuit_breaker':
      return {
        kind: 'circuit_breaker',
        title: 'AI service temporarily unavailable',
        description: 'The Guru\'s inner circuit is resetting. The cosmic connection will be restored shortly — please retry in a moment.',
        actionLabel: 'retry',
        detail,
      };
    default:
      return {
        kind: 'unknown',
        title: 'Something went wrong',
        description: rawMessage || 'The Guru could not answer this time. Please retry.',
        actionLabel: 'retry',
        detail,
      };
  }
};

export const WELCOME_MESSAGE = (slug: string | undefined): string =>
  `${greetingPrefix(slug, 'return_new_day')}, dear seeker. I am here to guide you toward your beautiful state. What brings you here today? Share what is in your heart, and together we shall explore the path to inner peace.`;

type PrePracticeLog = NonNullable<
  ReturnType<typeof import('@/lib/profileStorage').loadProfile>['prePracticeLog']
>;

export const buildPersonalisedWelcome = (log: PrePracticeLog | undefined, slug: string | undefined, recentMood?: string): string => {
  if (!log) return WELCOME_MESSAGE(slug);
  const insights = derivePrePracticeInsights(log);
  const prefix = greetingPrefix(slug, 'return_new_day');
  let base: string;
  switch (log.lastAnswer) {
    case 'soul_sync':
      base = `${prefix}. You arrived after Soul Sync — your heart is already listening. ${insights.encouragement} What would you like to explore?`;
      break;
    case 'serene_mind':
      base = `${prefix}. The Serene Mind practice has settled your breath. ${insights.encouragement} Share what stirs within.`;
      break;
    case 'both':
      base = `${prefix}. Soul Sync and Serene Mind together — a beautiful preparation. ${insights.encouragement} Speak freely.`;
      break;
    case 'none':
      base = `${prefix}, dear seeker. We can begin gently. ${insights.encouragement} What brings you here today?`;
      break;
    default:
      base = WELCOME_MESSAGE(slug);
  }
  if (recentMood === 'anxious' || recentMood === 'frustrated') {
    base += ' I sense some turbulence — let us find stillness together.';
  } else if (recentMood === 'sad') {
    base += ' I hold space for your heart. Share what weighs on you.';
  } else if (recentMood === 'calm') {
    base += ' A quiet mind is already a temple. Let us deepen that peace.';
  }
  return base;
};
