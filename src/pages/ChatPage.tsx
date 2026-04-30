import { ChatInterface } from '@/components/chat/ChatInterface';
import { PrePracticeGate } from '@/components/chat/PrePracticeGate';

const ChatPage = () => {
  return (
    <PrePracticeGate>
      <ChatInterface />
    </PrePracticeGate>
  );
};

export default ChatPage;
