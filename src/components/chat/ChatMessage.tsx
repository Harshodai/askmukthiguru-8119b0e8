import { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { Message } from '@/lib/chatStorage';
import { useProfile } from '@/hooks/useProfile';
import { getInitials } from '@/lib/profileStorage';

interface ChatMessageProps {
  message: Message;
  index?: number;
}

export const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, index = 0 }, ref) => {
    const isGuru = message.role === 'guru';
    const { profile } = useProfile();

    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{
          duration: 0.3,
          delay: Math.min(index * 0.04, 0.2),
        }}
        className={`flex items-start gap-2.5 ${isGuru ? 'justify-start' : 'justify-end'}`}
      >
        {isGuru && (
          <div className="w-8 h-8 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-4 h-4 text-ojas" />
          </div>
        )}

        <div
          className={`max-w-[82%] sm:max-w-[75%] px-4 py-2.5 ${
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
          </p>
          <p
            className={`text-[10px] mt-1.5 ${
              isGuru ? 'text-muted-foreground/70' : 'text-primary-foreground/70'
            }`}
          >
            {formatTime(message.timestamp)}
          </p>
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
