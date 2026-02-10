import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Flame, AlertCircle } from 'lucide-react';
import { 
  Message, 
  Conversation,
  generateId, 
  saveConversation,
  loadConversation,
  loadConversations,
  createNewConversation,
  getConversationPreview,
  getCurrentConversationId,
  setCurrentConversationId,
} from '@/lib/chatStorage';
import { sendMessage, MessagePayload } from '@/lib/aiService';
import { ChatMessage } from './ChatMessage';
import { ChatHeader } from './ChatHeader';
import { SereneMindModal } from './SereneMindModal';
import { MobileConversationSheet } from './MobileConversationSheet';
import { DesktopSidebar } from './DesktopSidebar';
import { LanguageSelector } from './LanguageSelector';
import { FloatingParticles } from '../landing/FloatingParticles';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';
import { useToast } from '@/hooks/use-toast';

const WELCOME_MESSAGE = 'Namaste, dear seeker. I am here to guide you toward your beautiful state. What brings you here today? Share what is in your heart, and together we shall explore the path to inner peace.';

export const ChatInterface = () => {
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [showSereneMind, setShowSereneMind] = useState(false);
  const [showMobileSheet, setShowMobileSheet] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState('en');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastGuruMessageRef = useRef<string>('');
  const { toast } = useToast();

  // Text-to-Speech hook
  const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported } = useTextToSpeech({
    lang: currentLanguage,
    rate: 0.9,
  });

  // Initialize or load conversation on mount
  useEffect(() => {
    const currentId = getCurrentConversationId();
    let conversation: Conversation | null = null;

    if (currentId) {
      conversation = loadConversation(currentId);
    }

    if (!conversation) {
      // Check if there are any existing conversations
      const existingConversations = loadConversations();
      if (existingConversations.length > 0) {
        conversation = existingConversations[0];
      } else {
        conversation = createNewConversation();
      }
    }

    setCurrentConversation(conversation);
    
    if (conversation.messages.length > 0) {
      setMessages(conversation.messages);
    } else {
      // Add welcome message
      const welcomeMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: WELCOME_MESSAGE,
        timestamp: new Date(),
      };
      setMessages([welcomeMessage]);
    }

    setCurrentConversationId(conversation.id);
  }, []);

  // Auto-speak new guru messages when TTS is enabled
  useEffect(() => {
    if (!ttsEnabled || messages.length === 0) return;
    
    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role === 'guru' && lastMessage.content !== lastGuruMessageRef.current) {
      lastGuruMessageRef.current = lastMessage.content;
      speak(lastMessage.content);
    }
  }, [messages, ttsEnabled, speak]);

  // Voice recognition hook
  const {
    transcript,
    interimTranscript,
    isListening,
    isSupported: voiceSupported,
    error: voiceError,
    startListening,
    stopListening,
    resetTranscript,
  } = useSpeechRecognition({
    lang: currentLanguage,
    onTranscript: (text, isFinal) => {
      if (isFinal) {
        setInputValue(prev => prev + text + ' ');
        resetTranscript();
      }
    },
    onError: (error) => {
      toast({
        title: 'Voice Error',
        description: error,
        variant: 'destructive',
      });
      setVoiceEnabled(false);
    },
  });

  // Handle voice mode toggle
  const handleVoiceToggle = useCallback(() => {
    if (!voiceSupported) {
      toast({
        title: 'Voice Not Supported',
        description: 'Your browser does not support voice recognition.',
        variant: 'destructive',
      });
      return;
    }

    if (voiceEnabled) {
      stopListening();
      setVoiceEnabled(false);
    } else {
      startListening();
      setVoiceEnabled(true);
    }
  }, [voiceEnabled, voiceSupported, startListening, stopListening, toast]);

  // Handle TTS toggle
  const handleTtsToggle = useCallback(() => {
    if (!ttsSupported) {
      toast({
        title: 'Text-to-Speech Not Supported',
        description: 'Your browser does not support text-to-speech.',
        variant: 'destructive',
      });
      return;
    }

    if (ttsEnabled) {
      stopSpeaking();
      setTtsEnabled(false);
      toast({
        title: '🔇 Voice Output Disabled',
        description: 'Guru responses will no longer be read aloud.',
        duration: 2000,
      });
    } else {
      setTtsEnabled(true);
      toast({
        title: '🔊 Voice Output Enabled',
        description: 'Guru responses will be read aloud.',
        duration: 2000,
      });
    }
  }, [ttsEnabled, ttsSupported, stopSpeaking, toast]);

  // Handle language change
  const handleLanguageChange = useCallback((code: string) => {
    setCurrentLanguage(code);
    if (isListening) {
      stopListening();
      setTimeout(() => startListening(), 100);
    }
  }, [isListening, stopListening, startListening]);

  // Save conversation whenever messages change
  const saveCurrentConversation = useCallback(() => {
    if (currentConversation && messages.length > 0) {
      const updatedConversation: Conversation = {
        ...currentConversation,
        messages,
        messageCount: messages.length,
        preview: getConversationPreview(messages),
        updatedAt: new Date(),
      };
      saveConversation(updatedConversation);
      setCurrentConversation(updatedConversation);
      setRefreshTrigger(prev => prev + 1);
    }
  }, [currentConversation, messages]);

  useEffect(() => {
    saveCurrentConversation();
  }, [messages, saveCurrentConversation]);

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

  const handleNewConversation = () => {
    stopSpeaking();
    const newConversation = createNewConversation();
    setCurrentConversation(newConversation);
    setCurrentConversationId(newConversation.id);
    
    const welcomeMessage: Message = {
      id: generateId(),
      role: 'guru',
      content: 'The slate is clean, dear one. Let us begin anew. What would you like to explore?',
      timestamp: new Date(),
    };
    setMessages([welcomeMessage]);
    setRefreshTrigger(prev => prev + 1);
  };

  const handleSelectConversation = (conversation: Conversation) => {
    stopSpeaking();
    setCurrentConversation(conversation);
    setCurrentConversationId(conversation.id);
    setMessages(conversation.messages);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="min-h-screen flex bg-background relative overflow-hidden">
      {/* Background - spans full width */}
      <div className="fixed inset-0 bg-spiritual-gradient" />
      <FloatingParticles />

      {/* Desktop Sidebar */}
      <DesktopSidebar
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        onNewConversation={handleNewConversation}
        onOpenSereneMind={() => setShowSereneMind(true)}
        onSelectConversation={handleSelectConversation}
        currentConversationId={currentConversation?.id}
        refreshTrigger={refreshTrigger}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <ChatHeader 
          onClearChat={handleNewConversation}
          onOpenMobileMenu={() => setShowMobileSheet(true)}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
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
                    className="w-8 h-8 rounded-full bg-ojas/20 flex items-center justify-center flex-shrink-0 border border-ojas/30"
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
                className="flex items-center gap-2 px-4 py-2 rounded-full bg-ojas/10 hover:bg-ojas/20 border border-ojas/20 hover:border-ojas/30 transition-all duration-300 hover:scale-105 group"
              >
                <Flame className="w-4 h-4 text-ojas group-hover:animate-pulse" />
                <span className="text-sm text-foreground font-medium">Feeling stressed? Try Serene Mind</span>
              </button>
            </motion.div>

            {/* Voice Recording Indicator */}
            <AnimatePresence>
              {isListening && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="flex items-center justify-center gap-2 mb-3"
                >
                  <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-ojas/20 border border-ojas/30">
                    <motion.div
                      className="w-2 h-2 rounded-full bg-ojas"
                      animate={{ scale: [1, 1.3, 1] }}
                      transition={{ duration: 0.8, repeat: Infinity }}
                    />
                    <span className="text-sm text-ojas font-medium">Listening...</span>
                    {interimTranscript && (
                      <span className="text-xs text-muted-foreground max-w-[200px] truncate">
                        {interimTranscript}
                      </span>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* TTS Speaking Indicator */}
            <AnimatePresence>
              {isSpeaking && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="flex items-center justify-center gap-2 mb-3"
                >
                  <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-prana/20 border border-prana/30">
                    <motion.div
                      className="flex gap-0.5"
                    >
                      {[0, 1, 2, 3].map((i) => (
                        <motion.div
                          key={i}
                          className="w-1 bg-prana rounded-full"
                          animate={{
                            height: ['8px', '16px', '8px'],
                          }}
                          transition={{
                            duration: 0.5,
                            repeat: Infinity,
                            delay: i * 0.1,
                          }}
                        />
                      ))}
                    </motion.div>
                    <span className="text-sm text-prana font-medium">Speaking...</span>
                    <button
                      onClick={stopSpeaking}
                      className="text-xs text-prana/70 hover:text-prana underline ml-1"
                    >
                      Stop
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Voice Error Alert */}
            <AnimatePresence>
              {voiceError && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="flex items-center justify-center gap-2 mb-3"
                >
                  <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-destructive/10 border border-destructive/30">
                    <AlertCircle className="w-4 h-4 text-destructive" />
                    <span className="text-sm text-destructive">{voiceError}</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input Form */}
            <motion.form 
              onSubmit={handleSubmit} 
              className={`glass-card p-3 transition-all duration-300 ${
                inputFocused ? 'ring-2 ring-ojas/40 shadow-lg' : ''
              } ${isListening ? 'ring-2 ring-ojas/60 shadow-ojas/20' : ''}`}
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
                  placeholder={isListening ? "Speak now..." : "Share what's on your heart..."}
                  rows={1}
                  className="flex-1 bg-transparent border-none outline-none resize-none text-foreground placeholder:text-muted-foreground py-2 px-2 max-h-32 scrollbar-spiritual"
                  style={{ minHeight: '44px' }}
                />
                <motion.button
                  type="submit"
                  disabled={!inputValue.trim() || isTyping}
                  className="p-3 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed shadow-md"
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  animate={inputValue.trim() ? { scale: [1, 1.05, 1] } : {}}
                  transition={{ duration: 0.3 }}
                >
                  <Send className="w-5 h-5" />
                </motion.button>
              </div>

              {/* Language & Voice Controls */}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                <LanguageSelector 
                  voiceEnabled={voiceEnabled}
                  isListening={isListening}
                  onVoiceToggle={handleVoiceToggle}
                  onLanguageChange={handleLanguageChange}
                  ttsEnabled={ttsEnabled}
                  onTtsToggle={handleTtsToggle}
                  isSpeaking={isSpeaking}
                />
                <p className="text-xs text-muted-foreground hidden sm:block">
                  AI companion • Not a replacement for professional guidance
                </p>
              </div>
            </motion.form>

            <p className="text-center text-xs text-muted-foreground mt-2 sm:hidden">
              AI companion • Not a replacement for professional guidance
            </p>
          </div>
        </footer>
      </div>

      {/* Mobile Conversation Sheet */}
      <MobileConversationSheet
        isOpen={showMobileSheet}
        onClose={() => setShowMobileSheet(false)}
        onNewConversation={handleNewConversation}
        onOpenSereneMind={() => setShowSereneMind(true)}
        onSelectConversation={handleSelectConversation}
        currentConversationId={currentConversation?.id}
      />

      {/* Serene Mind Modal */}
      <SereneMindModal isOpen={showSereneMind} onClose={() => setShowSereneMind(false)} />
    </div>
  );
};
