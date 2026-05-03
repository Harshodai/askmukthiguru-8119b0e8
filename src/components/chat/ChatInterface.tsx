import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Flame, AlertCircle, Sparkles, Share2 } from 'lucide-react';
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
import { derivePrePracticeInsights } from '@/lib/profileStorage';
import { sendMessage, sendMessageStreaming, MessagePayload } from '@/lib/aiService';
import { hashMessages, getCachedResponse, setCachedResponse } from '@/lib/responseCache';
import { ChatMessage } from './ChatMessage';
import { ChatHeader } from './ChatHeader';
import { ScrollToBottomFab } from './ScrollToBottomFab';
import { MobileConversationSheet } from './MobileConversationSheet';
import { DesktopSidebar } from './DesktopSidebar';
import { LanguageSelector } from './LanguageSelector';
import { WisdomCardGenerator } from './WisdomCardGenerator';
import { FloatingParticles } from '../landing/FloatingParticles';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';
import { useProfile } from '@/hooks/useProfile';
import { useToast } from '@/hooks/use-toast';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { GuidedMeditationFlow } from '@/components/meditation/GuidedMeditationFlow';
import React from 'react';

// ── Date separator helpers ──────────────────────────────────────────
const isSameDay = (a: Date, b: Date): boolean =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

const formatDateLabel = (date: Date): string => {
  const now = new Date();
  if (isSameDay(date, now)) return 'Today';
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (isSameDay(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

// ── Suggested starter chips ─────────────────────────────────────────
const STARTER_SUGGESTIONS = [
  'What is the Beautiful State?',
  'Guide me through a meditation',
  "I'm feeling overwhelmed",
];

// ── MessageList with date separators ────────────────────────────────
const MessageList = React.memo(({ messages, streamingId }: { messages: Message[]; streamingId?: string }) => {
  const groups: { label: string; messages: Message[] }[] = [];
  let currentLabel = '';

  messages.forEach((msg) => {
    const ts = msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp);
    const label = formatDateLabel(ts);
    if (label !== currentLabel) {
      currentLabel = label;
      groups.push({ label, messages: [msg] });
    } else {
      groups[groups.length - 1].messages.push(msg);
    }
  });

  return (
    <AnimatePresence mode="popLayout">
      {groups.map((group) => (
        <React.Fragment key={group.label}>
          {/* Date separator */}
          <div className="flex items-center gap-4 py-4">
            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />
            <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50 select-none px-2">
              {group.label}
            </span>
            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />
          </div>
          {group.messages.map((message, index) => (
            <ChatMessage 
              key={message.id} 
              message={message} 
              index={index}
              isStreaming={message.id === streamingId && message.content.length > 0}
            />
          ))}
        </React.Fragment>
      ))}
    </AnimatePresence>
  );
});
MessageList.displayName = 'MessageList';

const WELCOME_MESSAGE =
  'Namaste, dear seeker. I am here to guide you toward your beautiful state. What brings you here today? Share what is in your heart, and together we shall explore the path to inner peace.';

type PrePracticeLog = NonNullable<
  ReturnType<typeof import('@/lib/profileStorage').loadProfile>['prePracticeLog']
>;

const buildPersonalisedWelcome = (log: PrePracticeLog | undefined): string => {
  if (!log) return WELCOME_MESSAGE;
  const insights = derivePrePracticeInsights(log);
  switch (log.lastAnswer) {
    case 'soul_sync':
      return `Namaste. You arrived after Soul Sync — your heart is already listening. ${insights.encouragement} What would you like to explore?`;
    case 'serene_mind':
      return `Namaste. The Serene Mind practice has settled your breath. ${insights.encouragement} Share what stirs within.`;
    case 'both':
      return `Namaste. Soul Sync and Serene Mind together — a beautiful preparation. ${insights.encouragement} Speak freely.`;
    case 'none':
      return `Namaste, dear seeker. We can begin gently. ${insights.encouragement} What brings you here today?`;
    default:
      return WELCOME_MESSAGE;
  }
};

export const ChatInterface = () => {
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const { open: openSereneMind } = useSereneMind();
  const [showMobileSheet, setShowMobileSheet] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const { profile } = useProfile();
  const [ttsEnabled, setTtsEnabled] = useState(profile.ttsEnabled);
  const [inputFocused, setInputFocused] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(profile.preferredLanguage);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [meditationStep, setMeditationStep] = useState(0);
  const [showScrollFab, setShowScrollFab] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showGuidedMeditation, setShowGuidedMeditation] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | undefined>(undefined);
  const [showQuickWisdomCard, setShowQuickWisdomCard] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastGuruMessageRef = useRef<string>('');
  const isNearBottomRef = useRef(true);
  const { toast } = useToast();

  // ── Scroll tracking ──────────────────────────────────────────────
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 400;
    isNearBottomRef.current = nearBottom;
    setShowScrollFab(!nearBottom);
    if (nearBottom) setUnreadCount(0);
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    setShowScrollFab(false);
    setUnreadCount(0);
  }, []);

  // ── Textarea auto-resize ─────────────────────────────────────────
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 128)}px`;
  }, []);

  // Sync profile changes into local chat state
  useEffect(() => {
    setCurrentLanguage(profile.preferredLanguage);
    setTtsEnabled(profile.ttsEnabled);
  }, [profile.preferredLanguage, profile.ttsEnabled]);

  // Text-to-Speech hook
  const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported } = useTextToSpeech({
    lang: currentLanguage,
    rate: profile.ttsRate,
  });

  // Initialize or load conversation on mount
  useEffect(() => {
    const currentId = getCurrentConversationId();
    let conversation: Conversation | null = null;

    if (currentId) {
      conversation = loadConversation(currentId);
    }

    if (!conversation) {
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
      const welcomeMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: buildPersonalisedWelcome(profile.prePracticeLog),
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
    setCurrentLanguage(code as typeof profile.preferredLanguage);
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

  // Scroll to bottom when new messages arrive (only if near bottom)
  useEffect(() => {
    if (isNearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    } else if (messages.length > 0 && messages[messages.length - 1].role === 'guru') {
      setUnreadCount(prev => prev + 1);
    }
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
    
    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    setIsTyping(true);

    // Convert messages to API format
    const messageHistory: MessagePayload[] = messages.map((m) => ({
      role: m.role === 'guru' ? 'assistant' : 'user',
      content: m.content,
    }));

    // Check cache first
    const allMsgs = [...messageHistory, { role: 'user' as const, content: userMessage.content }];
    const cacheKey = hashMessages(allMsgs);
    const cached = getCachedResponse(cacheKey);

    if (cached) {
      const guruMessage: Message = {
        id: generateId(),
        role: 'guru',
        content: cached.content,
        timestamp: new Date(),
        citations: cached.citations,
      };
      setMessages((prev) => [...prev, guruMessage]);
      setIsTyping(false);
      return;
    }

    // Try streaming first
    const streamingGuruId = generateId();
    let streamingWorked = false;

    try {
      const stream = sendMessageStreaming(messageHistory, userMessage.content, meditationStep);
      
      // Add an empty guru message that we'll fill progressively
      const emptyGuru: Message = {
        id: streamingGuruId,
        role: 'guru',
        content: '',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, emptyGuru]);
      setIsStreaming(true);
      setStreamingMessageId(streamingGuruId);
      setIsTyping(false);

      let fullContent = '';
      for await (const chunk of stream) {
        fullContent += chunk;
        const captured = fullContent;
        setMessages((prev) =>
          prev.map((m) => (m.id === streamingGuruId ? { ...m, content: captured } : m))
        );
      }

      if (fullContent) {
        streamingWorked = true;
        setCachedResponse(cacheKey, fullContent);
      }
    } catch {
      // Streaming not available — fall back to regular fetch
    } finally {
      setIsStreaming(false);
      setStreamingMessageId(undefined);
    }

    if (streamingWorked) return;

    // Remove the empty streaming bubble if it was added
    setMessages((prev) => prev.filter((m) => m.id !== streamingGuruId || m.content !== ''));
    setIsTyping(true);

    try {
      const response = await sendMessage(messageHistory, userMessage.content, meditationStep);

      if (response.blocked && response.blockReason) {
        const blockedMessage: Message = {
          id: generateId(),
          role: 'guru',
          content: response.content || `Message blocked: ${response.blockReason}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, blockedMessage]);
      } else {
        if (response.errorCode === 'rate_limited') {
          toast({
            title: 'Slow down, dear seeker',
            description: "You're sending messages quickly. Please wait a moment.",
            variant: 'destructive',
          });
        } else if (response.errorCode === 'unauthorized') {
          toast({
            title: 'Session expired',
            description: 'Please sign in again to continue your conversation.',
            variant: 'destructive',
          });
        } else if (response.errorCode === 'server_error') {
          toast({
            title: 'The Guru is meditating',
            description: 'Our service is briefly unavailable. Showing offline guidance.',
          });
        }

        const guruMessage: Message = {
          id: generateId(),
          role: 'guru',
          content: response.content,
          timestamp: new Date(),
          citations: response.citations && response.citations.length > 0 ? response.citations.slice(0, 3) : undefined,
        };
        setMessages((prev) => [...prev, guruMessage]);
        setCachedResponse(cacheKey, response.content, guruMessage.citations);

        if (response.meditationStep !== undefined) {
          setMeditationStep(response.meditationStep);
        }

        if (response.intent === 'DISTRESS' && (response.meditationStep || 0) > 0) {
          openSereneMind('audio');
        }
      }
    } catch (error) {
      console.error('Error getting response:', error);
    } finally {
      setIsTyping(false);
    }
  };

  const handleSuggestionClick = (text: string) => {
    setInputValue(text);
    // Auto-submit after a brief tick so the user sees it
    setTimeout(() => {
      const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
      setInputValue(text);
      // We'll just set the value; user can press Send
    }, 50);
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

  const showStarters = messages.length <= 1 && messages[0]?.role === 'guru';

  return (
    <div className="min-h-screen flex bg-background relative overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 bg-spiritual-gradient" />
      <FloatingParticles />

      {/* Desktop Sidebar */}
      <DesktopSidebar
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        onNewConversation={handleNewConversation}
        onOpenSereneMind={() => openSereneMind()}
        onSelectConversation={handleSelectConversation}
        currentConversationId={currentConversation?.id}
        refreshTrigger={refreshTrigger}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {/* Header */}
        <ChatHeader 
          onClearChat={handleNewConversation}
          onOpenMobileMenu={() => setShowMobileSheet(true)}
          onToggleSidebar={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        {/* Messages Area */}
        <main
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="relative z-10 flex-1 overflow-y-auto px-3 sm:px-6 py-6 scrollbar-spiritual"
        >
          <div className="max-w-3xl mx-auto space-y-4">
            <MessageList messages={messages} streamingId={streamingMessageId} />

            {/* Suggested starters */}
            {showStarters && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
                className="flex flex-wrap justify-center gap-2 pt-4"
              >
                {STARTER_SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="px-4 py-2 rounded-full text-sm border border-ojas/30 bg-ojas/5 text-foreground hover:bg-ojas/15 hover:border-ojas/50 transition-all"
                  >
                    {suggestion}
                  </button>
                ))}
              </motion.div>
            )}

            {/* Streaming skeleton */}
            <AnimatePresence>
              {isStreaming && messages.length > 0 && messages[messages.length - 1].content === '' && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-start gap-3"
                >
                  <div className="w-8 h-8 rounded-full bg-ojas/20 flex items-center justify-center flex-shrink-0 border border-ojas/30">
                    <div className="w-4 h-4 rounded-full bg-ojas/50" />
                  </div>
                  <div className="glass-card px-4 py-3 rounded-2xl rounded-tl-sm space-y-2 w-48">
                    <div className="h-3 bg-muted-foreground/10 rounded-full animate-pulse" />
                    <div className="h-3 bg-muted-foreground/10 rounded-full animate-pulse w-3/4" />
                    <div className="h-3 bg-muted-foreground/10 rounded-full animate-pulse w-1/2" />
                  </div>
                </motion.div>
              )}
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

        {/* Scroll-to-bottom FAB */}
        <ScrollToBottomFab
          visible={showScrollFab}
          unreadCount={unreadCount}
          onClick={scrollToBottom}
        />

        {/* Input Area */}
        <footer className="relative z-20 px-3 sm:px-4 pb-3 pt-2 pb-safe">
          <div className="max-w-3xl mx-auto">
            {/* Subtle practice chips */}
            <div className="flex justify-center gap-2 mb-2">
              <button
                onClick={() => openSereneMind()}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] text-muted-foreground hover:text-ojas hover:bg-ojas/5 border border-transparent hover:border-ojas/20 transition-colors"
              >
                <Flame className="w-3 h-3" />
                <span>Serene Mind</span>
              </button>
              <button
                onClick={() => setShowGuidedMeditation(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] text-muted-foreground hover:text-ojas hover:bg-ojas/5 border border-transparent hover:border-ojas/20 transition-colors"
              >
                <Sparkles className="w-3 h-3" />
                <span>Guided Meditation</span>
              </button>
              {/* Quick share last guru message */}
              {messages.length > 1 && messages[messages.length - 1]?.role === 'guru' && (
                <button
                  onClick={() => setShowQuickWisdomCard(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] text-muted-foreground hover:text-ojas hover:bg-ojas/5 border border-transparent hover:border-ojas/20 transition-colors"
                >
                  <Share2 className="w-3 h-3" />
                  <span>Share Wisdom</span>
                </button>
              )}
            </div>

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
              className={`rounded-2xl border bg-card/90 backdrop-blur-lg transition-all duration-300 shadow-sm ${
                inputFocused ? 'border-ojas/40 shadow-lg shadow-ojas/8 ring-1 ring-ojas/15' : 'border-border/50'
              } ${isListening ? 'border-ojas/50 shadow-ojas/15 ring-1 ring-ojas/20' : ''}`}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 }}
            >
              <div className="flex items-end gap-2 px-3 pt-2.5 pb-1.5">
                <textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  onFocus={() => setInputFocused(true)}
                  onBlur={() => setInputFocused(false)}
                  placeholder={isListening ? 'Speak now…' : "Share what's on your heart…"}
                  rows={1}
                  aria-label="Your message"
                  className="flex-1 bg-transparent border-none outline-none resize-none text-foreground placeholder:text-muted-foreground py-1.5 px-1 max-h-32 scrollbar-spiritual text-[14px] leading-relaxed"
                  style={{ minHeight: '36px' }}
                />
                <motion.button
                  type="submit"
                  disabled={!inputValue.trim() || isTyping || isStreaming}
                  className="p-2.5 rounded-full bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md"
                  whileHover={{ scale: inputValue.trim() ? 1.05 : 1 }}
                  whileTap={{ scale: 0.95 }}
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </motion.button>
              </div>

              {/* Secondary controls row */}
              <div className="flex items-center justify-between px-3 pb-2 pt-1">
                <LanguageSelector
                  voiceEnabled={voiceEnabled}
                  isListening={isListening}
                  onVoiceToggle={handleVoiceToggle}
                  onLanguageChange={handleLanguageChange}
                  ttsEnabled={ttsEnabled}
                  onTtsToggle={handleTtsToggle}
                  isSpeaking={isSpeaking}
                />
                <p className="text-[10px] text-muted-foreground hidden sm:block">
                  AI companion • Not a substitute for professional care
                </p>
              </div>
            </motion.form>

            <p className="text-center text-[10px] text-muted-foreground mt-1.5 sm:hidden">
              AI companion • Not a substitute for professional care
            </p>
          </div>
        </footer>
      </div>

      {/* Mobile Conversation Sheet */}
      <MobileConversationSheet
        isOpen={showMobileSheet}
        onClose={() => setShowMobileSheet(false)}
        onNewConversation={handleNewConversation}
        onOpenSereneMind={() => openSereneMind()}
        onSelectConversation={handleSelectConversation}
        currentConversationId={currentConversation?.id}
      />

      {/* Guided Meditation Full-Screen Flow */}
      <GuidedMeditationFlow
        isOpen={showGuidedMeditation}
        onClose={() => setShowGuidedMeditation(false)}
      />

      {/* Quick Wisdom Card from last guru message */}
      <WisdomCardGenerator
        isOpen={showQuickWisdomCard}
        onClose={() => setShowQuickWisdomCard(false)}
        content={
          messages.length > 0
            ? (messages.filter(m => m.role === 'guru').pop()?.content ?? '')
            : ''
        }
      />
    </div>
  );
};
