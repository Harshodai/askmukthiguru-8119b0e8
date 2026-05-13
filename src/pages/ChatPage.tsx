import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { usePageMeta } from '@/hooks/usePageMeta';
import { Loader2 } from 'lucide-react';

const ChatPage = () => {
  const { loading } = useRequireAuth();
  usePageMeta({
    title: 'Chat with the Guru — AskMukthiGuru',
    description: 'Have a private, AI-guided spiritual conversation rooted in the teachings of Sri Preethaji & Sri Krishnaji.',
    canonical: 'https://askmukthiguru.lovable.app/chat',
  });

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
      <ChatInterface />
    </PrePracticeGate>
  );
};

export default ChatPage;
