import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Trash2, Flame, ArrowLeft, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { 
  Message, 
  generateId, 
  saveChatHistory, 
  loadChatHistory, 
  clearChatHistory,
  getPlaceholderResponse 
} from '@/lib/chatStorage';
import { ChatMessage } from './ChatMessage';
import { SereneMindModal } from './SereneMindModal';
import { FloatingParticles } from '../landing/FloatingParticles';

export const ChatInterface = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showSereneMind, setShowSereneMind] = useState(false);
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

    // Simulate AI response delay
    setTimeout(() => {
      const guruMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: getPlaceholderResponse(),
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, guruMessage]);
      setIsTyping(false);
    }, 1500 + Math.random() * 1000);
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
      <header className="relative z-20 glass-card mx-4 mt-4 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link 
              to="/" 
              className="p-2 rounded-full hover:bg-muted/50 transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-tejas" />
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-ojas/30 to-prana/30 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-ojas" />
              </div>
              <div>
                <h1 className="font-semibold text-tejas">Sri Preethaji & Sri Krishnaji</h1>
                <p className="text-xs text-muted-foreground">Your Spiritual Guides</p>
              </div>
            </div>
          </div>
          <button
            onClick={handleClearChat}
            className="p-2 rounded-full hover:bg-destructive/20 transition-colors group"
            title="Clear chat history"
          >
            <Trash2 className="w-5 h-5 text-muted-foreground group-hover:text-destructive transition-colors" />
          </button>
        </div>
      </header>

      {/* Messages Area */}
      <main className="relative z-10 flex-1 overflow-y-auto px-4 py-6 scrollbar-spiritual">
        <div className="max-w-3xl mx-auto space-y-4">
          <AnimatePresence mode="popLayout">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
          </AnimatePresence>

          {/* Typing Indicator */}
          {isTyping && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-start gap-3"
            >
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-ojas/30 to-prana/30 flex items-center justify-center flex-shrink-0">
                <Sparkles className="w-4 h-4 text-ojas" />
              </div>
              <div className="glass-card px-4 py-3 rounded-2xl rounded-tl-sm">
                <div className="flex gap-1">
                  <motion.div
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0 }}
                    className="w-2 h-2 rounded-full bg-ojas"
                  />
                  <motion.div
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.2 }}
                    className="w-2 h-2 rounded-full bg-ojas"
                  />
                  <motion.div
                    animate={{ opacity: [0.4, 1, 0.4] }}
                    transition={{ duration: 1.5, repeat: Infinity, delay: 0.4 }}
                    className="w-2 h-2 rounded-full bg-ojas"
                  />
                </div>
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Input Area */}
      <footer className="relative z-20 px-4 pb-4">
        <div className="max-w-3xl mx-auto">
          {/* Serene Mind Button */}
          <div className="flex justify-center mb-3">
            <button
              onClick={() => setShowSereneMind(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-full bg-prana/20 hover:bg-prana/30 border border-prana/30 transition-all duration-300 hover:scale-105 group"
            >
              <Flame className="w-4 h-4 text-ojas group-hover:animate-pulse" />
              <span className="text-sm text-tejas">Feeling stressed? Try Serene Mind</span>
            </button>
          </div>

          {/* Input Form */}
          <form onSubmit={handleSubmit} className="glass-card p-3">
            <div className="flex items-end gap-3">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Share what's on your heart..."
                rows={1}
                className="flex-1 bg-transparent border-none outline-none resize-none text-tejas placeholder:text-muted-foreground/50 py-2 px-2 max-h-32 scrollbar-spiritual"
                style={{ minHeight: '44px' }}
              />
              <button
                type="submit"
                disabled={!inputValue.trim() || isTyping}
                className="p-3 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </form>

          <p className="text-center text-xs text-muted-foreground/50 mt-2">
            AI companion based on spiritual teachings. Not a replacement for professional guidance.
          </p>
        </div>
      </footer>

      {/* Serene Mind Modal */}
      <SereneMindModal isOpen={showSereneMind} onClose={() => setShowSereneMind(false)} />
    </div>
  );
};
