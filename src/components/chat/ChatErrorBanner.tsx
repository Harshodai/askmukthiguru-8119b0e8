import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, ChevronDown, ChevronUp, LogIn, RefreshCw, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { chatErrorBus, type ChatBusError } from '@/lib/chatErrorBus';
import { ErrorCodePanel } from './ErrorCodePanel';

interface ChatErrorBannerProps {
  onRetry?: () => void;
}

export const ChatErrorBanner = ({ onRetry }: ChatErrorBannerProps) => {
  const [err, setErr] = useState<ChatBusError | null>(null);
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();

  useEffect(() => chatErrorBus.subscribe(setErr), []);
  useEffect(() => { setExpanded(false); }, [err?.id]);

  const isAuth = err?.kind === 'unauthorized';

  return (
    <AnimatePresence>
      {err && (
        <motion.div
          key={err.id}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.18 }}
          className="relative z-10 border-b border-destructive/20 bg-destructive/[0.06] backdrop-blur-sm"
          role="status"
          aria-live="polite"
        >
          <div className="max-w-3xl mx-auto px-3 sm:px-4 py-2 flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-destructive shrink-0 mt-0.5" aria-hidden />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-mono text-[10px] font-semibold text-destructive/90 tracking-wide">{err.code}</span>
                <p className="text-[13px] text-foreground/90 font-medium truncate">{err.title}</p>
              </div>
              <p className="text-[12px] text-foreground/70 mt-0.5 line-clamp-2">{err.summary}</p>

              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                {isAuth ? (
                  <button
                    type="button"
                    onClick={() => navigate('/auth?redirect=/chat')}
                    className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:bg-destructive/10 rounded-md px-2 py-0.5 transition-colors"
                  >
                    <LogIn className="w-3 h-3" /> Sign in again
                  </button>
                ) : (
                  err.retryable && onRetry && (
                    <button
                      type="button"
                      onClick={() => { onRetry(); chatErrorBus.dismiss(); }}
                      className="inline-flex items-center gap-1 text-[11px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:bg-destructive/10 rounded-md px-2 py-0.5 transition-colors"
                    >
                      <RefreshCw className="w-3 h-3" /> Retry last message
                    </button>
                  )
                )}
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
                  aria-expanded={expanded}
                >
                  {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  {expanded ? 'Hide details' : 'Details'}
                </button>
              </div>

              <AnimatePresence>
                {expanded && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.18 }}
                    className="mt-2 overflow-hidden"
                  >
                    <ErrorCodePanel error={err} compact />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <button
              type="button"
              onClick={() => chatErrorBus.dismiss()}
              className="text-muted-foreground hover:text-foreground transition-colors p-0.5 shrink-0"
              aria-label="Dismiss"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
