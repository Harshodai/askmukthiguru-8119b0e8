import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Flame, AlertCircle, Sparkles, Share2, BookOpen } from 'lucide-react';

const OptimisticPlaceholder = () => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0 }}
    className="flex items-start gap-3 w-full"
  >
    <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5 animate-pulse">
      <Sparkles className="w-3.5 h-3.5 text-ojas/60" />
    </div>
    <div className="flex-1 flex flex-col gap-2 max-w-[85%] sm:max-w-[75%]">
      <div className="border-l-[3px] border-ojas/10 pl-4 py-2 space-y-3 w-full bg-gradient-to-r from-ojas/5 to-transparent rounded-r-xl">
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[90%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[85%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[95%]" />
        <div className="h-3.5 bg-muted-foreground/10 rounded animate-pulse w-[60%]" />
      </div>
      <div className="w-full rounded-xl border border-ojas/10 bg-card/30 p-3 space-y-2.5">
        <div className="flex items-center gap-2">
          <BookOpen className="w-3 h-3 text-ojas/40 animate-pulse" />
          <div className="h-2.5 bg-muted-foreground/10 rounded animate-pulse w-24" />
        </div>
        <div className="space-y-1.5 pl-5">
          <div className="h-2 bg-muted-foreground/10 rounded animate-pulse w-2/3" />
          <div className="h-2 bg-muted-foreground/10 rounded animate-pulse w-1/2" />
        </div>
      </div>
    </div>
  </motion.div>
);

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
  updateConversationSummary,
} from '@/lib/chatStorage';
import type { MessageError, MessageErrorKind } from '@/lib/chatStorage';
import { chatErrorBus } from '@/lib/chatErrorBus';
import { ChatErrorBanner } from './ChatErrorBanner';

// Build a user-facing MessageError from an internal error code / details.
const buildMessageError = (
  code: MessageErrorKind | string | undefined,
  rawMessage?: string,
  status?: number,
): MessageError => {
  const detail = status ? `${rawMessage ?? ''} (HTTP ${status})`.trim() : rawMessage;
  switch (code) {
    case 'unauthorized':
      return {
        kind: 'unauthorized',
        title: 'Your session expired',
        description: 'Please sign in again to continue your conversation with the Guru.',
        actionLabel: 'sign_in',
        detail,
      };
    case 'rate_limited':
      return {
        kind: 'rate_limited',
        title: 'Too many requests',
        description: 'Please pause for a few seconds, then try again.',
        actionLabel: 'retry',
        detail,
      };
    case 'network':
      return {
        kind: 'network',
        title: 'Cannot reach the Guru',
        description: 'Network or backend is unreachable. Check your connection and retry.',
        actionLabel: 'retry',
        detail,
      };
    case 'timeout':
      return {
        kind: 'timeout',
        title: 'The response timed out',
        description: 'The Guru took too long to respond. Please retry your question.',
        actionLabel: 'retry',
        detail,
      };
    case 'server_error':
      return {
        kind: 'server_error',
        title: 'Service unavailable',
        description: 'Our backend returned an error. Please retry in a moment.',
        actionLabel: 'retry',
        detail,
      };
    default:
      return {
        kind: 'unknown',
        title: 'Something went wrong',
        description: rawMessage || 'The Guru could not answer this time. Please retry.',
        actionLabel: 'retry',
        detail,
      };
  }
};
import { derivePrePracticeInsights } from '@/lib/profileStorage';
import { sendMessage, sendMessageStreaming, MessagePayload, StreamChunk, generateSummary, generateConversationTitle, setLanguage as setAILanguage, ProactiveSereneMindTrigger } from '@/lib/aiService';
import { getLastCompletedMeditationTimestamp } from '@/lib/meditationStorage';
import { hashMessages, getCachedResponse, setCachedResponse, clearResponseCache } from '@/lib/responseCache';
import { ChatMessage } from './ChatMessage';
import { ChatHeader } from './ChatHeader';
import { ScrollToBottomFab } from './ScrollToBottomFab';
import { MobileConversationSheet } from './MobileConversationSheet';
import { DesktopSidebar, useSidebarCollapsed } from './DesktopSidebar';
import { LanguageSelector, LANGUAGES } from './LanguageSelector';
import { WisdomCardGenerator } from './WisdomCardGenerator';
import { FloatingParticles } from '../landing/FloatingParticles';
import { DailyTeaching } from './DailyTeaching';
import { ThinkingPills, type PipelineStep, mapStatusToLabel } from './ThinkingPills';
import { useSpeechRecognition } from '@/hooks/useSpeechRecognition';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';
import { useProfile } from '@/hooks/useProfile';
import { useChatShortcuts } from '@/hooks/useChatShortcuts';
import { useSwipeGesture } from '@/hooks/useSwipeGesture';
import { useToast } from '@/hooks/use-toast';
import { ToastAction } from '@/components/ui/toast';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { GuidedMeditationFlow } from '@/components/meditation/GuidedMeditationFlow';
import React from 'react';
import { createPortal } from 'react-dom';
import { MessageList } from './MessageList';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';

// ── Suggested starter chips ─────────────────────────────────────────
const STARTER_SUGGESTIONS = [
  'What is the Beautiful State?',
  'Guide me through a meditation',
  "I'm feeling overwhelmed",
];


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
  const [streamingMessageId, setStreamingMessageId] = useState<string | undefined>();
  const [streamingContent, setStreamingContent] = useState<string>('');
  const { open: openSereneMind, setOnComplete: setSereneMindOnComplete } = useSereneMind();
  const [isAwaitingSereneMind, setIsAwaitingSereneMind] = useState(false);
  const [showMobileSheet, setShowMobileSheet] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const { profile, loading: profileLoading, update: updateProfile } = useProfile();
  const [ttsEnabled, setTtsEnabled] = useState(profile.ttsEnabled);
  const [inputFocused, setInputFocused] = useState(false);
  const [currentLanguage, setCurrentLanguage] = useState(profile.preferredLanguage);
  const { isCollapsed: sidebarCollapsed, toggle: toggleSidebar } = useSidebarCollapsed();
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [prevProfileLoading, setPrevProfileLoading] = useState(true);
  if (prevProfileLoading && !profileLoading) {
    setPrevProfileLoading(false);
    setCurrentLanguage(profile.preferredLanguage);
    setTtsEnabled(profile.ttsEnabled);
    setAILanguage(profile.preferredLanguage);
  }
  const [meditationStep, setMeditationStep] = useState(0);
  const [showScrollFab, setShowScrollFab] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showGuidedMeditation, setShowGuidedMeditation] = useState(false);
  const [showQuickWisdomCard, setShowQuickWisdomCard] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [showPipeline, setShowPipeline] = useState(false);
  // Heartbeat pulse for "Still processing..." status events
  const [pipelineHeartbeat, setPipelineHeartbeat] = useState(false);
  // Instant pill shown immediately on submit, before backend status events arrive
  const [showInstantPill, setShowInstantPill] = useState(false);
  const { teaching: dailyTeaching } = useDailyTeaching();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const innerContentRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const lastGuruMessageRef = useRef<string>('');
  const isNearBottomRef = useRef(true);
  const titleGenerationRef = useRef<Set<string>>(new Set());
  const { toast } = useToast();

  // ── Scroll tracking ──────────────────────────────────────────────
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 200;
    isNearBottomRef.current = nearBottom;
    setShowScrollFab(!nearBottom);
    if (nearBottom) setUnreadCount(0);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    isNearBottomRef.current = true;
    const container = scrollContainerRef.current;
    if (container) {
      if (behavior === 'smooth') {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: 'smooth'
        });
      } else {
        container.scrollTop = container.scrollHeight;
      }
    }
    setShowScrollFab(false);
    setUnreadCount(0);
  }, []);

  // ── Smart ResizeObserver auto-scroll to bottom (no gaps) ─────────
  useEffect(() => {
    const container = scrollContainerRef.current;
    const inner = innerContentRef.current;
    if (!container || !inner || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      // Whenever content height changes (streaming tokens, regenerate, inline edit),
      // lock the scroll position to the bottom if the user was already near the bottom.
      if (isNearBottomRef.current) {
        container.scrollTop = container.scrollHeight;
      }
    });

    observer.observe(inner);
    return () => {
      observer.disconnect();
    };
  }, []);

  // ── Textarea auto-resize ─────────────────────────────────────────
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 128)}px`;
  }, []);

  // Sync profile changes into local chat state + push language to AI service
  useEffect(() => {
    setCurrentLanguage(profile.preferredLanguage);
    setTtsEnabled(profile.ttsEnabled);
    setAILanguage(profile.preferredLanguage);
  }, [profile.preferredLanguage, profile.ttsEnabled]);

  // Text-to-Speech hook
  const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported } = useTextToSpeech({
    lang: currentLanguage,
    rate: profile.ttsRate,
    speaker: profile.preferredVoice,
    onError: (err) => {
      toast({
        title: 'Voice Output Notice',
        description: err,
        variant: 'destructive',
        duration: 4000,
      });
    },
  });

  // Initialize or load conversation on mount
  useEffect(() => {
    if (profileLoading) return;
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

    // ── Restore partial stream checkpoint ─────────────────────────────
    try {
      const raw = sessionStorage.getItem('askmukthiguru_stream_checkpoint');
      if (raw) {
        const cp = JSON.parse(raw) as { conversationId: string; messageId: string; content: string; timestamp: number };
        const age = Date.now() - cp.timestamp;
        if (age < 60_000 && cp.conversationId === conversation.id && cp.content.length > 20) {
          const restoredMsg: Message = {
            id: cp.messageId,
            role: 'guru',
            content: cp.content + '\n\n*(Response was interrupted — tap Regenerate to try again)*',
            timestamp: new Date(cp.timestamp),
          };
          setMessages(prev => {
            // Only add if not already in the list
            if (prev.some(m => m.id === cp.messageId)) return prev;
            return [...prev, restoredMsg];
          });
        }
        sessionStorage.removeItem('askmukthiguru_stream_checkpoint');
      }
    } catch { /* non-fatal */ }
    // ────────────────────────────────────────────────────────────────

    // Scroll to bottom on mount after a tick
    requestAnimationFrame(() => {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
      }
    });
  }, [profileLoading]);

  // Auto-speak ONLY for newly generated guru messages — never on initial mount
  // or when switching conversations (avoids unwanted speaker when entering /chat).
  const ttsInitializedRef = useRef(false);
  useEffect(() => {
    if (!ttsEnabled || messages.length === 0) {
      // Seed the ref so the next message change is treated as "new"
      if (messages.length > 0) {
        lastGuruMessageRef.current = messages[messages.length - 1]?.content ?? '';
      }
      ttsInitializedRef.current = true;
      return;
    }

    // Skip first run: don't speak the already-existing last message on mount/switch
    if (!ttsInitializedRef.current) {
      ttsInitializedRef.current = true;
      lastGuruMessageRef.current = messages[messages.length - 1]?.content ?? '';
      return;
    }

    const lastMessage = messages[messages.length - 1];
    if (
      lastMessage.role === 'guru' &&
      lastMessage.content &&
      !isStreaming &&
      lastMessage.content !== lastGuruMessageRef.current
    ) {
      lastGuruMessageRef.current = lastMessage.content;
      speak(lastMessage.content);
    }
  }, [messages, ttsEnabled, speak, isStreaming]);

  // Reset TTS gate when switching conversations
  useEffect(() => {
    ttsInitializedRef.current = false;
  }, [currentConversation?.id]);

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
    useSarvam: true,
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
    onLanguageDetected: (detectedLang) => {
      const detectedLangObj = LANGUAGES.find(
        (l) => l.bcp47.toLowerCase() === detectedLang.toLowerCase() || l.code.toLowerCase() === detectedLang.toLowerCase()
      );
      if (!detectedLangObj || detectedLangObj.code === currentLanguage) return;
      // Don't re-prompt for the same language in the same session
      const dismissKey = `lang_dismiss_${detectedLangObj.code}`;
      if (sessionStorage.getItem(dismissKey)) return;

      toast({
        title: `🌐 Detected ${detectedLangObj.name}`,
        description: `Switch conversation language to ${detectedLangObj.native}?`,
        duration: 8000,
        action: (
          <ToastAction
            altText={`Switch to ${detectedLangObj.name}`}
            onClick={() => handleLanguageChange(detectedLangObj.code)}
          >
            Switch
          </ToastAction>
        ),
      });
      // Mark this detection as seen for the session if user ignores it
      sessionStorage.setItem(dismissKey, '1');
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

  // Handle language change — persist to profile, push to AI service, restart STT in new lang
  const handleLanguageChange = useCallback((code: string) => {
    setCurrentLanguage(code);
    setAILanguage(code);
    clearResponseCache();
    updateProfile({ preferredLanguage: code });
    if (isListening) {
      stopListening();
      setTimeout(() => startListening(), 150);
    }
  }, [isListening, stopListening, startListening, updateProfile]);

  // Save conversation whenever messages change (use ref to avoid re-render loop)
  const currentConversationRef = useRef(currentConversation);
  currentConversationRef.current = currentConversation;

  useEffect(() => {
    const conv = currentConversationRef.current;
    if (conv && messages.length > 0) {
      const updatedConversation: Conversation = {
        ...conv,
        messages,
        messageCount: messages.length,
        preview: conv.preview && conv.preview !== 'New conversation'
          ? conv.preview
          : getConversationPreview(messages),
        updatedAt: new Date(),
        summary: conv.summary,
      };
      saveConversation(updatedConversation);
      setCurrentConversation(updatedConversation);
      setRefreshTrigger(prev => prev + 1);
    }
  }, [messages]);

  // Track unread messages when we are not near the bottom
  useEffect(() => {
    if (!isNearBottomRef.current && messages.length > 0 && messages[messages.length - 1].role === 'guru') {
      setUnreadCount(prev => prev + 1);
    }
  }, [messages]);

  const handleSubmit = async (
    e: React.FormEvent,
    overrideText?: string,
    options: {
      appendUser?: boolean;
      baseMessages?: Message[];
      historyMessages?: Message[];
      bypassCache?: boolean;
    } = {},
  ) => {
    e.preventDefault();
    const textToSend = overrideText ?? inputValue;
    if (!textToSend.trim() || isTyping) {
      return;
    }

    // Show instant pill immediately on submit — appears before any backend status events
    setShowInstantPill(true);

    const appendUser = options.appendUser ?? true;
    const baseMessages = options.baseMessages ?? messages;
    const historyMessages = options.historyMessages ?? baseMessages;
    const isFirstUserMessage = appendUser && baseMessages.every((m) => m.role !== 'user');

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: textToSend.trim(),
      timestamp: new Date(),
    };

    if (appendUser) {
      setMessages((prev) => [...prev, userMessage]);
    } else if (options.baseMessages) {
      setMessages(options.baseMessages);
    }
    if (!overrideText) setInputValue('');

    // Reset textarea height
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }

    // Force scroll to bottom after sending
    isNearBottomRef.current = true;
    setIsTyping(true);

    // Convert messages to API format
    const messageHistory: MessagePayload[] = historyMessages.map((m) => ({
      role: m.role === 'guru' ? 'assistant' : 'user',
      content: m.content,
    }));

    // Check cache first
    const allMsgs = [...messageHistory, { role: 'user' as const, content: userMessage.content }];
    const cacheKey = `${currentLanguage}:${hashMessages(allMsgs)}`;
    const cached = options.bypassCache ? null : getCachedResponse(cacheKey);

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

    if (isFirstUserMessage && currentConversation?.id && !titleGenerationRef.current.has(currentConversation.id)) {
      titleGenerationRef.current.add(currentConversation.id);
      generateConversationTitle(userMessage.content).then((title) => {
        setCurrentConversation((prev) => {
          if (!prev || prev.id !== currentConversation.id) return prev;
          const updated = { ...prev, preview: title, updatedAt: new Date() };
          saveConversation(updated);
          return updated;
        });
        setRefreshTrigger((prev) => prev + 1);
      }).catch(() => {
        titleGenerationRef.current.delete(currentConversation.id);
      });
    }

    // Summary helper — fire-and-forget after every ~6 user messages
    const maybeSummarize = () => {
      const userMsgCount = allMsgs.filter(m => m.role === 'user').length;
      if (userMsgCount > 0 && userMsgCount % 6 === 0 && currentConversation?.id) {
        generateSummary(allMsgs).then(summary => {
          if (summary) {
            updateConversationSummary(currentConversation.id, summary);
            setCurrentConversation(prev => prev ? { ...prev, summary } : null);
          }
        }).catch(() => { /* non-fatal */ });
      }
    };

    // Try streaming first (skip when awaiting Serene Mind to avoid leaking blocked content during stream)
    const streamingGuruId = generateId();
    let streamingWorked = false;
    let fullContent = '';
    let finalIntent = 'CASUAL';
    let checkpointInterval: ReturnType<typeof setInterval> | undefined;

    if (!isAwaitingSereneMind) {
      try {
        const lastSereneMindAt = getLastCompletedMeditationTimestamp();
        const stream = sendMessageStreaming(
          messageHistory,
          userMessage.content,
          meditationStep,
          currentConversation?.summary,
          currentConversation?.id,
          lastSereneMindAt,
        );

        // Show pipeline thinking pills — start with Safety check active immediately to eliminate blank gap
        setPipelineSteps([
          { id: 'step-0', label: 'Safety check', status: 'active' as const }
        ]);
        setShowPipeline(true);

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

        // ── 500ms stream persistence checkpoint ────────────────────────
        checkpointInterval = setInterval(() => {
          if (fullContent.length > 20) {
            try {
              sessionStorage.setItem('askmukthiguru_stream_checkpoint', JSON.stringify({
                conversationId: currentConversation?.id ?? '',
                messageId: streamingGuruId,
                content: fullContent,
                timestamp: Date.now(),
              }));
            } catch { /* storage full — ignore */ }
          }
        }, 500);
        // ────────────────────────────────────────────────────────────────

        let gotFirstToken = false;
        let streamedCitations: string[] = [];
        let streamedMedStep = 0;
        let streamedBlocked = false;
        let streamedBlockReason: string | null = null;
        let streamedProactiveSereneMind: ProactiveSereneMindTrigger | null = null;
        for await (const chunk of stream) {
          if (chunk.type === 'status') {
            // First status event from backend → hide instant pill
            setShowInstantPill(false);
            // Pipeline status update → add or advance pills
            const label = mapStatusToLabel(chunk.text);
            // Handle heartbeat: pulse the current active step instead of adding a new step
            if (label === 'heartbeat') {
              setPipelineHeartbeat(true);
              continue;
            }
            setPipelineSteps((prev) => {
              // De-duplicate: if the latest step already has this label, just keep it active
              if (prev.length > 0 && prev[prev.length - 1].label === label) {
                return prev.map((s, idx) =>
                  idx === prev.length - 1 ? { ...s, status: 'active' as const } : s
                );
              }
              // Mark all previous steps as done
              const updated = prev.map((s) =>
                s.status === 'active' ? { ...s, status: 'done' as const } : s
              );
              // Add new active step
              return [...updated, { id: `step-${updated.length}`, label, status: 'active' as const }];
            });
            continue;
          }

          if (chunk.type === 'done') {
            // Final metadata from backend — citations, intent, meditationStep, proactiveSereneMind
            streamedCitations = chunk.citations;
            finalIntent = chunk.intent;
            streamedMedStep = chunk.meditationStep;
            streamedBlocked = chunk.blocked ?? false;
            streamedBlockReason = chunk.blockReason ?? null;
            streamedProactiveSereneMind = chunk.proactiveSereneMind ?? null;
            continue;
          }

          if (chunk.type === 'error') {
            toast({ title: 'Server error', description: chunk.text, variant: 'destructive' });
            continue;
          }

          // First token → hide pipeline pills
          if (!gotFirstToken) {
            gotFirstToken = true;
            // Mark all steps as done, then fade out
            setPipelineSteps((prev) => prev.map((s) => ({ ...s, status: 'done' as const })));
            setTimeout(() => setShowPipeline(false), 600);
            // Stop heartbeat pulse when actual content starts streaming
            setPipelineHeartbeat(false);
          }

          // Update the streaming message state locally without mapping entire array
          fullContent += chunk.text;
          setStreamingContent(fullContent);
          // Keep scrolling during streaming if near bottom
          if (isNearBottomRef.current && scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
          }
        }

        if (fullContent) {
          streamingWorked = true;
          // Commit the final streamed content to the message list
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingGuruId ? { ...m, content: fullContent, intent: finalIntent, citations: streamedCitations.length > 0 ? streamedCitations : undefined } : m))
          );

          setStreamingMessageId(undefined);
          setStreamingContent('');

          setCachedResponse(cacheKey, fullContent, streamedCitations.length > 0 ? streamedCitations : undefined);

          // Update meditation step from streaming metadata
          if (streamedMedStep !== undefined) {
            setMeditationStep(streamedMedStep);
          }

          // Trigger Serene Mind based on response signals
          if (streamedBlocked) {
            // Blocked content → gated Serene Mind (chat locked until completed)
            const prelude = 'Sri Krishnaji teaches that every obstacle is a teacher. Please do Serene Mind now to continue. You can click the button below, or say "can you open serene mind for me" to begin.';
            setMessages((prev) => [
              ...prev,
              {
                id: generateId(),
                role: 'guru',
                content: prelude,
                timestamp: new Date(),
              },
            ]);
            setTimeout(() => {
              setIsAwaitingSereneMind(true);
              setSereneMindOnComplete(() => () => {
                setIsAwaitingSereneMind(false);
                setSereneMindOnComplete(null);
              });
              openSereneMind('breathing', true);
            }, 7000);
          } else if (finalIntent === 'MEDITATION' || finalIntent === 'MEDITATION_CONTINUE') {
            // Voluntary request: open without gating — user asked for it
            openSereneMind('breathing');
          } else if (finalIntent === 'DISTRESS' && (streamedMedStep || 0) > 0) {
            openSereneMind('audio');
          } else if (streamedProactiveSereneMind?.triggered) {
            // Proactive: stream the teachings prelude as a guru message, then open gated after 7s
            const preludeText =
              streamedProactiveSereneMind.teachings_prelude ||
              'Sri Preethaji and Sri Krishnaji reminds us: suffering is not the truth of who you are. Every moment of pain is also a doorway to awakening. Please do Serene Mind now to continue. You can type "do serene mind now" or click the button below to start.';
            setMessages((prev) => [
              ...prev,
              {
                id: generateId(),
                role: 'guru',
                content: preludeText,
                timestamp: new Date(),
              },
            ]);
            setTimeout(() => {
              setIsAwaitingSereneMind(true);
              setSereneMindOnComplete(() => () => {
                setIsAwaitingSereneMind(false);
                setSereneMindOnComplete(null);
              });
              openSereneMind('breathing', true);
            }, 7000);
          }

          // Heuristic fallback: if LLM text explicitly describes a Serene Mind session
          // but backend didn't flag DISTRESS (e.g. serene_mind module not running),
          // open the modal so the real guided session plays alongside the text.
          if (finalIntent !== 'DISTRESS' && !streamedProactiveSereneMind?.triggered) {
            const t = fullContent.toLowerCase();
            const looksLikeSereneMind =
              t.includes('serene mind') ||
              t.includes('step 1/') ||
              (t.includes('close your eyes') && t.includes('breath')) ||
              (t.includes('meditation') && (t.includes('step 1') || t.includes('settling in')));
            if (looksLikeSereneMind && meditationStep === 0) {
              openSereneMind('breathing');
            }
          }
        }
      } catch (streamErr) {
        const err = streamErr as { errorCode?: string; status?: number; message?: string };
        // Streaming failed — show toast if partial content was received
        if (fullContent) {
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingGuruId ? { ...m, content: fullContent } : m))
          );
          toast({ title: 'Connection interrupted', description: 'Response may be incomplete.' });
          streamingWorked = true; // Keep partial content
        } else {
          const msgError = buildMessageError(err?.errorCode, err?.message, err?.status);
          // Replace the empty streaming bubble with an inline error card so the failure
          // is visible in the chat itself (not just a toast that can be missed).
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingGuruId
                ? { ...m, content: '', error: msgError }
                : m,
            ),
          );
          streamingWorked = true; // Suppress the offline fallback path; the bubble already shows the error.
          chatErrorBus.publishFromMessage(msgError, streamingGuruId);
        }
      } finally {
        clearInterval(checkpointInterval);
        setIsStreaming(false);
        setStreamingMessageId(undefined);
        setStreamingContent('');
        setShowPipeline(false);
        setPipelineSteps([]);
        setShowInstantPill(false);
        // Stop heartbeat pulse
        setPipelineHeartbeat(false);
        // Clear stream checkpoint on completion
        try {
          sessionStorage.removeItem('askmukthiguru_stream_checkpoint');
        } catch {
          // Storage can be unavailable in hardened browser modes.
        }
      }
    }

    if (streamingWorked) {
      maybeSummarize();
      return;
    }

    // Remove the empty streaming bubble if it was added
    setMessages((prev) => prev.filter((m) => m.id !== streamingGuruId || m.content !== ''));
    setIsTyping(true);

    try {
      const lastSereneMindAt = getLastCompletedMeditationTimestamp();
      const response = await sendMessage(
        messageHistory,
        userMessage.content,
        meditationStep,
        currentConversation?.summary,
        currentConversation?.id,
        lastSereneMindAt,
      );

      setIsTyping(false);

      if (isAwaitingSereneMind) {
        // If we are awaiting Serene Mind, we only allow MEDITATION/MEDITATION_CONTINUE intent
        if (response.intent === 'MEDITATION' || response.intent === 'MEDITATION_CONTINUE') {
          openSereneMind('breathing', true);
        } else {
          const blockedMsg: Message = {
            id: generateId(),
            role: 'guru',
            content: 'Please do Serene Mind now to continue. You can click the button below, or say "can you open serene mind for me" to begin.',
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, blockedMsg]);
        }
        return;
      }

      if (response.blocked && response.blockReason) {
        const blockedMessage: Message = {
          id: generateId(),
          role: 'guru',
          content: response.content || `Message blocked: ${response.blockReason}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, blockedMessage]);
        openSereneMind('breathing', true);
      } else {
        const responseError = response.errorCode
          ? buildMessageError(response.errorCode, response.error)
          : undefined;
        if (responseError) {
          chatErrorBus.publishFromMessage(responseError);
        }

        const guruMessage: Message = {
          id: generateId(),
          role: 'guru',
          content: response.content,
          timestamp: new Date(),
          citations: response.citations && response.citations.length > 0 ? response.citations : undefined,
          error: responseError,
        };
        setMessages((prev) => [...prev, guruMessage]);
        if (!responseError) {
          setCachedResponse(cacheKey, response.content, guruMessage.citations);
        }

        if (response.meditationStep !== undefined) {
          setMeditationStep(response.meditationStep);
        }

        if (response.intent === 'MEDITATION' || response.intent === 'MEDITATION_CONTINUE') {
          // Voluntary request: non-gated
          openSereneMind('breathing');
        } else if (response.intent === 'DISTRESS' && (response.meditationStep || 0) > 0) {
          openSereneMind('audio');
        } else if (response.proactiveSereneMind?.triggered) {
          // Proactive gated path with 7s teachings prelude
          const preludeText =
            response.proactiveSereneMind?.teachings_prelude ||
            'Sri Preethaji and Sri Krishnaji remind us: suffering is not the truth of who you are. Every moment of pain is also a doorway to awakening. Please do Serene Mind now to continue. You can click the button below to start.';
          setMessages((prev) => [
            ...prev,
            {
              id: generateId(),
              role: 'guru',
              content: preludeText,
              timestamp: new Date(),
            },
          ]);
          setTimeout(() => {
            setIsAwaitingSereneMind(true);
            setSereneMindOnComplete(() => () => {
              setIsAwaitingSereneMind(false);
              setSereneMindOnComplete(null);
            });
            openSereneMind('breathing', true);
          }, 7000);
        }

        // Heuristic fallback for non-streaming path (same logic as streaming)
        if (response.intent !== 'DISTRESS' && !response.proactiveSereneMind?.triggered) {
          const t = (response.content || '').toLowerCase();
          const looksLikeSereneMind =
            t.includes('serene mind') ||
            t.includes('step 1/') ||
            (t.includes('close your eyes') && t.includes('breath')) ||
            (t.includes('meditation') && (t.includes('step 1') || t.includes('settling in')));
          if (looksLikeSereneMind && meditationStep === 0) {
            openSereneMind('breathing');
          }
        }
      }

    } catch (error) {
    console.error('Error getting response:', error);

    const errObj = error as { errorCode?: string; status?: number; message?: string };
    const isOffline = !navigator.onLine || String(error).toLowerCase().includes('network') || String(error).toLowerCase().includes('fetch');
    const msgError = buildMessageError(
      errObj?.errorCode || (isOffline ? 'network' : 'unknown'),
      errObj?.message || (error instanceof Error ? error.message : String(error)),
      errObj?.status,
    );

    chatErrorBus.publishFromMessage(msgError);

    const fallbackMsg: Message = {
      id: generateId(),
      role: 'guru',
      content: '',
      timestamp: new Date(),
      error: msgError,
    };
    setMessages((prev) => [...prev, fallbackMsg]);
  } finally {
    setIsTyping(false);
    setShowInstantPill(false);
    maybeSummarize();
  }
};

const handleSuggestionClick = (text: string) => {
  setInputValue(text);
};

// ── Regenerate last guru response ─────────────────────────────────
const handleRegenerate = useCallback(() => {
  if (isStreaming || isTyping) return;
  // Capture last user text BEFORE mutating messages state
  const lastUserIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') return i;
    }
    return -1;
  })();
  const lastUserMsg = lastUserIdx >= 0 ? messages[lastUserIdx] : undefined;
  if (!lastUserMsg) return;
  const lastGuruIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'guru') return i;
    }
    return -1;
  })();
  const baseMessages = lastGuruIdx >= 0
    ? messages.filter((_, i) => i !== lastGuruIdx)
    : messages;
  const historyMessages = baseMessages.slice(0, lastUserIdx);
  const fakeEvent = { preventDefault: () => { } } as React.FormEvent;
  handleSubmit(fakeEvent, lastUserMsg.content, {
    appendUser: false,
    baseMessages,
    historyMessages,
    bypassCache: true,
  });
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [isStreaming, isTyping, messages, currentLanguage]);
// ─────────────────────────────────────────────────────────────────

// Legacy fallback (kept for API stability): copy message text into composer.
// No longer wired into MessageList — inline edit (handleSubmitEdit) is preferred.

// ── Inline edit: replace a past user message and regenerate from there ──
const handleSubmitEdit = useCallback((messageId: string, newContent: string) => {
  if (isStreaming || isTyping) return;
  const idx = messages.findIndex((m) => m.id === messageId);
  if (idx < 0) return;
  const updatedUserMsg: Message = { ...messages[idx], content: newContent, timestamp: new Date() };
  // Keep history up to (but not including) the edited message; we'll resubmit it.
  const baseMessages = [...messages.slice(0, idx), updatedUserMsg];
  const historyMessages = messages.slice(0, idx);
  const fakeEvent = { preventDefault: () => { } } as React.FormEvent;
  handleSubmit(fakeEvent, newContent, {
    appendUser: false,
    baseMessages,
    historyMessages,
    bypassCache: true,
  });
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [isStreaming, isTyping, messages]);

const handleNewConversation = () => {
  stopSpeaking();
  const newConversation = createNewConversation();

  const welcomeMessage: Message = {
    id: generateId(),
    role: 'guru',
    content: 'The slate is clean, dear one. Let us begin anew. What would you like to explore?',
    timestamp: new Date(),
  };

  newConversation.messages = [welcomeMessage];
  newConversation.preview = getConversationPreview([welcomeMessage]);
  saveConversation(newConversation);

  setCurrentConversation(newConversation);
  setCurrentConversationId(newConversation.id);
  setMessages([welcomeMessage]);
  setRefreshTrigger(prev => prev + 1);
};

const handleSelectConversation = (conversation: Conversation) => {
  stopSpeaking();
  setCurrentConversation(conversation);
  setCurrentConversationId(conversation.id);
  setMessages(conversation.messages);
  // Scroll to bottom when switching conversations
  isNearBottomRef.current = true;
  requestAnimationFrame(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  });
};

const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
  // Up-arrow (when input empty) recalls the last user message into the draft.
  if (e.key === 'ArrowUp' && !inputValue) {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) {
      e.preventDefault();
      setInputValue(lastUser.content);
      // After state flush, move caret to end + autosize
      requestAnimationFrame(() => {
        const ta = inputRef.current;
        if (ta) {
          ta.style.height = 'auto';
          ta.style.height = `${Math.min(ta.scrollHeight, 128)}px`;
          ta.setSelectionRange(ta.value.length, ta.value.length);
        }
      });
      return;
    }
  }
  // Ctrl/Cmd+Enter sends; plain Enter still sends (legacy); Shift+Enter = newline.
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSubmit(e);
  }
};

// ── Keyboard shortcuts (Ctrl+Enter / Ctrl+Shift+O / Ctrl+/) ──────
useChatShortcuts({
  onSubmit: () => {
    if (inputValue.trim() && !isTyping && !isStreaming) {
      handleSubmit({ preventDefault: () => { } } as React.FormEvent);
    }
  },
  onNewChat: handleNewConversation,
  onFocusInput: () => inputRef.current?.focus(),
});

// ── Left-edge swipe opens mobile conversation sheet (D20) ────────
useSwipeGesture({
  edgeOnly: true,
  onSwipeRight: () => setShowMobileSheet(true),
  enabled: !showMobileSheet,
});

const showStarters = messages.length <= 1 && messages[0]?.role === 'guru';

return (
  <div className="h-dvh flex bg-background relative overflow-hidden">
    {/* Background */}
    <div className="fixed inset-0 bg-spiritual-gradient pointer-events-none" />
    <FloatingParticles />

    {/* Desktop Sidebar */}
    <DesktopSidebar
      isCollapsed={sidebarCollapsed}
      onToggleCollapse={toggleSidebar}
      onNewConversation={handleNewConversation}
      onOpenSereneMind={() => openSereneMind()}
      onSelectConversation={handleSelectConversation}
      currentConversationId={currentConversation?.id}
    />

    {/* Main Chat Area */}
    <div className="flex-1 flex flex-col min-w-0 min-h-0 relative z-10">
      {/* Header */}
      <ChatHeader
        onClearChat={handleNewConversation}
        onOpenMobileMenu={() => setShowMobileSheet(true)}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={toggleSidebar}
      />

      {/* Global chat error banner */}
      <ChatErrorBanner onRetry={handleRegenerate} />


      {/* Messages Area — this is the scroll container */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 scrollbar-spiritual"
      >
        <div ref={innerContentRef} className="max-w-3xl mx-auto space-y-3">
          <MessageList
            messages={messages}
            streamingId={streamingMessageId}
            streamingContent={streamingContent}
            onRegenerate={handleRegenerate}
            onEditUserMessage={undefined}
            onSubmitEdit={handleSubmitEdit}
            scrollContainerRef={scrollContainerRef}
          />

          {/* Suggested starters */}
          {showStarters && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="space-y-4 pt-4"
            >
              {/* Compact daily teaching banner */}
              {dailyTeaching && dailyTeaching.caption && (
                <div className="mx-auto max-w-md rounded-xl border border-ojas/20 bg-ojas/5 backdrop-blur-sm p-4 flex items-start gap-3">
                  <Sparkles className="w-4 h-4 text-ojas shrink-0 mt-0.5 animate-pulse" />
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold text-ojas uppercase tracking-widest mb-1">Today&apos;s Wisdom</p>
                    <p className="text-sm text-foreground/80 font-serif italic leading-relaxed line-clamp-3">
                      &ldquo;{dailyTeaching.caption}&rdquo;
                    </p>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 w-full">
                {STARTER_SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => handleSuggestionClick(suggestion)}
                    className="px-4 py-3 rounded-2xl text-sm font-serif border border-ojas/25 bg-card/60 hover:bg-ojas/10 hover:border-ojas/50 text-foreground/85 hover:text-foreground transition-all text-center leading-snug min-h-[56px] flex items-center justify-center"
                  >
                    <span className="line-clamp-2">{suggestion}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          {/* Instant thinking pill — shows immediately on submit, before backend status events */}
          <AnimatePresence>
            {showInstantPill && pipelineSteps.length === 0 && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4, transition: { duration: 0.2 } }}
                className="group flex items-start gap-2.5 justify-start my-2"
              >
                {/* Avatar — identical to guru avatar in ChatMessage */}
                <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Sparkles className="w-3 h-3 text-ojas animate-pulse" />
                </div>

                {/* Instant pill with subtle pulse animation */}
                <div className="inline-flex items-center gap-2 rounded-full border border-ojas/30 bg-ojas/5 hover:bg-ojas/10 transition-colors px-3 py-1.5 text-[12px] text-foreground/80">
                  <motion.span
                    className="w-2 h-2 rounded-full bg-ojas"
                    animate={{ scale: [1, 1.3, 1], opacity: [0.5, 1, 0.5] }}
                    transition={{ duration: 1.2, repeat: Infinity }}
                  />
                  <span className="font-medium">Analyzing your question…</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Pipeline Visualization */}
          <ThinkingPills steps={pipelineSteps} visible={showPipeline} heartbeat={pipelineHeartbeat} />

          {/* Streaming skeleton — only show before empty guru bubble is added */}
          <AnimatePresence>
            {isTyping && !isStreaming && messages.length > 0 && messages[messages.length - 1].role === 'user' && (
              <OptimisticPlaceholder />
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

          {/* Thinking / first-token indicator — shown while streaming but content hasn't arrived yet */}
          <AnimatePresence>
            {isStreaming && streamingContent === '' && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="flex items-start gap-3"
              >
                <div className="w-8 h-8 rounded-full bg-ojas/15 flex items-center justify-center flex-shrink-0 border border-ojas/25 animate-pulse">
                  <Sparkles className="w-4 h-4 text-ojas/70" />
                </div>
                <div className="flex flex-col gap-1.5">
                  <div className="glass-card px-4 py-2.5 rounded-2xl rounded-tl-sm">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <motion.div
                        className="w-1.5 h-1.5 rounded-full bg-ojas/60"
                        animate={{ scale: [1, 1.4, 1], opacity: [0.5, 1, 0.5] }}
                        transition={{ duration: 1.8, repeat: Infinity }}
                      />
                      <span className="italic font-serif text-foreground/70">The Guru is reflecting on the sacred teachings...</span>
                    </div>
                  </div>
                  <p className="text-[11px] text-muted-foreground/60 pl-1">Delving deep into ancient wisdom for your answer</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Scroll anchor */}
          <div ref={messagesEndRef} className="h-1" />
        </div>
      </div>

      {/* Scroll-to-bottom FAB — positioned relative to the chat column */}
      <ScrollToBottomFab
        visible={showScrollFab}
        unreadCount={unreadCount}
        onClick={() => scrollToBottom('smooth')}
      />

      {/* Input Area */}
      <footer className="relative z-20 shrink-0 px-3 sm:px-4 pb-3 pt-2 pb-safe border-t border-border/30 bg-background/80 backdrop-blur-md">
        <div className="max-w-3xl mx-auto">
          {/* Subtle practice chips */}
          <div className="flex flex-wrap justify-center gap-1.5 sm:gap-2 mb-2">
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
                  <motion.div className="flex gap-0.5">
                    {[0, 1, 2, 3].map((i) => (
                      <motion.div
                        key={i}
                        className="w-1 bg-prana rounded-full"
                        animate={{ height: ['8px', '16px', '8px'] }}
                        transition={{ duration: 0.5, repeat: Infinity, delay: i * 0.1 }}
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
          <div
            className={`rounded-2xl border bg-card/90 backdrop-blur-lg transition-all duration-300 shadow-sm ${inputFocused ? 'border-ojas/40 shadow-lg shadow-ojas/8 ring-1 ring-ojas/15' : 'border-border/50'
              } ${isListening ? 'border-ojas/50 shadow-ojas/15 ring-1 ring-ojas/20' : ''}`}
          >
            {isAwaitingSereneMind && (
              <div className="flex items-center justify-between px-4 py-2 border-b border-border/40 bg-ojas/5 rounded-t-2xl">
                <span className="text-xs text-ojas font-medium">
                  Please do Serene Mind now to unlock the chat.
                </span>
                <button
                  onClick={() => openSereneMind('breathing', true)}
                  className="px-3 py-1 rounded-full bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground text-xs font-semibold hover:shadow-md transition-all"
                >
                  Open Serene Mind
                </button>
              </div>
            )}
            <form onSubmit={handleSubmit}>
              <div className="flex items-end gap-2 px-3 pt-2.5 pb-1.5">
                <textarea
                  ref={inputRef}
                  value={inputValue}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  onFocus={() => setInputFocused(true)}
                  onBlur={() => setInputFocused(false)}
                  placeholder={
                    isAwaitingSereneMind
                      ? 'Do Serene Mind now (say "open Serene Mind" to begin)…'
                      : isListening
                        ? 'Speak now…'
                        : "Share what's on your heart…"
                  }
                  rows={1}
                  aria-label="Your message"
                  className="flex-1 bg-transparent border-none outline-none resize-none text-foreground placeholder:text-muted-foreground py-1.5 px-1 max-h-32 scrollbar-spiritual text-[14px] leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ minHeight: '36px' }}
                />
                <button
                  type="submit"
                  disabled={!inputValue.trim() || isTyping || isStreaming}
                  className="p-2.5 rounded-full bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm hover:shadow-md hover:scale-105 active:scale-95"
                  aria-label="Send message"
                >
                  <Send className="w-4 h-4" />
                </button>
              </div>
            </form>

            {/* Secondary controls row */}
            <div className="flex items-center justify-between px-3 pb-2 pt-1">
              <LanguageSelector
                value={currentLanguage}
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
          </div>

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

    {/* Quick Wisdom Card — portaled to body to avoid sidebar z-index conflicts */}
    {showQuickWisdomCard && createPortal(
      <WisdomCardGenerator
        isOpen={showQuickWisdomCard}
        onClose={() => setShowQuickWisdomCard(false)}
        content={
          messages.length > 0
            ? (messages.filter(m => m.role === 'guru').pop()?.content ?? '')
            : ''
        }
      />,
      document.body
    )}

    {/* Daily Teaching Modal */}
    <DailyTeaching />
  </div>
);
};
