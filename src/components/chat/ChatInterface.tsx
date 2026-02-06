import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Flame } from 'lucide-react';
import { 
  Message, 
  generateId, 
  saveChatHistory, 
  loadChatHistory, 
  clearChatHistory,
} from '@/lib/chatStorage';
import { sendMessage, MessagePayload } from '@/lib/aiService';
import { ChatMessage } from './ChatMessage';
import { ChatHeader } from './ChatHeader';
import { SereneMindModal } from './SereneMindModal';
import { MobileConversationSheet } from './MobileConversationSheet';
import { LanguageSelector } from './LanguageSelector';
import { FloatingParticles } from '../landing/FloatingParticles';

export const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showSereneMind, setShowSereneMind] = useState(false);
  const [showMobileSheet, setShowMobileSheet] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load chat history on mount
  useEffect(() => {
    const history = loadChatHistory();
    if (history.length > 0) {
      setMessages(history);
    } else {
      // Add welcome message
      const welcomeMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: 'Namaste, dear seeker. I am here to guide you toward your beautiful state. What brings you here today? Share what is in your heart, and together we shall explore the path to inner peace.',
        timestamp: new Date(),
      };
      setMessages([welcomeMessage]);
    }
  }, []);

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      saveChatHistory(messages);
    }
  }, [messages]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isTyping) return;

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    // Convert messages to API format
    const messageHistory: MessagePayload[] = messages.map((m) => ({
      role: m.role === 'guru' ? 'assistant' : 'user',
      content: m.content,
    }));

    try {
      const response = await sendMessage(messageHistory, userMessage.content);
      
      const guruMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: response.content,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, guruMessage]);
    } catch (error) {
      console.error('Error getting response:', error);
    } finally {
      setIsTyping(false);
    }
  };

  const handleClearChat = () => {
    clearChatHistory();
    const welcomeMessage: Message = {
      id: generateId(),
      role: 'guru',
      content: 'The slate is clean, dear one. Let us begin anew. What would you like to explore?',
      timestamp: new Date(),
    };
    setMessages([welcomeMessage]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-background relative overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 bg-spiritual-gradient" />
      <FloatingParticles />

      {/* Header */}
      <ChatHeader 
        onClearChat={handleClearChat}
        onOpenMobileMenu={() => setShowMobileSheet(true)}
      />

      {/* Messages Area */}
      <main className="relative z-10 flex-1 overflow-y-auto px-4 py-6 scrollbar-spiritual">
        <div className="max-w-3xl mx-auto space-y-4">
          <AnimatePresence mode="popLayout">
            {messages.map((message, index) => (
              <ChatMessage 
                key={message.id} 
                message={message} 
                index={index}
              />
            ))}
          </AnimatePresence>

          {/* Typing Indicator */}
          <AnimatePresence>
            {isTyping && (
              <motion.div
                initial={{ opacity: 0, y: 10, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="flex items-start gap-3"
              >
                <motion.div 
                  className="w-8 h-8 rounded-full bg-gradient-to-br from-ojas/30 to-prana/30 flex items-center justify-center flex-shrink-0"
                  animate={{ scale: [1, 1.1, 1] }}
                  transition={{ duration: 2, repeat: Infinity }}
                >
                  <div className="w-4 h-4 rounded-full bg-ojas/50" />
                </motion.div>
                <div className="glass-card px-4 py-3 rounded-2xl rounded-tl-sm">
                  <div className="flex gap-1.5">
                    {[0, 0.15, 0.3].map((delay, i) => (
                      <motion.div
                        key={i}
                        animate={{ 
                          y: [0, -6, 0],
                          opacity: [0.4, 1, 0.4] 
                        }}
                        transition={{ 
                          duration: 0.8, 
                          repeat: Infinity, 
                          delay 
                        }}
                        className="w-2 h-2 rounded-full bg-ojas"
                      />
                    ))}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Input Area */}
      <footer className="relative z-20 px-4 pb-4 pb-safe">
        <div className="max-w-3xl mx-auto">
          {/* Serene Mind Button */}
          <motion.div 
            className="flex justify-center mb-3"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <button
              onClick={() => setShowSereneMind(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-prana/20 hover:bg-prana/30 border border-prana/30 transition-all duration-300 hover:scale-105 group"
            >
              <Flame className="w-4 h-4 text-ojas group-hover:animate-pulse" />
              <span className="text-sm text-tejas">Feeling stressed? Try Serene Mind</span>
            </button>
          </motion.div>

          {/* Input Form */}
          <motion.form 
            onSubmit={handleSubmit} 
            className={`glass-card p-3 transition-all duration-300 ${
              inputFocused ? 'ring-2 ring-ojas/50 glow-gold' : ''
            }`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <div className="flex items-end gap-3">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => setInputFocused(true)}
                onBlur={() => setInputFocused(false)}
                placeholder="Share what's on your heart..."
                rows={1}
                className="flex-1 bg-transparent border-none outline-none resize-none text-tejas placeholder:text-muted-foreground/50 py-2 px-2 max-h-32 scrollbar-spiritual"
                style={{ minHeight: '44px' }}
              />
              <motion.button
                type="submit"
                disabled={!inputValue.trim() || isTyping}
                className="p-3 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                animate={inputValue.trim() ? { scale: [1, 1.05, 1] } : {}}
                transition={{ duration: 0.3 }}
              >
                <Send className="w-5 h-5" />
              </motion.button>
            </div>

            {/* Language & Voice Controls */}
            <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/30">
              <LanguageSelector 
                voiceEnabled={voiceEnabled}
                onVoiceToggle={() => setVoiceEnabled(!voiceEnabled)}
              />
              <p className="text-xs text-muted-foreground/50 hidden sm:block">
                AI companion • Not a replacement for professional guidance
              </p>
            </div>
          </motion.form>

          <p className="text-center text-xs text-muted-foreground/50 mt-2 sm:hidden">
            AI companion • Not a replacement for professional guidance
          </p>
        </div>
      </footer>

      {/* Mobile Conversation Sheet */}
      <MobileConversationSheet
        isOpen={showMobileSheet}
        onClose={() => setShowMobileSheet(false)}
        onNewConversation={handleClearChat}
        onOpenSereneMind={() => setShowSereneMind(true)}
      />

      {/* Serene Mind Modal */}
      <SereneMindModal isOpen={showSereneMind} onClose={() => setShowSereneMind(false)} />
    </div>
  );
};
