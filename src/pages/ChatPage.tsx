import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';
import { MoodBanner } from '@/components/mood/MoodBanner';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Loader2, MonitorCheck, ArrowRight } from 'lucide-react';
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

const LAST_SEEN_KEY = 'askmukthiguru_last_seen';
const TOUR_COMPLETED_KEY = 'askmukthiguru_tour_completed';
const TOUR_SHOWN_COUNT_KEY = 'askmukthiguru_tour_shown_count';
const TOUR_MAX_SHOWS = 3;
const ONBOARDED_KEY = 'askmukthiguru_onboarded';

const ChatPage = () => {
  const { t } = useTranslation();
  const { loading, user } = useRequireAuth();
  const [tourOpen, setTourOpen] = useState(false);
  const [showContinuePrompt, setShowContinuePrompt] = useState(false);
  const [lastConversationId, setLastConversationId] = useState<string | null>(null);
  const navigate = useNavigate();
  usePageMeta({
    title: t('chat.pageTitle'),
    description: t('chat.pageDescription'),
    canonical: 'https://askmukthiguru.lovable.app/chat',
    ogType: 'website',
    ogImage: 'https://askmukthiguru.lovable.app/og-image.png',
    jsonLd: {
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      name: 'AskMukthiGuru Chat',
      url: 'https://askmukthiguru.lovable.app/chat',
      applicationCategory: 'LifestyleApplication',
      operatingSystem: 'Web',
      description: 'AI-guided spiritual conversations rooted in the teachings of Sri Preethaji & Sri Krishnaji',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    },
  });

  // Auto-show tour for new / returning users who haven't completed it
  useEffect(() => {
    if (loading) return;
    const onboarded = localStorage.getItem(ONBOARDED_KEY) === '1';
    const tourDone = localStorage.getItem(TOUR_COMPLETED_KEY) === '1';
    const shownCount = parseInt(localStorage.getItem(TOUR_SHOWN_COUNT_KEY) || '0', 10);

    // Show tour for:
    //  - any authenticated user who hasn't finished it yet, up to TOUR_MAX_SHOWS times
    //  - OR any user at all if tour was never shown (handles demo / product team)
    const shouldShow = (onboarded || !!user) && !tourDone && shownCount < TOUR_MAX_SHOWS;
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
    if (loading) return;
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
  }, [loading]);

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
      <MoodBanner />
      <ChatInterface />
      <GuidedTour isOpen={tourOpen} onComplete={handleTourComplete} onDismiss={handleTourDismiss} />
      <Dialog open={showContinuePrompt} onOpenChange={setShowContinuePrompt}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader className="gap-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center mb-2">
              <MonitorCheck className="w-6 h-6 text-ojas" />
            </div>
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
