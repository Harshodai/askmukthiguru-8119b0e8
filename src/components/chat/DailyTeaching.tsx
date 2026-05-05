import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Sparkles } from 'lucide-react';

export interface DailyTeachingData {
  id: string;
  imageUrl: string;
  caption?: string;
  date: string; // ISO date string
}

const TEACHING_STORAGE_KEY = 'askmukthiguru_daily_teaching';
const DISMISSED_KEY = 'askmukthiguru_teaching_dismissed';

/** Admin sets teaching via localStorage for now; will migrate to DB later */
export const setDailyTeaching = (teaching: DailyTeachingData): void => {
  localStorage.setItem(TEACHING_STORAGE_KEY, JSON.stringify(teaching));
};

export const getDailyTeaching = (): DailyTeachingData | null => {
  try {
    const raw = localStorage.getItem(TEACHING_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const DailyTeaching = () => {
  const [teaching, setTeaching] = useState<DailyTeachingData | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const data = getDailyTeaching();
    if (!data) return;
    const today = new Date().toISOString().slice(0, 10);
    const dismissedDate = localStorage.getItem(DISMISSED_KEY);
    if (dismissedDate === today) {
      setDismissed(true);
      return;
    }
    setTeaching(data);
  }, []);

  const handleDismiss = () => {
    setDismissed(true);
    const today = new Date().toISOString().slice(0, 10);
    localStorage.setItem(DISMISSED_KEY, today);
  };

  if (dismissed || !teaching) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -12, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -12, scale: 0.97 }}
        className="mx-auto max-w-2xl mb-4"
        data-testid="daily-teaching"
      >
        <div className="relative rounded-2xl overflow-hidden border border-ojas/20 shadow-lg bg-card/90 backdrop-blur-sm">
          {/* Close */}
          <button
            onClick={handleDismiss}
            className="absolute top-2.5 right-2.5 z-10 p-1 rounded-full bg-background/70 backdrop-blur-sm hover:bg-background transition-colors"
            aria-label="Dismiss teaching"
          >
            <X className="w-3.5 h-3.5 text-muted-foreground" />
          </button>

          {/* Image */}
          <div className="relative aspect-[16/7] overflow-hidden">
            <img
              src={teaching.imageUrl}
              alt="Today's teaching from the Gurus"
              className="w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-card/90 via-transparent to-transparent" />
          </div>

          {/* Caption */}
          <div className="px-4 py-3 -mt-8 relative z-10">
            <div className="flex items-center gap-1.5 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-ojas" />
              <span className="text-[11px] font-medium text-ojas uppercase tracking-wider">
                Today&apos;s Teaching
              </span>
            </div>
            {teaching.caption && (
              <p className="text-sm text-foreground leading-relaxed line-clamp-2">
                {teaching.caption}
              </p>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
