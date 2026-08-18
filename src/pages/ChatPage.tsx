import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';
import { useOptionalAuth } from '@/hooks/useOptionalAuth';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Loader2, ArrowRight } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { GuidedTour } from '@/components/onboarding/GuidedTour';
import { PRODUCTION_DOMAIN, PRODUCTION_OG_IMAGE, buildCanonical } from '@/lib/domain';

const LAST_SEEN_KEY = 'askmukthiguru_last_seen';
const TOUR_COMPLETED_KEY = 'askmukthiguru_tour_completed';
const TOUR_SHOWN_COUNT_KEY = 'askmukthiguru_tour_shown_count';
const TOUR_MAX_SHOWS = 3;
const ONBOARDED_KEY = 'askmukthiguru_onboarded';

const BackendHealthBanner = () => {
  const health = useBackendHealth();
  if (health !== 'degraded') return null;
  return (
    <div className="w-full bg-amber-500/15 border-b border-amber-500/30 text-amber-900 dark:text-amber-200 text-xs px-4 py-2 text-center">
      ⚠️ The Guru is waking up — responses may be slower than usual for the next minute.
    </div>
  );
};

const ChatPage = () => {
  const { t } = useTranslation();
  const { loading, user, mode } = useOptionalAuth();
  const isAnonymous = mode === 'anonymous';
  const [tourOpen, setTourOpen] = useState(false);
  const [showContinuePrompt, setShowContinuePrompt] = useState(false);
  const [lastConversationId, setLastConversationId] = useState<string | null>(null);
  const navigate = useNavigate();
  usePageMeta({
    title: t('chat.pageTitle'),
    description: t('chat.pageDescription'),
    canonical: buildCanonical('/chat'),
    ogType: 'website',
    ogImage: PRODUCTION_OG_IMAGE,
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      name: 'AskMukthiGuru Chat',
      url: buildCanonical('/chat'),
      applicationCategory: 'LifestyleApplication',
      operatingSystem: 'Web',
      description: 'AI-guided spiritual conversations rooted in the teachings of Sri Preethaji & Sri Krishnaji',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    },
  });

  // Auto-show tour for new / returning users who haven't completed it
  useEffect(() => {
    if (loading) return;
    // Demo mode only when explicitly enabled at build time — never via
    // query string or localStorage (was an auth-bypass vector in dev).
    if (import.meta.env.VITE_ENABLE_DEMO_AUTH === 'true' && (window.location.search.includes('demo=true') || localStorage.getItem('demo_mode') === 'true')) {
      setTourOpen(false);
      return;
    }
    const onboarded = localStorage.getItem(ONBOARDED_KEY) === '1';
    const tourDone = localStorage.getItem(TOUR_COMPLETED_KEY) === '1';
    const shownCount = parseInt(localStorage.getItem(TOUR_SHOWN_COUNT_KEY) || '0', 10);

    // Show tour for authenticated users only; never prompt anonymous users to onboard.
    const shouldShow = !!user && !tourDone && shownCount < TOUR_MAX_SHOWS;
    if (shouldShow) {
      localStorage.setItem(TOUR_SHOWN_COUNT_KEY, String(shownCount + 1));
      // Small delay so the chat UI renders before the tour positions itself
      const t = setTimeout(() => setTourOpen(true), 600);
      return () => clearTimeout(t);
    }
  }, [loading, user]);

  // Listen for 'tour:restart' custom event (dispatched by UserMenu "Take a Tour")
  useEffect(() => {
    const handleRestartTour = () => {
      localStorage.removeItem(TOUR_COMPLETED_KEY);
      localStorage.removeItem(TOUR_SHOWN_COUNT_KEY);
      setTourOpen(false);
      // Re-open after a tick so state resets cleanly
      setTimeout(() => setTourOpen(true), 80);
    };
    window.addEventListener('tour:restart', handleRestartTour);
    return () => window.removeEventListener('tour:restart', handleRestartTour);
  }, []);

  /** "Got it" — the user finished the tour; never show it again. */
  const handleTourComplete = () => {
    localStorage.setItem(TOUR_COMPLETED_KEY, '1');
    setTourOpen(false);
  };

  /** Skip / Escape — dismiss without confirming, so it can re-show next visit. */
  const handleTourDismiss = () => {
    setTourOpen(false);
  };

  useEffect(() => {
    if (loading || isAnonymous) return;
    const checkMultiDevice = async () => {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) {
        localStorage.removeItem(LAST_SEEN_KEY);
        return;
      }
      const { data: profile } = await supabase
        .from('profiles')
        .select('last_active_at, last_conversation_id, last_message_id')
        .eq('id', session.user.id)
        .single();
      if (!profile?.last_conversation_id || !profile.last_active_at || !profile.last_message_id) return;
      const serverLastActive = new Date(profile.last_active_at).getTime();
      const localLastSeen = parseInt(localStorage.getItem(LAST_SEEN_KEY) || '0', 10);
      if (serverLastActive > localLastSeen) {
        setLastConversationId(profile.last_conversation_id);
        setShowContinuePrompt(true);
      }
      localStorage.setItem(LAST_SEEN_KEY, Date.now().toString());
    };
    checkMultiDevice();
  }, [loading, isAnonymous]);

  const handleContinue = () => {
    if (lastConversationId) {
      navigate(`/chat?conversation=${lastConversationId}`);
    }
    setShowContinuePrompt(false);
  };

  const handleDismiss = () => {
    setShowContinuePrompt(false);
  };

  if (loading) {
    return (
      <div className="h-dvh flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 text-ojas animate-spin" />
          <p className="text-sm text-muted-foreground">{t('chat.loadingSession')}</p>
        </div>
      </div>
    );
  }

  return (
    <PrePracticeGate>
      <h1 className="sr-only">{t('chat.srOnlyTitle')}</h1>
      {/* The banner is a sibling of a full-height ChatInterface, so it has to
          share the viewport with it — otherwise it pushes the chat (and the
          sidebar footer / user menu) below the fold whenever it appears. */}
      <div className="h-dvh flex flex-col">
        <BackendHealthBanner />
        <ChatInterface />
      </div>
      <GuidedTour isOpen={tourOpen} onComplete={handleTourComplete} onDismiss={handleTourDismiss} />
      <Dialog open={showContinuePrompt} onOpenChange={setShowContinuePrompt}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader className="gap-2">
            <DialogTitle className="text-center">{t('chat.continueTitle')}</DialogTitle>
            <DialogDescription className="text-center">
              {t('chat.continueDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col sm:flex-row gap-3 mt-4">
            <Button variant="outline" onClick={handleDismiss} className="flex-1">
              {t('chat.stayHere')}
            </Button>
            <Button onClick={handleContinue} className="flex-1 bg-ojas hover:bg-ojas-light gap-2">
              {t('chat.continueBtn')} <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </PrePracticeGate>
  );
};

export default ChatPage;
