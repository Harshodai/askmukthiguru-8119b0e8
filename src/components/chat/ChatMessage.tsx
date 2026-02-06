import { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { Message } from '@/lib/chatStorage';

interface ChatMessageProps {
  message: Message;
  index?: number;
}

export const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, index = 0 }, ref) => {
    const isGuru = message.role === 'guru';

    return (
      <motion.div
        ref={ref}
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ 
          duration: 0.4,
          delay: index * 0.05,
          type: 'spring',
          stiffness: 300,
          damping: 25
        }}
        className={`flex items-start gap-3 ${isGuru ? 'justify-start' : 'justify-end'}`}
      >
        {/* Guru Avatar */}
        {isGuru && (
          <motion.div 
            className="w-8 h-8 rounded-full bg-gradient-to-br from-ojas/30 to-prana/30 flex items-center justify-center flex-shrink-0"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ 
              delay: index * 0.05 + 0.1,
              type: 'spring',
              stiffness: 400,
              damping: 15
            }}
          >
            <Sparkles className="w-4 h-4 text-ojas" />
          </motion.div>
        )}

        {/* Message Bubble */}
        <motion.div
          className={`max-w-[80%] ${
            isGuru
              ? 'glass-card rounded-2xl rounded-tl-sm'
              : 'bg-gradient-to-r from-ojas to-ojas-dark text-primary-foreground rounded-2xl rounded-tr-sm'
          } px-4 py-3`}
          whileHover={{ scale: 1.01 }}
          transition={{ duration: 0.2 }}
        >
          <motion.p 
            className={`text-sm leading-relaxed ${isGuru ? 'text-tejas/90' : ''}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: index * 0.05 + 0.15 }}
          >
            {message.content}
          </motion.p>
          <motion.p 
            className={`text-xs mt-2 ${isGuru ? 'text-muted-foreground/50' : 'text-primary-foreground/60'}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: index * 0.05 + 0.2 }}
          >
            {formatTime(message.timestamp)}
          </motion.p>
        </motion.div>

        {/* User Avatar */}
        {!isGuru && (
          <motion.div 
            className="w-8 h-8 rounded-full bg-gradient-to-br from-prana to-prana-dark flex items-center justify-center flex-shrink-0"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ 
              delay: index * 0.05 + 0.1,
              type: 'spring',
              stiffness: 400,
              damping: 15
            }}
          >
            <span className="text-xs font-medium text-secondary-foreground">You</span>
          </motion.div>
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
