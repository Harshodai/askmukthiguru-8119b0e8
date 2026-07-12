import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Sparkles } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

export interface DailyTeachingData {
  id: string;
  imageUrl: string;
  caption?: string;
}

const DISMISSED_KEY = 'askmukthiguru_teaching_dismissed_id';

export const DailyTeaching = () => {
  const { t } = useTranslation();
  const [teaching, setTeaching] = useState<DailyTeachingData | null>(null);
  const [imageError, setImageError] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [dismissedId, setDismissedId] = useState<string | null>(
    () => localStorage.getItem(DISMISSED_KEY),
  );
  const retryCount = useRef(0);

  const fetchTeaching = useCallback(async () => {
    const now = new Date().toISOString();
    const { data, error } = await supabase
      .from('daily_teachings')
      .select('id, image_url, caption')
      .or(`expires_at.is.null,expires_at.gte.${now}`)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      console.warn('[DailyTeaching] Fetch error:', error.message);
      if (retryCount.current < 3) {
        retryCount.current += 1;
        setTimeout(() => fetchTeaching(), 2000 * retryCount.current);
      }
      return;
    }

    if (!data) {
      console.debug('[DailyTeaching] No active teaching found.');
      if (retryCount.current < 2) {
        retryCount.current += 1;
        setTimeout(() => fetchTeaching(), 2500);
      }
      return;
    }

    console.debug('[DailyTeaching] Loaded:', data.id, data.caption?.slice(0, 40));
    retryCount.current = 0;

    const oldDismissed = localStorage.getItem(DISMISSED_KEY);
    if (oldDismissed && oldDismissed !== data.id) {
      localStorage.removeItem(DISMISSED_KEY);
      setDismissedId(null);
    }

    setImageError(false);
    setTeaching({
      id: data.id,
      imageUrl: data.image_url,
      caption: data.caption ? data.caption.replace(/^\[Source:\s*[^\]]+\]\s*/i, '') : undefined,
    });

    const prePracticeCompleted = sessionStorage.getItem('askmukthiguru_pre_practice_asked') === '1';
    if (prePracticeCompleted && data.id !== oldDismissed) {
      setIsOpen(true);
    }
  }, []);

  useEffect(() => {
    fetchTeaching();

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        retryCount.current = 0;
        fetchTeaching();
      }
    });

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

    const handlePrePracticeCompleted = () => {
      const prePracticeCompleted = sessionStorage.getItem('askmukthiguru_pre_practice_asked') === '1';
      if (prePracticeCompleted) {
        setIsOpen(true);
      }
    };

    const handleMeditationCompleted = () => {
      localStorage.removeItem(DISMISSED_KEY);
      setDismissedId(null);
      retryCount.current = 0;
      fetchTeaching();
    };

    window.addEventListener('askmukthiguru:pre_practice_completed', handlePrePracticeCompleted);
    window.addEventListener('askmukthiguru:meditation_completed', handleMeditationCompleted);

    return () => {
      subscription.unsubscribe();
      supabase.removeChannel(channel);
      window.removeEventListener('askmukthiguru:pre_practice_completed', handlePrePracticeCompleted);
      window.removeEventListener('askmukthiguru:meditation_completed', handleMeditationCompleted);
    };
  }, [fetchTeaching]);

  const handleDismiss = () => {
    if (!teaching) return;
    setDismissedId(teaching.id);
    localStorage.setItem(DISMISSED_KEY, teaching.id);
    setIsOpen(false);
  };

  if (!teaching || teaching.id === dismissedId || !isOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[70] flex items-center justify-center p-4 bg-background/80 backdrop-blur-md animate-fade-in"
        onClick={handleDismiss}
        data-testid="daily-teaching-modal"
      >
        <motion.div
          initial={{ scale: 0.95, y: 20, opacity: 0 }}
          animate={{ scale: 1, y: 0, opacity: 1 }}
          exit={{ scale: 0.95, y: 20, opacity: 0 }}
          transition={{ type: 'spring', duration: 0.5 }}
          className="relative max-w-md w-full rounded-3xl overflow-hidden border border-ojas/30 bg-card/90 shadow-2xl backdrop-blur-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={handleDismiss}
            className="absolute top-4 right-4 z-20 p-2 rounded-full bg-background/60 hover:bg-background/90 text-foreground transition-all border border-border"
            aria-label={t('chat.closeTeachingModal')}
          >
            <X className="w-4 h-4" />
          </button>

          <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted/20">
            {imageError ? (
              <div className="w-full h-full bg-gradient-to-tr from-indigo-950 via-purple-950 to-amber-950/80 flex items-center justify-center pointer-events-none">
                <Sparkles className="w-16 h-16 text-ojas/30 animate-pulse" />
              </div>
            ) : (
              <picture>
                <source
                  srcSet={`${teaching.imageUrl}?transform=1&format=webp&width=600 600w`}
                  type="image/webp"
                  sizes="(max-width: 600px) 400px, 600px"
                />
                <img
                  src={teaching.imageUrl}
                  alt={t('chat.teachingAlt')}
                  className="w-full h-full object-cover transition-opacity duration-700 ease-in-out"
                  onError={() => setImageError(true)}
                  loading="eager"
                />
              </picture>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent pointer-events-none" />
          </div>

          <div className="p-6 sm:p-8 -mt-6 relative z-10">
            <div className="flex items-center gap-1.5 mb-3">
              <Sparkles className="w-4 h-4 text-ojas animate-pulse" />
              <span className="text-xs font-semibold text-ojas uppercase tracking-widest">
                {t('chat.todaysWisdom')}
              </span>
            </div>
            {teaching.caption && (
              <p className="text-base sm:text-lg text-foreground font-serif leading-relaxed italic mb-6">
                &ldquo;{teaching.caption}&rdquo;
              </p>
            )}

            <button
              onClick={handleDismiss}
              className="w-full py-3 px-4 rounded-xl bg-ojas hover:bg-ojas-light text-primary-foreground font-medium text-sm transition-all shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-ojas/50"
            >
              {t('chat.receiveWisdom')}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};
