import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Sparkles, History, MessageSquare } from 'lucide-react';
import { loadConversations, type Conversation } from '@/lib/chatStorage';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';

interface ChatEmptyStateProps {
  currentConversationId?: string;
  onResume: (conversation: Conversation) => void;
  onOpenTeaching?: () => void;
}

const formatRelative = (iso: string | Date, t: (key: string, opts?: any) => any): string => {
  const time = typeof iso === 'string' ? new Date(iso).getTime() : iso.getTime();
  const diff = Date.now() - time;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return t('common.justNow');
  if (mins < 60) return t('common.minutesAgo', { count: mins });
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return t('common.hoursAgo', { count: hrs });
  const days = Math.floor(hrs / 24);
  return t('common.daysAgo', { count: days });
};

export const ChatEmptyState = ({
  currentConversationId,
  onResume,
  onOpenTeaching,
}: ChatEmptyStateProps) => {
  const { t } = useTranslation();
  const [lastConvo, setLastConvo] = useState<Conversation | null>(null);
  const { teaching } = useDailyTeaching();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const all = await loadConversations();
      if (cancelled) return;
      const candidate = all
        .filter((c) => c.id !== currentConversationId && c.messages.some((m) => m.role === 'user'))
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())[0];
      setLastConvo(candidate ?? null);
    })();
    return () => { cancelled = true; };
  }, [currentConversationId]);

  if (!lastConvo && !teaching?.caption) return null;

  const userMessageCount = lastConvo?.messages.filter((m) => m.role === 'user').length ?? 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.5 }}
      className={`grid gap-3 w-full ${
        lastConvo && teaching?.caption ? 'md:grid-cols-5' : 'grid-cols-1'
      }`}
    >
      {lastConvo && (
        <motion.button
          type="button"
          onClick={() => onResume(lastConvo)}
          whileHover={{ y: -2 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          className={`group relative text-left rounded-2xl border border-ojas/30 bg-gradient-to-br from-card/80 to-ojas/[0.04] hover:border-ojas/60 backdrop-blur-md p-5 transition-all shadow-sm hover:shadow-lg hover:shadow-ojas/10 overflow-hidden ${
            teaching?.caption ? 'md:col-span-3' : ''
          }`}
          aria-label={t('chat.continueLast')}
        >
          <div
            aria-hidden
            className="absolute inset-y-0 left-0 w-[3px] bg-gradient-to-b from-ojas/0 via-ojas/70 to-ojas/0 opacity-60 group-hover:opacity-100 transition-opacity"
          />
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-ojas/15 flex items-center justify-center">
              <History className="w-3.5 h-3.5 text-ojas" />
            </div>
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-[0.15em]">
              {t('chat.continueLeftOff')}
            </span>
            <span className="text-[10px] text-foreground/45 ml-auto tabular-nums">
              {formatRelative(lastConvo.updatedAt, t)}
            </span>
          </div>
          <p className="text-[15px] text-foreground/90 font-sans leading-relaxed line-clamp-2 mb-3">
            {lastConvo.preview || t('chat.resumeLast')}
          </p>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-[11px] text-foreground/55">
              <MessageSquare className="w-3 h-3" />
              <span>{userMessageCount} {t('common.message', { count: userMessageCount })}</span>
            </div>
            <div className="flex items-center gap-1 text-xs font-medium text-ojas group-hover:gap-2 transition-all">
              {t('chat.resume')} <ArrowRight className="w-3.5 h-3.5" />
            </div>
          </div>
        </motion.button>
      )}

      {teaching?.caption && (
        <motion.button
          type="button"
          onClick={onOpenTeaching}
          whileHover={{ y: -2 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          className={`group relative text-left rounded-2xl border border-ojas/30 bg-gradient-to-br from-ojas/[0.08] to-ojas/[0.02] hover:border-ojas/60 backdrop-blur-md p-5 transition-all shadow-sm hover:shadow-lg hover:shadow-ojas/10 overflow-hidden ${
            lastConvo ? 'md:col-span-2' : ''
          }`}
          aria-label={t('chat.openTeaching')}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-7 h-7 rounded-full bg-ojas/15 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-ojas animate-pulse" />
            </div>
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-[0.15em]">
              {t('chat.todaysTeaching')}
            </span>
          </div>
          <p className="text-[14px] text-foreground/85 font-serif italic leading-relaxed line-clamp-3">
            &ldquo;{teaching.caption}&rdquo;
          </p>
        </motion.button>
      )}
    </motion.div>
  );
};
