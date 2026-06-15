/**
 * Empty-state cards rendered above the starter suggestions on a fresh chat.
 * - "Continue last conversation" — when the user has prior history.
 * - "Today's teaching" — daily Krishnaji teaching pulled from useDailyTeaching.
 *
 * Cards are intentionally compact and use the project's golden / glassmorphism
 * tokens so they sit naturally beneath the welcome message.
 */
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Sparkles, History } from 'lucide-react';
import { loadConversations, type Conversation } from '@/lib/chatStorage';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';

interface ChatEmptyStateProps {
  currentConversationId?: string;
  onResume: (conversation: Conversation) => void;
  onOpenTeaching?: () => void;
}

const formatRelative = (iso: string | Date): string => {
  const t = typeof iso === 'string' ? new Date(iso).getTime() : iso.getTime();
  const diff = Date.now() - t;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
};

export const ChatEmptyState = ({
  currentConversationId,
  onResume,
  onOpenTeaching,
}: ChatEmptyStateProps) => {
  const [lastConvo, setLastConvo] = useState<Conversation | null>(null);
  const { teaching } = useDailyTeaching();

  useEffect(() => {
    const all = loadConversations();
    const candidate = all
      .filter((c) => c.id !== currentConversationId && c.messages.some((m) => m.role === 'user'))
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())[0];
    setLastConvo(candidate ?? null);
  }, [currentConversationId]);

  if (!lastConvo && !teaching?.caption) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25 }}
      className="grid grid-cols-1 sm:grid-cols-2 gap-3 mx-auto max-w-xl pt-2"
    >
      {lastConvo && (
        <button
          type="button"
          onClick={() => onResume(lastConvo)}
          className="group text-left rounded-2xl border border-ojas/25 bg-card/60 hover:bg-ojas/10 hover:border-ojas/50 backdrop-blur-sm p-4 transition-all"
          aria-label="Continue last conversation"
        >
          <div className="flex items-center gap-2 mb-1.5">
            <History className="w-3.5 h-3.5 text-ojas" />
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-widest">
              Continue
            </span>
            <span className="text-[10px] text-foreground/50 ml-auto">
              {formatRelative(lastConvo.updatedAt)}
            </span>
          </div>
          <p className="text-sm text-foreground/85 font-serif line-clamp-2 leading-snug">
            {lastConvo.preview || lastConvo.title || 'Resume your last conversation'}
          </p>
          <div className="flex items-center gap-1 mt-2 text-xs text-ojas/80 group-hover:text-ojas">
            Resume <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
          </div>
        </button>
      )}

      {teaching?.caption && (
        <button
          type="button"
          onClick={onOpenTeaching}
          className="group text-left rounded-2xl border border-ojas/25 bg-ojas/5 hover:bg-ojas/10 hover:border-ojas/50 backdrop-blur-sm p-4 transition-all"
          aria-label="Open today's teaching"
        >
          <div className="flex items-center gap-2 mb-1.5">
            <Sparkles className="w-3.5 h-3.5 text-ojas animate-pulse" />
            <span className="text-[10px] font-semibold text-ojas uppercase tracking-widest">
              Today&apos;s Teaching
            </span>
          </div>
          <p className="text-sm text-foreground/85 font-serif italic line-clamp-3 leading-snug">
            &ldquo;{teaching.caption}&rdquo;
          </p>
        </button>
      )}
    </motion.div>
  );
};
