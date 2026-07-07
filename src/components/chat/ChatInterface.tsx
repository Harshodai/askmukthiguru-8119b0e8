import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, AlertCircle, Sparkles, Share2, BookOpen, RefreshCw, Square } from 'lucide-react';

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
import { buildGreeting, greetingPrefix, buildGreetingSubline } from '@/lib/greeting';
import { telemetryEvents } from '@/lib/telemetryEvents';
import { queueMemoryExtraction } from '@/lib/aiService';
import { ChatErrorBanner } from './ChatErrorBanner';

import { derivePrePracticeInsights } from '@/lib/profileStorage';
import { sendMessage, sendMessageStreaming, MessagePayload, StreamChunk, generateSummary, generateConversationTitle, setLanguage as setAILanguage, ProactiveSereneMindTrigger, getAIConfig } from '@/lib/aiService';
import { memoryApi } from '@/lib/memoryApi';
import { supabase } from '@/integrations/supabase/client';
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
import { ChatEmptyState } from './ChatEmptyState';
import { ConversationSourcesPanel } from './ConversationSourcesPanel';
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
import { SlashCommandMenu, type SlashCommandId } from './SlashCommandMenu';
import { downloadConversationAsMarkdown } from '@/lib/exportConversation';
import { useDailyTeaching } from '@/hooks/useDailyTeaching';
import { useAssistants } from '@/hooks/useAssistants';
import { ChatComposer } from './ChatComposer';

import {
  OptimisticPlaceholder,
  SlowResponseHint,
  buildMessageError,
  buildPersonalisedWelcome,
} from './ChatHelpers';

// ── Suggested starter prompt-cards (ChatGPT-style, spiritually themed) ──
import { Flower2, Heart as HeartIcon, Compass } from 'lucide-react';

const STARTER_CARDS = [
  { id: 'reflect', icon: Compass, eyebrow: 'Reflect', prompt: 'What is the Beautiful State, and how do I begin?' },
  { id: 'meditate', icon: Flower2, eyebrow: 'Meditate', prompt: 'Guide me through a short breathing meditation' },
  { id: 'heal', icon: HeartIcon, eyebrow: 'Heal', prompt: "I'm feeling overwhelmed — help me find calm" },
  { id: 'learn', icon: BookOpen, eyebrow: 'Learn', prompt: 'Share a teaching from Sri Preethaji on suffering' },
] as const;

const STARTER_SUGGESTIONS = STARTER_CARDS.map((c) => c.prompt);

export const ChatInterface = () => {
  const [currentConversation, setCurrentConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sourcesPanelOpen, setSourcesPanelOpen] = useState(false);
  const [sourcesFilterMessageId, setSourcesFilterMessageId] = useState<string | null>(null);
  const uniqueSourcesCount = useMemo(() => {
    const set = new Set<string>();
    for (const m of messages) {
      if (m.role !== 'guru') continue;
      for (const c of m.citations ?? []) if (c) set.add(c);
    }
    return set.size;
  }, [messages]);
  const jumpToMessage = useCallback((id: string) => {
    const el = document.querySelector<HTMLElement>(`[data-message-id="${id}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('ring-2', 'ring-ojas/60', 'ring-offset-2', 'ring-offset-background', 'transition');
    window.setTimeout(() => {
      el.classList.remove('ring-2', 'ring-ojas/60', 'ring-offset-2', 'ring-offset-background');
    }, 1800);
  }, []);
  const handleCitationClick = useCallback((messageId: string, _citationIndex: number) => {
    setSourcesFilterMessageId(messageId);
    setSourcesPanelOpen(true);
  }, []);
  // Keyboard shortcut: "s" opens/closes the Sources panel (skips when typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 's' && e.key !== 'S') return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      e.preventDefault();
      setSourcesPanelOpen((v) => !v);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);


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
  const { selected } = useAssistants();
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
  /** AbortController for the in-flight streaming request — Stop button calls .abort(). */
  const streamControllerRef = useRef<AbortController | null>(null);
  /** The current background job ID running on the backend. */
  const currentJobIdRef = useRef<string | null>(null);
  const tokenBufferRef = useRef('');
  const rafScheduledRef = useRef(false);
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

  // ── Esc to stop generating ───────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && streamControllerRef.current) {
        streamControllerRef.current.abort();
        if (currentJobIdRef.current) {
          const { endpoint } = getAIConfig();
          const baseUrl = endpoint?.replace(/\/api\/chat\/?$/, '') || '';
          const jobId = currentJobIdRef.current;
          currentJobIdRef.current = null;
          import('@/lib/chat/auth').then(async ({ getAccessToken }) => {
            try {
              const token = await getAccessToken();
              await fetch(`${baseUrl}/api/jobs/${jobId}`, {
                method: 'DELETE',
                headers: {
                  ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
              });
            } catch (err) {
              console.error('Failed to cancel job:', err);
            }
          });
        }
        if (inputRef.current) {
          inputRef.current.focus();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // ── Telemetry failure → toast ────────────────────────────────────
  useEffect(() => telemetryEvents.subscribe((title, summary) => {
    toast({ title, description: summary, variant: 'default', duration: 5000 });
  }), [toast]);

  // ── Textarea auto-resize ─────────────────────────────────────────
  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    const ta = e.target;
    ta.style.height = '36px';
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
        content: buildPersonalisedWelcome(profile.prePracticeLog, selected?.slug),
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

    const newLangObj = LANGUAGES.find((l) => l.code === code);
    toast({
      title: '🌐 Language Switched',
      description: `Language set to ${newLangObj?.name ?? code}.`,
      duration: 3000,
    });

    if (isListening) {
      stopListening();
      setTimeout(() => startListening(), 150);
    }
  }, [isListening, stopListening, startListening, updateProfile, toast]);

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
      // Write-back: track last conversation for multi-device resume.
      // Fire-and-forget; never blocks UI; ignores errors (e.g. anon user).
      void (async () => {
        try {
          const { supabase } = await import('@/integrations/supabase/client');
          const { data: { session } } = await supabase.auth.getSession();
          if (!session) return;
          await supabase.from('profiles').update({
            last_conversation_id: updatedConversation.id,
            last_message_id: messages[messages.length - 1]?.id ?? null,
            last_active_at: new Date().toISOString(),
          }).eq('id', session.user.id);
          localStorage.setItem('askmukthiguru_last_seen', Date.now().toString());
        } catch {
          // best-effort
        }
      })();
    }
  }, [messages]);

  // Track unread messages when we are not near the bottom
  useEffect(() => {
    if (!isNearBottomRef.current && messages.length > 0 && messages[messages.length - 1].role === 'guru') {
      setUnreadCount(prev => prev + 1);
    }
  }, [messages]);

  const handleSubmit = async (
    e?: React.FormEvent | React.KeyboardEvent<HTMLTextAreaElement> | React.MouseEvent,
    overrideText?: string,
    options: {
      appendUser?: boolean;
      baseMessages?: Message[];
      historyMessages?: Message[];
      bypassCache?: boolean;
    } = {},
  ) => {
    if (e && 'preventDefault' in e) {
      e.preventDefault();
    }
    const textToSend = overrideText ?? inputValue;
    // Race condition fix: if already streaming/typing, abort previous request before starting new one
    if (isTyping || isStreaming) {
      streamControllerRef.current?.abort();
      if (currentJobIdRef.current) {
        fetch(`/api/jobs/${currentJobIdRef.current}`, { method: 'DELETE' }).catch(() => {});
      }
      setIsTyping(false);
      setIsStreaming(false);
      setShowPipeline(false);
      setPipelineSteps([]);
      setShowInstantPill(false);
      streamControllerRef.current = null;
      currentJobIdRef.current = null;
    }
    if (!textToSend.trim()) {
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

    // Reset textarea height and refocus
    if (inputRef.current) {
      inputRef.current.style.height = '36px';
      inputRef.current.focus();
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

    // ── Memory: fetch relevant context before sending ─────────────────
    // failures are silent (best-effort).
    let seekerContext = '';
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session) {
        const relevant = await memoryApi.getRelevant(userMessage.content, 5);
        if (relevant.length > 0) {
          seekerContext = relevant.map((m) => `- ${m.content}`).join('\n');
        }
      }
    } catch { /* memory is best-effort — never block the chat */ }

    // Try streaming first (skip when awaiting Serene Mind to avoid leaking blocked content during stream)
    const streamingGuruId = generateId();
    let streamingWorked = false;
    let fullContent = '';
    let finalIntent = 'CASUAL';
    let checkpointInterval: ReturnType<typeof setInterval> | undefined;

    if (!isAwaitingSereneMind) {
      try {
        const lastSereneMindAt = getLastCompletedMeditationTimestamp();

        // Fresh AbortController for this turn — Stop button calls .abort().
        const controller = new AbortController();
        streamControllerRef.current = controller;

        const stream = sendMessageStreaming(
          messageHistory,
          userMessage.content,
          meditationStep,
          currentConversation?.summary,
          currentConversation?.id,
          lastSereneMindAt,
          seekerContext || undefined,
          controller.signal,
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
        let streamedFollowUpSuggestions: string[] = [];
        let streamedConfidenceScore: number | null = null;
        for await (const chunk of stream) {
          if (chunk.type === 'status') {
            if (chunk.jobId) {
              currentJobIdRef.current = chunk.jobId;
            }
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
            // Final metadata from backend — citations, intent, meditationStep, proactiveSereneMind, confidenceScore
            streamedCitations = chunk.citations;
            finalIntent = chunk.intent;
            streamedMedStep = chunk.meditationStep;
            streamedBlocked = chunk.blocked ?? false;
            streamedBlockReason = chunk.blockReason ?? null;
            streamedProactiveSereneMind = chunk.proactiveSereneMind ?? null;
            streamedFollowUpSuggestions = chunk.followUpSuggestions ?? [];
            streamedConfidenceScore = chunk.confidenceScore ?? null;
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
          tokenBufferRef.current = fullContent;
          if (!rafScheduledRef.current) {
            rafScheduledRef.current = true;
            requestAnimationFrame(() => {
              if (rafScheduledRef.current) {
                setStreamingContent(tokenBufferRef.current);
                // Keep scrolling during streaming if near bottom
                if (isNearBottomRef.current && scrollContainerRef.current) {
                  scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
                }
              }
            });
          }
        }

        if (fullContent) {
          streamingWorked = true;
          // Commit the final streamed content to the message list
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingGuruId
                ? {
                    ...m,
                    content: fullContent,
                    intent: finalIntent,
                    citations: streamedCitations.length > 0 ? streamedCitations : undefined,
                    followUpSuggestions: streamedFollowUpSuggestions.length > 0 ? streamedFollowUpSuggestions : undefined,
                    confidenceScore: streamedConfidenceScore ?? undefined,
                  }
                : m
            )
          );

          setStreamingMessageId(undefined);
          setStreamingContent('');

          setCachedResponse(cacheKey, fullContent, streamedCitations.length > 0 ? streamedCitations : undefined);

          // ── Memory: fire-and-forget extraction ───────────────────────────
          // Offload to aiService so ChatInterface stays clean.
          queueMemoryExtraction({
            userMessage: userMessage.content,
            assistantMessage: fullContent,
            conversationId: currentConversation?.id,
          });

          // Update meditation step from streaming metadata
          if (streamedMedStep !== undefined) {
            setMeditationStep(streamedMedStep);
          }

          // Trigger Serene Mind based on response signals
          if (streamedBlocked) {
            if (streamedBlockReason === 'circuit_breaker_open') {
              const err = buildMessageError('circuit_breaker', fullContent);
              setMessages((prev) => [
                ...prev,
                {
                  id: generateId(),
                  role: 'guru',
                  content: fullContent,
                  timestamp: new Date(),
                  error: err,
                },
              ]);
            } else {
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
                setSereneMindOnComplete(() => {
                  setIsAwaitingSereneMind(false);
                  setSereneMindOnComplete(null);
                });
                openSereneMind('breathing', true);
              }, 7000);
            }
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
            const customMed = streamedProactiveSereneMind?.custom_meditation;
            setTimeout(() => {
              setIsAwaitingSereneMind(true);
              setSereneMindOnComplete(() => {
                setIsAwaitingSereneMind(false);
                setSereneMindOnComplete(null);
              });
              openSereneMind('breathing', true, customMed?.steps, customMed?.source_teaching);
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
        const err = streamErr as { name?: string; errorCode?: string; status?: number; message?: string };
        const wasAborted =
          err?.name === 'AbortError' || streamControllerRef.current?.signal.aborted;
        if (wasAborted) {
          // User clicked Stop — keep whatever streamed, append a clear marker.
          const stopped = (fullContent || '').trimEnd() + '\n\n_Stopped by you._';
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingGuruId ? { ...m, content: stopped } : m,
            ),
          );
          streamingWorked = true;
        } else if (fullContent) {
          setMessages((prev) =>
            prev.map((m) => (m.id === streamingGuruId ? { ...m, content: fullContent } : m))
          );
          toast({ title: 'Connection interrupted', description: 'Response may be incomplete.' });
          streamingWorked = true;
        } else {
          const msgError = buildMessageError(err?.errorCode, err?.message, err?.status);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === streamingGuruId
                ? { ...m, content: '', error: msgError }
                : m,
            ),
          );
          streamingWorked = true;
          chatErrorBus.publishFromMessage(msgError, streamingGuruId);
        }
      } finally {
        clearInterval(checkpointInterval);
        rafScheduledRef.current = false;
        tokenBufferRef.current = '';
        setIsStreaming(false);
        setStreamingMessageId(undefined);
        setStreamingContent('');
        setShowPipeline(false);
        setPipelineSteps([]);
        setShowInstantPill(false);
        setPipelineHeartbeat(false);
        streamControllerRef.current = null;
        currentJobIdRef.current = null;
        if (inputRef.current) {
          inputRef.current.focus();
        }
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
        seekerContext || undefined,
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
          // If the backend returned an error and no content, show a friendly fallback instead of an empty bubble.
          content: response.content || (response.errorCode
            ? 'The Guru is resting. Please try again in a moment.'
            : ''),
          timestamp: new Date(),
          citations: response.citations && response.citations.length > 0 ? response.citations : undefined,
          error: responseError,
          followUpSuggestions: response.followUpSuggestions && response.followUpSuggestions.length > 0 ? response.followUpSuggestions : undefined,
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
              setSereneMindOnComplete(() => {
                setIsAwaitingSereneMind(false);
                setSereneMindOnComplete(null);
              });
              const customMed = response.proactiveSereneMind?.custom_meditation;
              openSereneMind('breathing', true, customMed?.steps, customMed?.source_teaching);
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
  // Prompt cards should behave like Claude.ai — one click sends immediately.
  setInputValue('');
  if (inputRef.current) inputRef.current.focus();
  requestAnimationFrame(() => {
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    handleSubmit(fakeEvent, text);
  });
};

const handleInlineAction = (query: string) => {
  setInputValue(query);
  if (inputRef.current) {
    inputRef.current.focus();
  }
  requestAnimationFrame(() => {
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    handleSubmit(fakeEvent, query, { bypassCache: true });
  });
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

const handleExportConversation = useCallback(() => {
  if (!currentConversation || messages.length === 0) {
    toast({ title: 'Nothing to export yet', description: 'Send a message first.' });
    return;
  }
  try {
    const filename = downloadConversationAsMarkdown({ ...currentConversation, messages });
    toast({ title: 'Conversation exported', description: filename });
  } catch (err) {
    toast({
      title: 'Export failed',
      description: err instanceof Error ? err.message : 'Could not save the file.',
      variant: 'destructive',
    });
  }
}, [currentConversation, messages, toast]);

const runSlashCommand = useCallback(
  (id: SlashCommandId) => {
    setInputValue('');
    requestAnimationFrame(() => inputRef.current?.focus());
    switch (id) {
      case 'serene':
        openSereneMind();
        break;
      case 'meditate':
        setShowGuidedMeditation(true);
        break;
      case 'retry':
        handleRegenerate();
        break;
      case 'share':
        if (messages.some((m) => m.role === 'guru')) setShowQuickWisdomCard(true);
        else toast({ title: 'No Guru message yet', description: 'Ask something first.' });
        break;
      case 'clear':
        handleNewConversation();
        break;
      case 'lang':
        toast({ title: 'Language picker', description: 'Use the globe icon below the input.' });
        break;
      case 'teach':
        // Prefill the composer so the user can type the concept they want explained.
        setInputValue('Please explain step-by-step: ');
        requestAnimationFrame(() => {
          const ta = inputRef.current;
          if (ta) {
            ta.focus();
            ta.setSelectionRange(ta.value.length, ta.value.length);
          }
        });
        break;
      case 'reflect':
        // Inject a reflection-question request as a user message immediately.
        handleSubmit(
          { preventDefault: () => {} } as React.FormEvent,
          'Give me a reflection question based on our conversation so far.',
        );
        break;
    }
  },
  [handleRegenerate, handleNewConversation, handleSubmit, messages, openSereneMind, toast],
);



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
          ta.style.height = '36px';
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

const isLandingMode = messages.length <= 1 && messages[0]?.role === 'guru';

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
        onExport={handleExportConversation}
        onOpenSources={() => setSourcesPanelOpen(true)}
        sourcesCount={uniqueSourcesCount}
      />


      {/* Global chat error banner */}
      <ChatErrorBanner onRetry={handleRegenerate} />


      {/* Messages Area — this is the scroll container */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-3 sm:px-6 lg:px-8 pt-4 sm:pt-6 pb-2 scrollbar-spiritual"
      >
        <div ref={innerContentRef} className="max-w-3xl mx-auto min-h-full">
          {isLandingMode ? (
            /* ── Landing State (Claude-inspired, minimal, particles) ── */
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center justify-center min-h-[calc(100dvh-12rem)] gap-4 py-6 sm:gap-5 sm:py-8"
            >
              <div className="text-center px-4">
                <motion.h2
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="text-[26px] sm:text-4xl font-serif text-foreground/95 tracking-tight leading-tight"
                >
                  {buildGreeting(selected?.slug, profile.displayName ?? '')}
                </motion.h2>
                <motion.p
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                  className="mt-3 text-sm sm:text-base text-muted-foreground/75 leading-relaxed max-w-md mx-auto font-serif italic"
                >
                  {buildGreetingSubline()}
                </motion.p>
              </div>

              <div className="w-full max-w-2xl px-4 mt-2">
                <ChatComposer
                                  inputValue={inputValue}
                                  inputRef={inputRef}
                                  onInputChange={handleInputChange}
                                  onKeyDown={handleKeyDown}
                                  onSubmit={(e) => handleSubmit(e)}
                                  onStop={() => {
                                    streamControllerRef.current?.abort();
                                    if (inputRef.current) inputRef.current.focus();
                                  }}
                                  isTyping={isTyping}
                                  isStreaming={isStreaming}
                                  isAwaitingSereneMind={isAwaitingSereneMind}
                                  isListening={isListening}
                                  currentLanguage={currentLanguage}
                                  voiceEnabled={voiceEnabled}
                                  ttsEnabled={ttsEnabled}
                                  isSpeaking={isSpeaking}
                                  inputFocused={inputFocused}
                                  showPipeline={showPipeline}
                                  pipelineSteps={pipelineSteps}
                                  pipelineHeartbeat={pipelineHeartbeat}
                                  showInstantPill={showInstantPill}
                                  isLandingMode={true}
                                  onVoiceToggle={handleVoiceToggle}
                                  onTtsToggle={handleTtsToggle}
                                  onLanguageChange={handleLanguageChange}
                                  onSereneMind={() => openSereneMind()}
                                  onGuidedMeditation={() => setShowGuidedMeditation(true)}
                                  onFocus={() => setInputFocused(true)}
                                  onBlur={() => setInputFocused(false)}
                                  onSlashCommand={(cmd) => {
                                    setInputValue('');
                                    switch (cmd) {
                                      case 'serene': openSereneMind(); break;
                                      case 'meditate': setShowGuidedMeditation(true); break;
                                      case 'retry': if (messages.length > 0) handleRegenerate(); break;
                                      case 'clear': handleNewConversation(); break;
                                    }
                                  }}
                                />
              </div>

              {/* Compact starter pills */}
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="w-full max-w-2xl px-4 flex flex-wrap items-center justify-center gap-2 mt-2"
              >
                {STARTER_CARDS.map((card, idx) => (
                  <motion.button
                    key={card.id}
                    type="button"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 + idx * 0.05 }}
                    onClick={() => handleSuggestionClick(card.prompt)}
                    className="px-3 py-1.5 rounded-full border border-border/70 bg-card/50 hover:bg-card/80 hover:border-ojas/30 text-xs text-muted-foreground/90 transition-colors"
                  >
                    {card.prompt}
                  </motion.button>
                ))}
              </motion.div>

              {messages.length === 1 && (
                <div className="w-full max-w-2xl px-4">
                  <ChatEmptyState
                    currentConversationId={currentConversation?.id}
                    onResume={handleSelectConversation}
                  />
                </div>
              )}
            </motion.div>
          ) : (

            <>
                <div className="space-y-2 sm:space-y-3 pb-36 sm:pb-40">
                <MessageList
                  messages={messages}
                  streamingId={streamingMessageId}
                  streamingContent={streamingContent}
                  onRegenerate={handleRegenerate}
                  onEditUserMessage={undefined}
                  onSubmitEdit={handleSubmitEdit}
                  onAction={handleInlineAction}
                  onCitationClick={handleCitationClick}
                  scrollContainerRef={scrollContainerRef}
                />

                {/* Unified thinking indicator */}
                <div className="flex items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <ThinkingPills
                      steps={pipelineSteps}
                      visible={
                        showInstantPill ||
                        showPipeline ||
                        isTyping ||
                        (isStreaming && streamingContent === '')
                      }
                      heartbeat={pipelineHeartbeat}
                      fallbackLabel={
                        isStreaming && streamingContent === ''
                          ? 'The Guru is reflecting on the sacred teachings…'
                          : 'Analyzing your question…'
                      }
                    />
                    {isStreaming && streamingContent === '' && (
                      <div className="pl-10 -mt-1">
                        <SlowResponseHint visible />
                      </div>
                    )}
                  </div>
                  {(isStreaming || isTyping || showInstantPill) && (
                    <button
                      type="button"
                      onClick={() => {
                        streamControllerRef.current?.abort();
                        if (currentJobIdRef.current) {
                          const { endpoint } = getAIConfig();
                          const baseUrl = endpoint?.replace(/\/api\/chat\/?$/, '') || '';
                          const jobId = currentJobIdRef.current;
                          currentJobIdRef.current = null;
                          import('@/lib/chat/auth').then(async ({ getAccessToken }) => {
                            try {
                              const token = await getAccessToken();
                              await fetch(`${baseUrl}/api/jobs/${jobId}`, {
                                method: 'DELETE',
                                headers: {
                                  ...(token ? { Authorization: `Bearer ${token}` } : {}),
                                },
                              });
                            } catch (err) {
                              console.error('Failed to cancel job:', err);
                            }
                          });
                        }
                        if (inputRef.current) {
                          inputRef.current.focus();
                        }
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 mt-1 rounded-full text-[12px] font-medium text-foreground/80 border border-border/60 bg-background/80 hover:bg-destructive/10 hover:border-destructive/40 hover:text-destructive transition-colors flex-shrink-0"
                      aria-label="Stop generating"
                      title="Stop generating (Esc)"
                    >
                      <Square className="w-3 h-3 fill-current" />
                      Stop
                    </button>
                  )}
                </div>

                {/* Scroll anchor */}
                <div ref={messagesEndRef} className="h-1" />
              </div>

            </>
          )}
        </div>
      </div>

      {!isLandingMode && (
        <div className="relative z-20 shrink-0 px-3 sm:px-6 lg:px-8 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] bg-background/95 border-t border-border/20 shadow-[0_-18px_36px_hsl(var(--background)/0.96)]">
          <ChatComposer
            inputValue={inputValue}
            inputRef={inputRef}
            onInputChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onSubmit={(e) => handleSubmit(e)}
            onStop={() => {
              streamControllerRef.current?.abort();
              if (inputRef.current) inputRef.current.focus();
            }}
            isTyping={isTyping}
            isStreaming={isStreaming}
            isAwaitingSereneMind={isAwaitingSereneMind}
            isListening={isListening}
            currentLanguage={currentLanguage}
            voiceEnabled={voiceEnabled}
            ttsEnabled={ttsEnabled}
            isSpeaking={isSpeaking}
            inputFocused={inputFocused}
            showPipeline={showPipeline}
            pipelineSteps={pipelineSteps}
            pipelineHeartbeat={pipelineHeartbeat}
            showInstantPill={showInstantPill}
            isLandingMode={false}
            onVoiceToggle={handleVoiceToggle}
            onTtsToggle={handleTtsToggle}
            onLanguageChange={handleLanguageChange}
            onSereneMind={() => openSereneMind()}
            onGuidedMeditation={() => setShowGuidedMeditation(true)}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            onSlashCommand={(cmd) => {
              setInputValue('');
              switch (cmd) {
                case 'serene': openSereneMind(); break;
                case 'meditate': setShowGuidedMeditation(true); break;
                case 'retry': if (messages.length > 0) handleRegenerate(); break;
                case 'clear': handleNewConversation(); break;
              }
            }}
          />
        </div>
      )}

      {/* Scroll-to-bottom FAB — positioned relative to the chat column.
          Only meaningful once there's an actual conversation to scroll
          through; on the empty greeting screen the stacked content
          (heading + quote + input + suggestion cards) can exceed the
          viewport height on its own, which used to trigger this FAB to
          overlap the greeting content with nothing to "jump to". */}
      <ScrollToBottomFab
        visible={showScrollFab && messages.length > 0}
        unreadCount={unreadCount}
        onClick={() => scrollToBottom('smooth')}
      />

      {/* Floating indicators that appear above the scroll area */}
      <AnimatePresence>
        {isListening && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute left-1/2 -translate-x-1/2 bottom-28 z-30 flex items-center gap-2 px-4 py-2 rounded-full bg-ojas/20 border border-ojas/30"
          >
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
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {isSpeaking && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute left-1/2 -translate-x-1/2 bottom-28 z-30 flex items-center gap-2 px-4 py-2 rounded-full bg-prana/20 border border-prana/30"
          >
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
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {voiceError && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute left-1/2 -translate-x-1/2 bottom-28 z-30 max-w-[calc(100vw-2rem)] flex items-center gap-2 px-4 py-2 rounded-full bg-destructive/10 border border-destructive/30"
          >
            <AlertCircle className="w-4 h-4 text-destructive" />
            <span className="text-sm text-destructive truncate">{voiceError}</span>
          </motion.div>
        )}
      </AnimatePresence>
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

    {/* Conversation-wide Sources panel (ChatGPT-style side sheet) */}
    <ConversationSourcesPanel
      isOpen={sourcesPanelOpen}
      onClose={() => { setSourcesPanelOpen(false); setSourcesFilterMessageId(null); }}
      messages={messages.map((m) => ({ id: m.id, role: m.role, citations: m.citations }))}
      onJumpToMessage={jumpToMessage}
      filterMessageId={sourcesFilterMessageId}
      onClearFilter={() => setSourcesFilterMessageId(null)}
    />

  </div>
);
};

