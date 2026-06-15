import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';
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

const LAST_SEEN_KEY = 'askmukthiguru_last_seen';

const ChatPage = () => {
  const { loading, user } = useRequireAuth();
  const [showContinuePrompt, setShowContinuePrompt] = useState(false);
  const [lastConversationId, setLastConversationId] = useState<string | null>(null);
  const navigate = useNavigate();
  usePageMeta({
    title: 'Chat with the Guru — AskMukthiGuru',
    description: 'Have a private, AI-guided spiritual conversation rooted in the teachings of Sri Preethaji & Sri Krishnaji.',
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
        .select('last_active_at, last_conversation_id')
        .eq('id', session.user.id)
        .single();
      if (!profile?.last_conversation_id) return;
      const serverLastActive = new Date(profile.last_active_at).getTime();
      const localLastSeen = parseInt(localStorage.getItem(LAST_SEEN_KEY) || '0', 10);
      // Show prompt if server has newer activity than what this device last saw
      if (serverLastActive > localLastSeen) {
        setLastConversationId(profile.last_conversation_id);
        setShowContinuePrompt(true);
      }
      // Update local timestamp to now
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
          <p className="text-sm text-muted-foreground">Loading your session…</p>
        </div>
      </div>
    );
  }

  return (
    <PrePracticeGate>
      <h1 className="sr-only">Chat with your AI Spiritual Guide</h1>
      <ChatInterface />
      <Dialog open={showContinuePrompt} onOpenChange={setShowContinuePrompt}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader className="gap-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center mb-2">
              <MonitorCheck className="w-6 h-6 text-ojas" />
            </div>
            <DialogTitle className="text-center">Continue on this device?</DialogTitle>
            <DialogDescription className="text-center">
              It looks like you were recently active on another device.
              Pick up where you left off.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col sm:flex-row gap-3 mt-4">
            <Button variant="outline" onClick={handleDismiss} className="flex-1">
              Stay here
            </Button>
            <Button onClick={handleContinue} className="flex-1 bg-ojas hover:bg-ojas-light gap-2">
              Continue <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </PrePracticeGate>
  );
};

export default ChatPage;
