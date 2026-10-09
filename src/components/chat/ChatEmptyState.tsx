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

type RelativeTranslation = (key: string, opts?: { count?: number }) => string;
const formatRelative = (iso: string | Date, t: RelativeTranslation): string => {
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

const WhatsAppIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L0 24l6.335-1.662c1.746.953 3.71 1.455 5.711 1.456h.005c6.554 0 11.89-5.336 11.893-11.893a11.821 11.821 0 00-3.48-8.414z" />
  </svg>
);

export const ChatEmptyState = ({
  currentConversationId,
  onResume,
  onOpenTeaching,
}: ChatEmptyStateProps) => {
  const { t } = useTranslation();
  const [lastConvo, setLastConvo] = useState<Conversation | null>(null);
  const { teaching } = useDailyTeaching();
  const rawWhatsApp = (import.meta.env.VITE_WHATSAPP_NUMBER || '').trim();
  const whatsappNumber = rawWhatsApp.replace(/[^0-9]/g, '');
  const whatsappUrl = `https://wa.me/${whatsappNumber}?text=Namaste%20Mukthi%20Guru`;

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
      className={`max-w-lg mx-auto text-center grid gap-3 w-full ${
        lastConvo && teaching?.caption ? 'md:grid-cols-5' : 'grid-cols-1'
      }`}
    >
      {lastConvo && (
        <motion.button
          type="button"
          onClick={() => onResume(lastConvo)}
          whileHover={{ y: -2 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          className={`group relative text-left rounded-2xl border border-hairline bg-card hover:border-ojas/40 p-4 transition-all shadow-sm hover:shadow-md overflow-hidden ${
            teaching?.caption ? 'md:col-span-3' : ''
          }`}
          aria-label={t('chat.continueLast')}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-full bg-ojas/10 flex items-center justify-center">
              <History className="w-3 h-3 text-ojas" />
            </div>
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-wider">
              {t('chat.continueLeftOff')}
            </span>
            <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">
              {formatRelative(lastConvo.updatedAt, t)}
            </span>
          </div>
          <p className="text-sm text-foreground/90 leading-relaxed line-clamp-2 mb-3">
            {lastConvo.preview || t('chat.resumeLast')}
          </p>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <MessageSquare className="w-3 h-3" />
              <span>{userMessageCount} {t('common.message', { count: userMessageCount })}</span>
            </div>
            <div className="flex items-center gap-1 text-xs font-medium text-ojas group-hover:gap-1.5 transition-all">
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
          className={`group relative text-left rounded-2xl border border-hairline bg-card hover:border-ojas/40 p-4 transition-all shadow-sm hover:shadow-md overflow-hidden ${
            lastConvo ? 'md:col-span-2' : ''
          }`}
          aria-label={t('chat.openTeaching')}
        >
          <div className="flex items-center gap-2 mb-2">
            <div className="w-6 h-6 rounded-full bg-ojas/10 flex items-center justify-center">
              <Sparkles className="w-3 h-3 text-ojas" />
            </div>
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-wider">
              {t('chat.todaysTeaching')}
            </span>
          </div>
          <p className="text-[13px] text-foreground/80 font-serif italic leading-relaxed line-clamp-3">
            &ldquo;{teaching.caption}&rdquo;
          </p>
        </motion.button>
      )}

      <motion.a
        href={whatsappUrl}
        target="_blank"
        rel="noopener noreferrer"
        whileHover={{ y: -2 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        className={`group relative flex items-center justify-between rounded-2xl border border-hairline bg-card hover:border-emerald-500/40 p-4 transition-all shadow-sm hover:shadow-md overflow-hidden text-left ${
          lastConvo && teaching?.caption ? 'md:col-span-5' : ''
        }`}
        aria-label={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
        data-testid="whatsapp-empty-state-banner"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
            <WhatsAppIcon className="w-4 h-4 fill-current" />
          </div>
          <div>
            <div className="text-xs font-semibold text-foreground group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
              {t('chat.whatsappBannerTitle', 'Connect with Mukthi Guru on WhatsApp')}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {t('chat.whatsappBannerSubtitle', 'Ask questions & receive daily wisdom directly on your phone')}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 group-hover:gap-1.5 transition-all shrink-0">
          <span>{t('chat.openWhatsApp', 'Chat')}</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </div>
      </motion.a>
    </motion.div>
  );
};
