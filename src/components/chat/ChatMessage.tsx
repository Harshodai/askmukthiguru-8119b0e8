import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { Message } from '@/lib/chatStorage';

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage = ({ message }: ChatMessageProps) => {
  const isGuru = message.role === 'guru';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.3 }}
      className={`flex items-start gap-3 ${isGuru ? 'justify-start' : 'justify-end'}`}
    >
      {/* Guru Avatar */}
      {isGuru && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-ojas/30 to-prana/30 flex items-center justify-center flex-shrink-0">
          <Sparkles className="w-4 h-4 text-ojas" />
        </div>
      )}

      {/* Message Bubble */}
      <div
        className={`max-w-[80%] ${
          isGuru
            ? 'glass-card rounded-2xl rounded-tl-sm'
            : 'bg-gradient-to-r from-ojas to-ojas-dark text-primary-foreground rounded-2xl rounded-tr-sm'
        } px-4 py-3`}
      >
        <p className={`text-sm leading-relaxed ${isGuru ? 'text-tejas/90' : ''}`}>
          {message.content}
        </p>
        <p className={`text-xs mt-2 ${isGuru ? 'text-muted-foreground/50' : 'text-primary-foreground/60'}`}>
          {formatTime(message.timestamp)}
        </p>
      </div>

      {/* User Avatar Placeholder */}
      {!isGuru && (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-prana to-prana-dark flex items-center justify-center flex-shrink-0">
          <span className="text-xs font-medium text-secondary-foreground">You</span>
        </div>
      )}
    </motion.div>
  );
};

const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
