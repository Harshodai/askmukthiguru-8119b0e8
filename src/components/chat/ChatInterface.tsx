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
  updateConversationSummary,
} from '@/lib/chatStorage';
import { derivePrePracticeInsights } from '@/lib/profileStorage';
import { sendMessage, sendMessageStreaming, MessagePayload, StreamChunk, generateSummary, generateConversationTitle, setLanguage as setAILanguage } from '@/lib/aiService';
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
  const { open: openSereneMind } = useSereneMind();
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
  const { teaching: dailyTeaching } = useDailyTeaching();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
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
    messagesEndRef.current?.scrollIntoView({ behavior });
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
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
    });
  }, [profileLoading]);

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
          <button
            onClick={() => handleLanguageChange(detectedLangObj.code)}
            className="px-3 py-1.5 rounded-md bg-ojas text-white text-xs font-medium hover:bg-ojas/90"
          >
            Switch
          </button>
        ) as unknown as undefined,
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

  // Scroll to bottom when new messages arrive (only if near bottom)
  useEffect(() => {
    if (isNearBottomRef.current) {
      // Use requestAnimationFrame for reliable scroll after DOM update
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      });
    } else if (messages.length > 0 && messages[messages.length - 1].role === 'guru') {
      setUnreadCount(prev => prev + 1);
    }
  }, [messages, isTyping, scrollToBottom]);

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

    // Try streaming first
    const streamingGuruId = generateId();
    let streamingWorked = false;
    let fullContent = '';
    let finalIntent = 'CASUAL';
    // Declared OUTSIDE try so finally block can access it
    let checkpointInterval: ReturnType<typeof setInterval> | undefined;

    try {
      const stream = sendMessageStreaming(
        messageHistory, 
        userMessage.content, 
        meditationStep,
        currentConversation?.summary,
        currentConversation?.id
      );
      
      // Show pipeline thinking pills
      setPipelineSteps([]);
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
      for await (const chunk of stream) {
        if (chunk.type === 'status') {
          // Pipeline status update → add or advance pills
          const label = mapStatusToLabel(chunk.text);
          setPipelineSteps((prev) => {
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
          // Final metadata from backend — citations, intent, meditationStep
          streamedCitations = chunk.citations;
          finalIntent = chunk.intent;
          streamedMedStep = chunk.meditationStep;
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
        }

        // Update the streaming message state locally without mapping entire array
        fullContent += chunk.text;
        setStreamingContent(fullContent);
        // Keep scrolling during streaming if near bottom
        if (isNearBottomRef.current) {
          requestAnimationFrame(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
          });
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

        // Trigger Serene Mind if distress detected in streaming
        if (finalIntent === 'DISTRESS' && (streamedMedStep || 0) > 0) {
          openSereneMind('audio');
        }

        // Heuristic fallback: if LLM text explicitly describes a Serene Mind session
        // but backend didn't flag DISTRESS (e.g. serene_mind module not running),
        // open the modal so the real guided session plays alongside the text.
        if (finalIntent !== 'DISTRESS') {
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
    } catch {
      // Streaming failed — show toast if partial content was received
      if (fullContent) {
        setMessages((prev) =>
          prev.map((m) => (m.id === streamingGuruId ? { ...m, content: fullContent } : m))
        );
        toast({ title: 'Connection interrupted', description: 'Response may be incomplete.' });
        streamingWorked = true; // Keep partial content
      }
    } finally {
      clearInterval(checkpointInterval);
      setIsStreaming(false);
      setStreamingMessageId(undefined);
      setStreamingContent('');
      setShowPipeline(false);
      setPipelineSteps([]);
      // Clear stream checkpoint on completion
      try {
        sessionStorage.removeItem('askmukthiguru_stream_checkpoint');
      } catch {
        // Storage can be unavailable in hardened browser modes.
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
      const response = await sendMessage(
        messageHistory, 
        userMessage.content, 
        meditationStep,
        currentConversation?.summary,
        currentConversation?.id
      );

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
          citations: response.citations && response.citations.length > 0 ? response.citations : undefined,
        };
        setMessages((prev) => [...prev, guruMessage]);
        setCachedResponse(cacheKey, response.content, guruMessage.citations);

        if (response.meditationStep !== undefined) {
          setMeditationStep(response.meditationStep);
        }

        if (response.intent === 'DISTRESS' && (response.meditationStep || 0) > 0) {
          openSereneMind('audio');
        }

        // Heuristic fallback for non-streaming path (same logic as streaming)
        if (response.intent !== 'DISTRESS') {
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
    } finally {
      setIsTyping(false);
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
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    handleSubmit(fakeEvent, lastUserMsg.content, {
      appendUser: false,
      baseMessages,
      historyMessages,
      bypassCache: true,
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isStreaming, isTyping, messages, currentLanguage]);
  // ─────────────────────────────────────────────────────────────────

  const handleEditUserMessage = useCallback((message: Message) => {
    setInputValue(message.content);
    requestAnimationFrame(() => {
      inputRef.current?.focus();
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
        inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 128)}px`;
      }
    });
  }, []);

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
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
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
        handleSubmit({ preventDefault: () => {} } as React.FormEvent);
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
      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        {/* Header */}
        <ChatHeader 
          onClearChat={handleNewConversation}
          onOpenMobileMenu={() => setShowMobileSheet(true)}
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
        />

        {/* Messages Area — this is the scroll container */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 scrollbar-spiritual"
        >
          <div className="max-w-3xl mx-auto space-y-3">
            <MessageList
              messages={messages}
              streamingId={streamingMessageId}
              streamingContent={streamingContent}
              onRegenerate={handleRegenerate}
              onEditUserMessage={handleEditUserMessage}
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
                <div className="flex flex-wrap justify-center gap-2">
                  {STARTER_SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => handleSuggestionClick(suggestion)}
                      className="px-4 py-2 rounded-full text-sm border border-ojas/30 bg-ojas/5 text-foreground hover:bg-ojas/15 hover:border-ojas/50 transition-all"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {/* Pipeline Thinking Pills */}
            <ThinkingPills steps={pipelineSteps} visible={showPipeline} />

            {/* Streaming skeleton */}
            <AnimatePresence>
              {isStreaming && messages.length > 0 && messages[messages.length - 1].content === '' && !showPipeline && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex items-start gap-3"
                >
                  <div className="w-7 h-7 rounded-full bg-ojas/20 flex items-center justify-center flex-shrink-0 border border-ojas/30">
                    <div className="w-3.5 h-3.5 rounded-full bg-ojas/50" />
                  </div>
                  <div className="border-l-2 border-ojas/20 pl-3.5 space-y-2 w-48">
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
              className={`rounded-2xl border bg-card/90 backdrop-blur-lg transition-all duration-300 shadow-sm ${
                inputFocused ? 'border-ojas/40 shadow-lg shadow-ojas/8 ring-1 ring-ojas/15' : 'border-border/50'
              } ${isListening ? 'border-ojas/50 shadow-ojas/15 ring-1 ring-ojas/20' : ''}`}
            >
              <form onSubmit={handleSubmit}>
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
