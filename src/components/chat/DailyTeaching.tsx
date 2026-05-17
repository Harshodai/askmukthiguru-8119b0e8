import { useState, useEffect, useCallback, useRef } from 'react';
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
  const [imageError, setImageError] = useState(false);
  const [dismissedId, setDismissedId] = useState<string | null>(
    () => localStorage.getItem(DISMISSED_KEY),
  );
  const retryCount = useRef(0);

  const fetchTeaching = useCallback(async () => {
    const now = new Date().toISOString();
    const { data, error } = await supabase
      .from('daily_teachings')
      .select('id, image_url, caption')
      .or(`expires_at.is.null,expires_at.gte.${now}`)   // skip expired
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      console.warn('[DailyTeaching] Fetch error:', error.message);
      // Retry up to 3 times — RLS may reject if auth session isn't ready yet
      if (retryCount.current < 3) {
        retryCount.current += 1;
        setTimeout(() => fetchTeaching(), 2000 * retryCount.current);
      }
      return;
    }

    if (!data) {
      console.debug('[DailyTeaching] No active teaching found.');
      // If no data and auth might not be ready, retry once after a delay
      if (retryCount.current < 2) {
        retryCount.current += 1;
        setTimeout(() => fetchTeaching(), 2500);
      }
      return;
    }

    console.debug('[DailyTeaching] Loaded:', data.id, data.caption?.slice(0, 40));
    retryCount.current = 0;

    // If a NEW teaching arrived, clear the old dismissed state
    const oldDismissed = localStorage.getItem(DISMISSED_KEY);
    if (oldDismissed && oldDismissed !== data.id) {
      localStorage.removeItem(DISMISSED_KEY);
      setDismissedId(null);
    }

    setImageError(false);
    setTeaching({
      id: data.id,
      imageUrl: data.image_url,
      caption: data.caption ?? undefined,
    });
  }, []);


  useEffect(() => {
    fetchTeaching();

    // Re-fetch after auth state changes (login completes after component mount)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        retryCount.current = 0;
        fetchTeaching();
      }
    });

    // Realtime: when a new daily teaching is uploaded, refetch immediately
    // so all open chat sessions update without a reload.
    const channel = supabase
      .channel('daily-teachings-feed')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'daily_teachings' },
        () => {
          retryCount.current = 0;
          fetchTeaching();
        },
      )
      .subscribe();

    const handleMeditationCompleted = () => {
      localStorage.removeItem(DISMISSED_KEY);
      setDismissedId(null);
      retryCount.current = 0;
      fetchTeaching();
    };

    window.addEventListener('askmukthiguru:meditation_completed', handleMeditationCompleted);

    return () => {
      subscription.unsubscribe();
      supabase.removeChannel(channel);
      window.removeEventListener('askmukthiguru:meditation_completed', handleMeditationCompleted);
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

          <div className="relative aspect-[16/7] overflow-hidden bg-muted/20">
            {imageError ? (
              <div className="w-full h-full bg-gradient-to-tr from-indigo-950/80 via-purple-900/60 to-amber-900/40 flex items-center justify-center pointer-events-none">
                <Sparkles className="w-12 h-12 text-amber-500/20 animate-pulse" />
              </div>
            ) : (
              <picture>
                <source 
                  srcSet={`${teaching.imageUrl}?transform=1&format=webp&width=800 800w, ${teaching.imageUrl}?transform=1&format=webp&width=400 400w`} 
                  type="image/webp" 
                  sizes="(max-width: 600px) 400px, 800px" 
                />
                <img
                  src={teaching.imageUrl}
                  alt="Today's teaching from the Gurus"
                  className="w-full h-full object-cover transition-opacity duration-700 ease-in-out"
                  loading="lazy"
                  decoding="async"
                  onError={() => {
                    console.warn('[DailyTeaching] Image failed to load:', teaching.imageUrl);
                    setImageError(true);
                  }}
                />
              </picture>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-card/90 via-transparent to-transparent pointer-events-none" />
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
