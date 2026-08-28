import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, CornerDownLeft, Edit3, Paperclip, Trash2, Zap } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export interface QueuedMessage {
  id: string;
  text: string;
  attachedFiles?: Array<{ name: string; content: string }>;
  timestamp: number;
}

interface QueuedMessagesTrayProps {
  queue: QueuedMessage[];
  onSendNow: (id: string) => void;
  onEdit: (id: string) => void;
  onRemove: (id: string) => void;
  onClearAll?: () => void;
}

export const QueuedMessagesTray: React.FC<QueuedMessagesTrayProps> = ({
  queue,
  onSendNow,
  onEdit,
  onRemove,
  onClearAll,
}) => {
  const { t } = useTranslation();

  if (queue.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 12, scale: 0.98 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="w-full max-w-3xl mx-auto mb-2 px-3 sm:px-4"
    >
      <div className="rounded-2xl border border-saffron-gold/30 bg-zinc-950/85 backdrop-blur-xl shadow-2xl p-3 ring-1 ring-white/10">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10 text-xs">
          <div className="flex items-center gap-2 text-saffron-gold font-mono font-semibold tracking-wider uppercase text-[11px]">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-saffron-gold opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-saffron-gold" />
            </span>
            <span>
              {queue.length} {queue.length === 1 ? 'Message Queued' : 'Messages Queued'}
            </span>
          </div>

          <div className="flex items-center gap-3 text-[11px] text-white/50">
            <span className="hidden sm:inline-flex items-center gap-1 font-mono">
              <CornerDownLeft className="w-3 h-3 text-saffron-gold" /> Auto-dispatches on response
            </span>
            {queue.length > 1 && onClearAll && (
              <button
                type="button"
                onClick={onClearAll}
                className="text-rose-400/80 hover:text-rose-300 transition-colors"
              >
                Clear all
              </button>
            )}
          </div>
        </div>

        {/* Queued Message Items */}
        <div className="space-y-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
          <AnimatePresence initial={false}>
            {queue.map((item, idx) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10, height: 0 }}
                transition={{ duration: 0.2 }}
                className="group flex items-center justify-between gap-3 p-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.07] border border-white/5 transition-all text-left"
              >
                <div className="flex items-start gap-2.5 min-w-0 flex-1">
                  <span className="shrink-0 flex items-center justify-center w-5 h-5 rounded-full bg-saffron-gold/15 text-saffron-gold text-[10px] font-mono font-bold mt-0.5">
                    {idx + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-white/90 line-clamp-2 leading-snug font-sans break-words">
                      {item.text}
                    </p>
                    {item.attachedFiles && item.attachedFiles.length > 0 && (
                      <div className="flex items-center gap-1 mt-1 text-[10px] text-white/50">
                        <Paperclip className="w-3 h-3 text-saffron-gold" />
                        <span>{item.attachedFiles.length} file attached</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 shrink-0 opacity-90 sm:opacity-75 sm:group-hover:opacity-100 transition-opacity">
                  <button
                    type="button"
                    onClick={() => onSendNow(item.id)}
                    title="Send now (interrupts current answer)"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-saffron-gold/20 hover:bg-saffron-gold/30 text-saffron-gold text-[11px] font-medium transition-all"
                  >
                    <Zap className="w-3 h-3 fill-current" />
                    <span className="hidden sm:inline">Send Now</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => onEdit(item.id)}
                    title="Edit message"
                    className="p-1.5 rounded-lg hover:bg-white/10 text-white/60 hover:text-white transition-colors"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>

                  <button
                    type="button"
                    onClick={() => onRemove(item.id)}
                    title="Remove from queue"
                    className="p-1.5 rounded-lg hover:bg-rose-500/20 text-white/60 hover:text-rose-400 transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  );
};
