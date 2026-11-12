import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
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
      ? t('chat.stillWorking')
      : phase === 'slow'
        ? t('chat.drawingFromTeachings')
        : t('chat.reflecting');
  return <p className="text-[11px] text-muted-foreground/70 pl-1">{text}</p>;
};

export const WELCOME_MESSAGE = (slug: string | undefined): string =>
  `${greetingPrefix(slug, 'return_new_day')}. Welcome to AskMukthiGuru. You can ask a question to explore the recorded teachings of Sri Krishnaji and Sri Preethaji.\n\n• If a recorded teaching matches, you will receive the teacher's verbatim words with a direct video clip.\n• If no teaching addresses your question, the guide abstains honestly and offers a stillness practice.\n• In cases of acute emotional distress, professional crisis care lines are provided.`;

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
      base = `${prefix}. You completed Soul Sync — centered in stillness. ${insights.encouragement} What question would you like to explore in the teachings?`;
      break;
    case 'serene_mind':
      base = `${prefix}. You completed Serene Mind — breath settled. ${insights.encouragement} What question would you like to explore in the teachings?`;
      break;
    case 'both':
      base = `${prefix}. You completed Soul Sync and Serene Mind. ${insights.encouragement} What question would you like to explore in the teachings?`;
      break;
    case 'none':
      base = `${prefix}. Welcome. We can begin gently. ${insights.encouragement} What question would you like to explore in the teachings?`;
      break;
    default:
      base = WELCOME_MESSAGE(slug);
  }
  return base;
};
