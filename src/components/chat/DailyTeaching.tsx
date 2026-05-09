import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Sparkles } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

export interface DailyTeachingData {
  id: string;
  imageUrl: string;
  caption?: string;
}

// Dismissed teachings are tracked by id, so a fresh upload re-shows the banner.
const DISMISSED_KEY = 'askmukthiguru_teaching_dismissed_id';

export const DailyTeaching = () => {
  const [teaching, setTeaching] = useState<DailyTeachingData | null>(null);
  const [dismissedId, setDismissedId] = useState<string | null>(
    () => localStorage.getItem(DISMISSED_KEY),
  );

  const fetchTeaching = useCallback(async () => {
    const { data, error } = await supabase
      .from('daily_teachings')
      .select('id, image_url, caption')
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error || !data) return;

    setTeaching({
      id: data.id,
      imageUrl: data.image_url,
      caption: data.caption ?? undefined,
    });
  }, []);

  useEffect(() => {
    fetchTeaching();

    // Realtime: when a new daily teaching is uploaded, refetch immediately
    // so all open chat sessions update without a reload.
    const channel = supabase
      .channel('daily-teachings-feed')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'daily_teachings' },
        () => {
          fetchTeaching();
        },
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetchTeaching]);

  const handleDismiss = () => {
    if (!teaching) return;
    setDismissedId(teaching.id);
    localStorage.setItem(DISMISSED_KEY, teaching.id);
  };

  if (!teaching || teaching.id === dismissedId) return null;

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
          <button
            onClick={handleDismiss}
            className="absolute top-2.5 right-2.5 z-10 p-1 rounded-full bg-background/70 backdrop-blur-sm hover:bg-background transition-colors"
            aria-label="Dismiss teaching"
          >
            <X className="w-3.5 h-3.5 text-muted-foreground" />
          </button>

          <div className="relative aspect-[16/7] overflow-hidden">
            <img
              src={teaching.imageUrl}
              alt="Today's teaching from the Gurus"
              className="w-full h-full object-cover"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-card/90 via-transparent to-transparent" />
          </div>

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
