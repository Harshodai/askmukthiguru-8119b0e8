import { useTranslation } from 'react-i18next';
import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';
import { useOptionalAuth } from '@/hooks/useOptionalAuth';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { usePageMeta } from '@/hooks/usePageMeta';
import { ArrowRight, Sparkles, RefreshCw } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { BACKEND_URL } from '@/lib/backendUrl';
import { requestBackendHealth } from '@/lib/chat/health';
import { DISCLAIMER_ACCEPTED_EVENT, isDisclaimerAccepted } from '@/components/common/SafetyDisclaimer';
import { cn } from '@/lib/utils';
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
const ONBOARDED_KEY = 'askmukthiguru_onboarded';

const BackendHealthBanner = () => {
  const initialHealth = useBackendHealth();
  const { t } = useTranslation();
  const [health, setHealth] = useState(initialHealth);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    setHealth(initialHealth);
  }, [initialHealth]);

  if (health !== 'degraded' && health !== 'unreachable') return null;

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const status = await requestBackendHealth(`${BACKEND_URL}/api/chat`, AbortSignal.timeout(6000));
      setHealth(status);
      if (status === 'ok') {
        // ChatInterface owns the last-message retry and its request state.
        window.dispatchEvent(new Event('chat:retry-last'));
      }
    } catch {
      setHealth('unreachable');
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      role="status"
      className="w-full bg-ojas/10 border-b border-ojas/30 text-foreground px-4 py-2.5 shadow-sm transition-all"
    >
      <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-2.5 text-xs text-center sm:text-left">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-500 motion-safe:animate-pulse shrink-0" />
          <span>
            {health === 'degraded'
              ? t('chat.backendDegraded', 'The teaching service is currently reconnecting. Saved conversations and all meditative practices remain fully available.')
              : t('chat.backendUnreachable', 'AskMukthiGuru cannot reach its teaching service right now. Meditative practices and your saved conversations still work.')}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Link
            to="/practices/serene-mind"
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-ojas text-primary-foreground font-medium hover:bg-ojas-light transition-colors text-[11px]"
          >
            <Sparkles className="w-3 h-3" />
            <span>{t('chat.tryPracticeFallback', 'Start 3-Min Practice')}</span>
          </Link>
          <button
            type="button"
            onClick={handleRetry}
            disabled={retrying}
            aria-label={retrying ? t('chat.checkingHealth', 'Checking service') : t('chat.checkService', 'Check service')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-background/80 hover:bg-background border border-border/50 text-muted-foreground hover:text-foreground transition-colors text-[11px]"
          >
            <RefreshCw className={cn("w-3 h-3", retrying && "motion-safe:animate-spin")} />
            <span>{retrying ? t('chat.checkingHealth', 'Checking…') : t('chat.checkService', 'Check service')}</span>
          </button>
        </div>
      </div>
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

  // Auto-show the tour once for a new authenticated user. Dismissing the tour
  // counts as onboarding so a returning user is never trapped by a recurring
  // modal; the explicit "Take a Tour" action clears both keys and restarts it.
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

    // Show tour for authenticated users only; never prompt anonymous users to onboard.
    // Wait for SafetyDisclaimer acceptance so first-run overlays never stack.
    const shouldShow = !!user && !tourDone && !onboarded;
    if (shouldShow) {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const scheduleTour = () => {
        localStorage.setItem(ONBOARDED_KEY, '1');
        localStorage.setItem(TOUR_SHOWN_COUNT_KEY, '1');
        // Small delay so the chat UI renders before the tour positions itself
        timer = setTimeout(() => setTourOpen(true), 600);
      };
      if (isDisclaimerAccepted()) {
        scheduleTour();
        return () => clearTimeout(timer);
      }
      window.addEventListener(DISCLAIMER_ACCEPTED_EVENT, scheduleTour, { once: true });
      return () => {
        window.removeEventListener(DISCLAIMER_ACCEPTED_EVENT, scheduleTour);
        clearTimeout(timer);
      };
    }
  }, [loading, user]);

  // Listen for 'tour:restart' custom event (dispatched by UserMenu "Take a Tour")
  useEffect(() => {
    const handleRestartTour = () => {
      localStorage.removeItem(TOUR_COMPLETED_KEY);
      localStorage.removeItem(TOUR_SHOWN_COUNT_KEY);
      localStorage.removeItem(ONBOARDED_KEY);
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

  /** Skip / Escape — persist dismissal so it does not interrupt later sessions. */
  const handleTourDismiss = () => {
    localStorage.setItem(ONBOARDED_KEY, '1');
    localStorage.setItem(TOUR_COMPLETED_KEY, '1');
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

  // No `loading` gate here: useOptionalAuth() resolves async and its anon-session
  // mint can wait on a cold backend, so a full-screen spinner used to replace the
  // whole chat — composer included — indefinitely. The UI renders immediately and
  // auth resolves in the background; the effects above already wait on `loading`.
  return (
    <PrePracticeGate>
      <h1 className="sr-only">{t('chat.srOnlyTitle')}</h1>
      {/* The banner is a sibling of a full-height ChatInterface, so it has to
          share the viewport with it — otherwise it pushes the chat (and the
          sidebar footer / user menu) below the fold whenever it appears. */}
      <div className="h-dvh max-h-dvh flex flex-col overflow-hidden">
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
