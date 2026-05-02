import { forwardRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, ExternalLink, Share2 } from 'lucide-react';
import { Message } from '@/lib/chatStorage';
import { useProfile } from '@/hooks/useProfile';
import { getInitials } from '@/lib/profileStorage';
import { WisdomCardGenerator } from './WisdomCardGenerator';

interface ChatMessageProps {
  message: Message;
  index?: number;
  isStreaming?: boolean;
}

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

export const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, index = 0, isStreaming = false }, ref) => {
    const isGuru = message.role === 'guru';
    const { profile } = useProfile();
    const citations = message.citations ?? [];
    const [showWisdomCard, setShowWisdomCard] = useState(false);

    return (
      <>
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.2) }}
          className={`group flex items-start gap-2.5 ${isGuru ? 'justify-start' : 'justify-end'}`}
        >
          {isGuru && (
            <div className="w-8 h-8 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center flex-shrink-0">
              <Sparkles className="w-4 h-4 text-ojas" />
            </div>
          )}

          <div className={`max-w-[82%] sm:max-w-[75%] flex flex-col gap-1.5 ${isGuru ? 'items-start' : 'items-end'}`}>
            <div
              className={`relative px-4 py-2.5 ${
                isGuru
                  ? 'glass-card rounded-2xl rounded-tl-md'
                  : 'bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground rounded-2xl rounded-tr-md shadow-sm'
              }`}
            >
              <p
                className={`text-[14px] leading-relaxed whitespace-pre-wrap break-words ${
                  isGuru ? 'text-foreground' : ''
                }`}
              >
                {message.content}
                {isStreaming && (
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
                    className="inline-block w-[2px] h-[1em] bg-ojas ml-0.5 align-text-bottom"
                  />
                )}
              </p>
              <div className="flex items-center justify-between mt-1.5">
                <p
                  className={`text-[10px] ${
                    isGuru ? 'text-muted-foreground/70' : 'text-primary-foreground/70'
                  }`}
                >
                  {formatTime(message.timestamp)}
                </p>
                {/* Share button on guru messages */}
                {isGuru && message.content && !isStreaming && (
                  <button
                    onClick={() => setShowWisdomCard(true)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded-full hover:bg-ojas/10"
                    title="Share as Wisdom Card"
                  >
                    <Share2 className="w-3 h-3 text-muted-foreground hover:text-ojas" />
                  </button>
                )}
              </div>
            </div>

            {/* Sources card */}
            {isGuru && citations.length > 0 && (
              <div className="w-full rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Sources
                </p>
                <div className="flex flex-col gap-1">
                  {citations.slice(0, 3).map((url, i) => (
                    <a
                      key={`${url}-${i}`}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-[11px] text-ojas hover:text-ojas-light transition-colors group"
                    >
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate group-hover:underline">{getDomain(url)}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>

          {!isGuru && (
            <div className="w-8 h-8 rounded-full bg-prana/15 border border-prana/25 flex items-center justify-center flex-shrink-0 overflow-hidden">
              {profile.avatarDataUrl ? (
                <img src={profile.avatarDataUrl} alt={profile.displayName} className="w-full h-full object-cover" />
              ) : (
                <span className="text-[10px] font-semibold text-prana-dark">
                  {getInitials(profile.displayName)}
                </span>
              )}
            </div>
          )}
        </motion.div>

        {/* Wisdom Card Generator Modal */}
        <WisdomCardGenerator
          isOpen={showWisdomCard}
          onClose={() => setShowWisdomCard(false)}
          content={message.content}
        />
      </>
    );
  }
);

ChatMessage.displayName = 'ChatMessage';

const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
