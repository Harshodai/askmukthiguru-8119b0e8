import { useTranslation } from 'react-i18next';
import { forwardRef, useState, useCallback, memo, useRef, useEffect, Suspense, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ExternalLink, Share2, Shield, Copy, Check, RotateCcw, Pencil, BookOpen, Youtube, Play, AlertTriangle, LogIn, RefreshCw, Bookmark, StickyNote, Languages, Volume2, VolumeX } from 'lucide-react';
import { useNotes } from '@/hooks/useNotes';
import { useStudyNotebooks } from '@/hooks/useStudyNotebooks';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@/lib/chatStorage';
import { evidenceSupport } from '@/lib/chat/evidenceSupport';
import { FEATURE_FLAGS } from '@/lib/featureFlags';
import { cn } from '@/lib/utils';
import { useProfile } from '@/hooks/useProfile';
import { translateText } from '@/lib/aiService';
import { lazyWithRetry } from '@/lib/lazyWithRetry';
import { InlineActions, EngagementCard } from './InlineActions';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { createPortal } from 'react-dom';
import { memoryApi } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';
import { CitationPanel, type Citation } from './CitationPanel';
import { LiveLogisticsCards } from './LiveLogisticsCards';
import { EuAiBadge } from '@/components/compliance/EuAiBadge';
import { ProvenanceDrawer } from '@/components/compliance/ProvenanceDrawer';
import { CitationBadge, DiscourseVideoModal, type DiscourseCitation } from './CitationCard';
import { LinkSearchModal } from './LinkSearchModal';
import { SacredPracticeWidget } from './SacredPracticeWidget';
import { ReflectionChips } from './ReflectionChips';

interface ChatMessageProps {
  message: Message;
  queryText?: string;
  index?: number;
  isStreaming?: boolean;
  isLastGuru?: boolean;
  onRegenerate?: () => void;
  onEditUserMessage?: (message: Message) => void;
  onSubmitEdit?: (messageId: string, newContent: string) => void;
  onAction?: (query: string) => void;
  /** Fired when the reader clicks an inline `[N]` citation marker in the answer. */
  onCitationClick?: (messageId: string, citationIndex: number) => void;
}

/**
 * Preprocess assistant content so that literal `[N]` (or `[1, 2]`) citation
 * markers become clickable markdown links (`href="#cite-N"`) that our custom
 * `a` renderer converts into accessible buttons.
 * Only markers whose N maps to a real citation URL are transformed.
 */
const injectCitationLinks = (content: string, citationsLen: number): string => {
  if (!content || citationsLen === 0) return content;
  // Match [1], [ 2 ], [1,2], [1, 2, 3] — expand comma lists into adjacent markers.
  return content.replace(/\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]/g, (match, group: string) => {
    const nums = group.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => Number.isFinite(n) && n >= 1 && n <= citationsLen);
    if (nums.length === 0) return match;
    return nums.map((n) => `[[${n}]](#cite-${n})`).join('');
  });
};

/**
 * Allowlist for markdown-rendered URLs. react-markdown v10 forwards raw hrefs
 * unless urlTransform is set; model-generated content must never open
 * javascript:/data: links, so every scheme outside the allowlist is dropped.
 */
export const safeUrlTransform = (url: string): string =>
  /^(https?:|mailto:|#)/i.test(url) ? url : '';


/**
 * True when a guru answer is a crisis/helpline response. Such answers must never
 * carry the "Did this help? 👍/👎" engagement card or the "explain simply" inline
 * actions — a thumbs-down widget under a suicide helpline is unsafe. The backend
 * crisis path (services/crisis_helplines.format_helplines_block) always emits the
 * 🆘 intro; we also match a bare helpline heading defensively.
 */
const isCrisisAnswer = (content: string): boolean =>
  /🆘/.test(content) || /immediate crisis|crisis, please reach out|helpline/i.test(content);

const GuidancePlanCard = ({ plan }: { plan: NonNullable<Message["guidancePlan"]> }) => (
  <aside
    data-testid="guidance-plan"
    aria-label="Optional guidance plan"
    className="w-full rounded-xl border border-ojas/20 bg-gradient-to-br from-ojas/10 to-card px-3.5 py-3 shadow-sm"
  >
    <div className="flex items-start gap-2">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {plan.action_step && (
          <>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">Try this now</p>
            <p className="mt-1 text-sm font-medium leading-5 text-foreground">{plan.action_step.title}</p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{plan.action_step.instruction}</p>
            {plan.action_step.safety_note && (
              <p className="mt-2 text-xs leading-4 text-muted-foreground">{plan.action_step.safety_note}</p>
            )}
          </>
        )}
        {plan.reflection_prompt && (
          <div className={plan.action_step ? "mt-3 border-t border-ojas/15 pt-2.5" : ""}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">Go deeper</p>
            <p className="mt-1 text-sm leading-5 text-foreground/85">{plan.reflection_prompt}</p>
          </div>
        )}
      </div>
    </div>
  </aside>
);

const SereneMindOfferCard = ({ offer }: { offer: NonNullable<Message["sereneMindOffer"]> }) => {
  const { open } = useSereneMind();
  const customMeditation = offer.custom_meditation;
  const durationSeconds = offer.duration_seconds ?? 225;
  const durationLabel = durationSeconds >= 60
    ? `${Math.round(durationSeconds / 60)} min`
    : `${durationSeconds} sec`;

  return (
    <aside
      data-testid="serene-mind-offer"
      aria-label="Optional Serene Mind practice"
      role="status"
      aria-live="polite"
      className="mt-3 w-full rounded-xl border border-ojas/25 bg-gradient-to-br from-ojas/10 to-card px-3.5 py-3 shadow-sm"
    >
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">Optional practice</p>
          <p className="mt-1 text-sm font-medium leading-5 text-foreground">
            {offer.offer_reason || "A brief practice may help you settle and reconnect."}
          </p>
          <p className="mt-1 text-xs leading-4 text-muted-foreground">
            {durationLabel} · The teaching comes first; start only if it feels right.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => open('audio', false, customMeditation?.steps, customMeditation?.source_teaching)}
              className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light px-3 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition-transform hover:scale-[1.02]"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              Start Serene Mind
            </button>
            <span className="self-center text-[11px] text-muted-foreground">You can continue chatting instead.</span>
          </div>
        </div>
      </div>
    </aside>
  );
};

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

/** Extract a valid 11-character YouTube video ID from a source URL. */
const getYouTubeId = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    let candidate: string | null = null;
    if (hostname === 'youtu.be') {
      candidate = parsed.pathname.split('/').filter(Boolean)[0] ?? null;
    } else if (hostname === 'youtube.com') {
      if (parsed.pathname === '/watch') candidate = parsed.searchParams.get('v');
      if (parsed.pathname.startsWith('/embed/')) candidate = parsed.pathname.split('/')[2] ?? null;
      if (parsed.pathname.startsWith('/shorts/')) candidate = parsed.pathname.split('/')[2] ?? null;
    }
    return candidate && /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : null;
  } catch {
    return null;
  }
};

/** Check if a URL is a usable HTTP(S) source. */
const isUsableSourceUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    if (!parsed.hostname) return false;
    const hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    if (hostname === 'youtube.com' || hostname === 'youtu.be') {
      return getYouTubeId(url) !== null;
    }
    return true;
  } catch {
    return false;
  }
};

/** Check if a URL is a valid YouTube source. */
const isYouTubeUrl = (url: string): boolean => getYouTubeId(url) !== null;

/** Lazy YouTube embed: thumbnail → click → iframe */
interface YTPlayerReadyEvent {
  target: {
    addEventListener: (event: string, listener: (e: { data: number }) => void) => void;
  };
}

declare global {
  interface Window {
    YT?: {
      Player: new (
        elementId: string,
        options: {
          videoId: string;
          playerVars?: Record<string, number | string>;
          events?: { onReady?: (event: YTPlayerReadyEvent) => void; onError?: (event: { data: number }) => void };
        }
      ) => { destroy: () => void };
      PlayerState?: { ENDED: number; PLAYING: number };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

const LazyYouTube = ({ videoId, url }: { videoId: string; url: string }) => {
  const [loaded, setLoaded] = useState(false);
  const [embedError, setEmbedError] = useState(false);
  const playerRef = useRef<{ destroy: () => void } | null>(null);
  const thumbnail = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

  useEffect(() => {
    if (!loaded) return;

    // Lightweight postMessage listener for embed errors when YT API isn't loaded.
    const handleMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.youtube.com') return;
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (data?.event === 'onError' || data?.event === 'onStateChange') {
          const code = data?.info ?? data?.data;
          if (code === 101 || code === 150) {
            setEmbedError(true);
          }
        }
      } catch {
        // ignore non-JSON postMessages
      }
    };
    window.addEventListener('message', handleMessage);

    // If the API script is already present, register a real player to listen for errors.
    // Use an off-screen probe element so the visible iframe is the only DOM node.
    let probeContainer: HTMLDivElement | null = null;
    if (window.YT?.Player) {
      const containerId = `yt-probe-${videoId}-${Math.random().toString(36).slice(2, 8)}`;
      probeContainer = document.createElement('div');
      probeContainer.id = containerId;
      probeContainer.style.cssText = 'position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;';
      document.body.appendChild(probeContainer);
      playerRef.current = new window.YT.Player(containerId, {
        videoId,
        playerVars: { autoplay: 1, enablejsapi: 1, origin: window.location.origin },
        events: {
          onReady: (event) => {
            event.target.addEventListener('onError', (e) => {
              if (e.data === 101 || e.data === 150) {
                setEmbedError(true);
              }
            });
          },
          onError: (event) => {
            if (event.data === 101 || event.data === 150) {
              setEmbedError(true);
            }
          },
        },
      });
    }

    return () => {
      window.removeEventListener('message', handleMessage);
      try {
        playerRef.current?.destroy();
      } catch {
        // ignore cleanup errors
      }
      playerRef.current = null;
      if (probeContainer) {
        probeContainer.remove();
      }
    };
  }, [loaded, videoId]);

  if (loaded && !embedError) {
    return (
      <div className="relative group rounded-xl overflow-hidden shadow-md border border-border/30 bg-black/5 aspect-video w-full max-w-[320px]">
        <div id="yt-player-root" className="absolute inset-0">
          <iframe
            width="100%"
            height="100%"
            src={`https://www.youtube.com/embed/${videoId}?autoplay=1&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}`}
            title="YouTube video player"
            frameBorder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-[10px] text-white/90 bg-black/70 px-2 py-1 rounded flex items-center gap-1 shadow-md hover:bg-black/90 z-10"
        >
          Watch on YouTube ↗
        </a>
      </div>
    );
  }

  if (loaded && embedError) {
    // Embed blocked - show fallback with direct link
    return (
      <div className="rounded-xl overflow-hidden shadow-md border border-border/30 bg-ojas/5 aspect-video w-full max-w-[320px] relative group">
        <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center bg-gradient-to-br from-ojas/10 to-ojas/5">
          <div className="w-16 h-16 rounded-full bg-red-500/20 flex items-center justify-center mb-3">
            <Youtube className="w-8 h-8 text-red-500" />
          </div>
          <p className="text-sm font-medium text-ojas mb-1">Video unavailable</p>
          <p className="text-xs text-muted-foreground mb-3">This video can't be embedded</p>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-ojas text-white text-xs font-medium rounded-full hover:bg-ojas-light transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            Watch on YouTube
          </a>
        </div>
        <div className="absolute bottom-2 right-2">
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-white/90 bg-black/60 px-1.5 py-0.5 rounded"
          >
            YouTube
          </a>
        </div>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl overflow-hidden shadow-md border border-border/30 bg-black/5 aspect-video w-full max-w-[320px] relative cursor-pointer group"
      onClick={() => setLoaded(true)}
      role="button"
      aria-label="Play YouTube video"
    >
      <img
        src={thumbnail}
        alt="YouTube thumbnail"
        className="w-full h-full object-cover"
        loading="lazy"
      />
      <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/30 transition-colors">
        <div className="w-12 h-12 rounded-full bg-background/90 flex items-center justify-center shadow-lg">
          <Play className="w-5 h-5 text-red-600 fill-red-600 ml-0.5" />
        </div>
      </div>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="absolute bottom-2 right-2 text-[10px] text-white/90 bg-black/60 px-1.5 py-0.5 rounded"
        onClick={(e) => e.stopPropagation()}
      >
        YouTube
      </a>
    </div>
  );
};

/** Get a display name for a citation: the real title when known, else a
 *  domain-derived label (e.g., 'Video Source A') synthesized from the URL. */
const getSourceDisplayName = (citation: Citation, index: number): string => {
  if (citation.title) return citation.title;
  const url = citation.url;
  try {
    const urlObj = new URL(url);
    const hostname = urlObj.hostname.replace(/^www\./, '');
    if (hostname.includes('youtube') || hostname.includes('youtu.be')) {
      return `Video Source ${String.fromCharCode(65 + index)}`;
    }
    if (hostname.includes('academy') || hostname.includes('ekam')) {
      return `O&O Academy Reference`;
    }
    if (hostname.includes('preethaji') || hostname.includes('krishnaji')) {
      return 'Teaching Reference';
    }
    return hostname;
  } catch {
    return `Source ${index + 1}`;
  }
};


/**
 * Wisdom Card generator is a big, rarely-opened modal — it ships in its own
 * chunk and loads only when the share button is clicked, keeping it off the
 * chat hot path (P1-AI-16). lazyWithRetry reloads once if a deploy invalidated
 * the chunk URL mid-session. The module exports a named component, so adapt
 * it to the `{ default }` shape lazyWithRetry expects. Shared by ChatInterface
 * (Quick Wisdom Card) so the generator stays in exactly one lazy chunk.
 */
export const LazyWisdomCardGenerator = lazyWithRetry<
  React.ComponentType<{ isOpen: boolean; onClose: () => void; content: string }>
>(async () => {
  const mod = await import('./WisdomCardGenerator');
  return { default: mod.WisdomCardGenerator };
});


const ChatMessageInner = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, queryText, index = 0, isStreaming = false, isLastGuru = false, onRegenerate, onEditUserMessage, onSubmitEdit, onAction, onCitationClick }, ref) => {
    const { t } = useTranslation();
    const isGuru = message.role === 'guru';
    const navigate = useNavigate();
    const { profile } = useProfile();
    const { open: openSereneMind } = useSereneMind();
    // Extract any https:// URL from the guru's response as a fallback citation.
    // Covers: YouTube links, source references like "Source: https://...", inline citations.
    // No title is available for these — the panel falls back to the domain.
    const inlineCitations: Citation[] = isGuru
      ? Array.from(new Set(
        (message.content.match(/https?:\/\/[^\s)"'<>]+/g) ?? [])
          .filter(isUsableSourceUrl)
      )).map((url) => ({ url }))
      : [];
    const citations: Citation[] = (message.citations && message.citations.length > 0)
      ? message.citations.filter((c) => isUsableSourceUrl(c.url))
      : inlineCitations;
    const groundingState = message.groundingState ?? 'abstained';

    // Attribution integrity: a quoted teacher statement with no linked source
    // must be labelled unverified rather than rendered as doctrine (QA P1).
    // Exempt safety_redirect (distress/crisis preemption): those are hardcoded
    // compassionate templates, not RAG-retrieved doctrine, so they're never
    // citable — but they still legitimately quote a teacher for comfort, and
    // replacing them silently drops the crisis helpline text they carry.
    const hasUnverifiedAttribution = useMemo(() => {
      if (!isGuru || citations.length > 0 || groundingState === 'safety_redirect') return false;
      return /(?:Sri\s+(?:Preethaji|Krishnaji)|Preethaji|Krishnaji)[^.\n]{0,60}["“'']/.test(message.content);
    }, [isGuru, citations.length, groundingState, message.content]);

    const displayContent = useMemo(() => {
      if (!isGuru || citations.length > 0 || !hasUnverifiedAttribution) return message.content;
      return 'I could not verify the quoted teaching against a linked source, so I am not presenting it as a teacher attribution. Please retry to request a grounded answer.';
    }, [citations.length, hasUnverifiedAttribution, isGuru, message.content]);

    const [showWisdomCard, setShowWisdomCard] = useState(false);
    const [copied, setCopied] = useState(false);
    const [saved, setSaved] = useState(false);
    const [savingMemory, setSavingMemory] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(message.content);
    const [noteSaved, setNoteSaved] = useState(false);
    const [sourcesOpen, setSourcesOpen] = useState(false);
    const [provenanceOpen, setProvenanceOpen] = useState(false);
    const [activeVideoCitation, setActiveVideoCitation] = useState<DiscourseCitation | null>(null);
    const [activeSearchCitation, setActiveSearchCitation] = useState<DiscourseCitation | null>(null);
    const editTextareaRef = useRef<HTMLTextAreaElement>(null);

    // Auto-resize + cursor-end when editing opens or text changes
    useEffect(() => {
      const el = editTextareaRef.current;
      if (!el || !isEditing) return;
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
    }, [editValue, isEditing]);

    // Place cursor at end only once when edit mode opens
    useEffect(() => {
      if (!isEditing) return;
      const el = editTextareaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }, [isEditing]);
    const { toast } = useToast();
    const { createNote } = useNotes();
    const { notebooks, createNotebook, addItem } = useStudyNotebooks();

    const handleSaveAsNote = useCallback(async () => {
      const snippet = (queryText ? `**Question:** ${queryText}\n\n**Teaching:**\n` : '') + message.content;
      // Prefer study notebooks; fall back to legacy notes table
      try {
        let target: typeof notebooks[number] | undefined = notebooks[0];
        if (!target) {
          target = (await createNotebook(t('chat.savedFromChat'))) ?? undefined;
        }
        if (target) {
          await addItem(target.id, {
            query: queryText || 'Teaching',
            answer: message.content,
            source_episode_id: null,
          });
          setNoteSaved(true);
          setTimeout(() => setNoteSaved(false), 2000);
          toast({ title: 'Saved to Study Notebook', description: `Added to "${target.title}"` });
          return;
        }
      } catch {
        // fall through to legacy notes
      }
      const note = await createNote({
        title: queryText ? queryText.slice(0, 80) : t('chat.teaching'),
        body: snippet,
        tags: ['from-chat'],
        source_message_id: message.id,
      });
      if (note) {
        setNoteSaved(true);
        setTimeout(() => setNoteSaved(false), 2000);
        toast({ title: t('chat.savedToNotes'), description: t('chat.savedToNotesDescription') });
      } else {
        toast({ title: t('chat.signInSaveNotes'), variant: 'destructive' });
      }
    }, [createNote, createNotebook, addItem, notebooks, message.content, message.id, queryText, toast, t]);

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      } catch { /* ignore */ }
    }, [message.content]);

    // Per-message read-aloud. speak() cancels any other message's speech, so
    // one utterance plays at a time across the conversation.
    const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported, currentSentence } = useTextToSpeech();
    const plainText = useMemo(() =>
      message.content
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, ' ')
        .replace(/[#*_>`]/g, '')
        .replace(/\s+/g, ' ')
        .trim(),
      [message.content]);
    const sentences = useMemo(() => {
      if (!plainText) return [];
      return plainText.split(/(?<=[.!?।?\n])\s+/).map((s) => s.trim()).filter(Boolean);
    }, [plainText]);
    const handleSpeak = useCallback(() => {
      if (isSpeaking) {
        stopSpeaking();
        return;
      }
      if (plainText) speak(plainText);
    }, [isSpeaking, stopSpeaking, speak, plainText]);

    const renderHighlightedText = () => {
      if (sentences.length === 0 || !currentSentence) {
        return <span>{plainText}</span>;
      }
      return (
        <span>
          {sentences.map((sentence, i) => (
            <span
              key={i}
              className={sentence === currentSentence ? 'bg-ojas/20 rounded px-0.5 transition-colors' : ''}
            >
              {sentence}
              {i < sentences.length - 1 ? ' ' : ''}
            </span>
          ))}
        </span>
      );
    };

    const handleSaveToMemory = useCallback(async () => {
      if (saved || savingMemory) return;
      setSavingMemory(true);
      try {
        // Use the user's question + a short slice of the answer as the saved fact.
        const snippet = (queryText ? `Q: ${queryText}\nA: ` : '') + message.content.slice(0, 600);
        await memoryApi.add(snippet);
        setSaved(true);
        toast({ title: t('chat.savedToMemory'), description: t('chat.guruWillRecall') });
      } catch (e) {
        const err = e as { code?: string; message?: string };
        if (err?.code === 'unauthorized') {
          toast({ title: 'Sign in to save memories', description: 'Memory is available to signed-in seekers.', variant: 'destructive' });
        } else {
          toast({ title: 'Could not save', description: err?.message ?? 'Please try again.', variant: 'destructive' });
        }
      } finally {
        setSavingMemory(false);
      }
    }, [saved, savingMemory, queryText, message.content, toast, t]);

    return (
      <>
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.15) }}
          className={`group message-bubble flex items-start gap-2 ${isGuru ? 'justify-start' : 'justify-end'}`}
          data-message-id={message.id}
        >
          {isGuru && (
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-ojas/15 to-ojas/5 border border-hairline flex items-center justify-center flex-shrink-0 mt-0.5">
              <Sparkles className="w-3.5 h-3.5 text-ojas" />
            </div>
          )}
          {/* The guru answer is long-form prose — it gets the full reading column
              (the parent is already capped at max-w-3xl), the way Claude/ChatGPT
              lay out assistant turns. Capping it at 75% made every answer a
              narrow ragged strip. The user's own turn stays a right-aligned bubble. */}
          <div className={`${isEditing ? 'w-full max-w-[95%] sm:max-w-[85%]' : isGuru ? 'flex-1 min-w-0 w-full' : 'max-w-[85%] sm:max-w-[75%]'} flex flex-col gap-1 ${isGuru ? 'items-start' : 'items-end'}`}>
            {/* Message body */}
            <div
className={`relative ${isGuru ? 'w-full' : 'w-fit'} transition-all duration-200 ${isGuru
                    ? 'rounded-2xl rounded-tl-sm px-0 py-1 sm:py-1.5 text-[15px] leading-[1.75] text-foreground font-normal'
                    : isEditing
                      ? 'bg-card border border-hairline rounded-2xl p-3 sm:p-4 shadow-sm'
                      : 'bg-chat-user rounded-2xl p-3 sm:p-4 text-[15px] leading-[1.55] font-normal shadow-sm'
                }`}
            >
              <div
                className={`break-words ${isGuru ? '' : 'whitespace-pre-wrap'}`}
              >
                {isGuru ? (
                  message.error ? (
                    <div
                      role="alert"
                      aria-live="assertive"
                      className="not-prose rounded-xl border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-foreground/90"
                    >
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="w-4 h-4 mt-0.5 text-destructive shrink-0" aria-hidden />
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-semibold text-destructive leading-tight">{message.error.title}</p>
                          <p className="text-[12.5px] text-foreground/75 mt-1 leading-relaxed">{message.error.description}</p>
                          {message.error.detail && (
                            <details className="mt-1.5">
                              <summary className="text-[11px] text-muted-foreground cursor-pointer hover:text-foreground/70 select-none">
                                Technical detail
                              </summary>
                              <pre className="mt-1 text-[11px] text-muted-foreground whitespace-pre-wrap break-all font-mono bg-background/40 rounded px-2 py-1.5 border border-border/40">
                                {message.error.detail}
                              </pre>
                            </details>
                          )}
                          <div className="flex flex-wrap gap-2 mt-2.5">
                            {(message.error.actionLabel === 'retry' || !message.error.actionLabel) && onRegenerate && (
                              <button
                                type="button"
                                onClick={onRegenerate}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <RefreshCw className="w-3 h-3" aria-hidden />
                                Retry
                              </button>
                            )}
                            {message.error.actionLabel === 'sign_in' && (
                              <button
                                type="button"
                                onClick={() => navigate('/auth')}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <LogIn className="w-3 h-3" aria-hidden />
                                Sign in again
                              </button>
                            )}
                            {message.error.actionLabel === 'reload' && (
                              <button
                                type="button"
                                onClick={() => window.location.reload()}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <RefreshCw className="w-3 h-3" aria-hidden />
                                Reload
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="text-[15px] leading-[1.75] text-foreground selection:bg-ojas/20">
                      {/* While streaming with no content, render nothing — the single
                        ThinkingPills indicator in ChatInterface is the source of truth.
                        This prevents two simultaneous "thinking" indicators. */}
                      {isStreaming && !message.content ? null : (
                        <ReactMarkdown
                          // GFM: tables, strikethrough, task lists, autolinks. Without it the
                          // model's markdown tables rendered as raw pipe soup.
                          remarkPlugins={[remarkGfm]}
                          urlTransform={safeUrlTransform}
                          components={{
                            // Reading rhythm: a full blank line between paragraphs, the way
                            // ChatGPT/Claude set long-form answers. `mb-1.5` ran them together.
                            p: ({ children }) => (
                              <p className="mb-4 last:mb-0">{children}</p>
                            ),
                            // Headings — sized in `em` so they scale with the message body
                            // instead of colliding with it at a fixed 14–16px.
                            h1: ({ children }) => (
                              <h1 className="text-[1.35em] font-semibold text-foreground leading-snug mt-7 mb-3 first:mt-0">{children}</h1>
                            ),
                            h2: ({ children }) => (
                              <h2 className="text-[1.15em] font-semibold text-foreground leading-snug mt-6 mb-2.5 first:mt-0">{children}</h2>
                            ),
                            h3: ({ children }) => (
                              <h3 className="text-[1.02em] font-semibold text-foreground leading-snug mt-5 mb-2 first:mt-0">{children}</h3>
                            ),
                            h4: ({ children }) => (
                              <h4 className="text-[0.95em] font-semibold text-muted-foreground uppercase tracking-wide mt-5 mb-1.5 first:mt-0">{children}</h4>
                            ),
                            // Native list markers, not a hand-rolled flex marker in `li`:
                            // react-markdown v9 stopped passing `ordered` to `li`, so the old
                            // code rendered every numbered list as bullets. The browser knows
                            // whether it's in a ul or an ol — let it. Nesting works for free.
                            ul: ({ children }) => (
                              <ul className="my-4 space-y-2 pl-5 list-disc marker:text-ojas/70">{children}</ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="my-4 space-y-2 pl-5 list-decimal marker:text-ojas marker:font-semibold marker:tabular-nums">{children}</ol>
                            ),
                            li: ({ children }) => (
                              <li className="leading-[1.7] pl-1">{children}</li>
                            ),
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-[3px] border-ojas/50 pl-4 pr-3 py-2 my-4 bg-ojas/5 rounded-r-lg italic text-foreground/80">
                                {children}
                              </blockquote>
                            ),
                            // `pre` owns the scroll container + chrome; `code` inside it stays
                            // unstyled. Previously there was no `pre` override, so a fenced
                            // block got bubble-breaking horizontal overflow instead of its
                            // own scrollbar.
                            pre: ({ children }) => (
                              <pre className="my-4 overflow-x-auto rounded-xl bg-muted/60 border border-border/40 p-4 text-[13px] leading-[1.6] font-mono">
                                {children}
                              </pre>
                            ),
                            code: ({ children, className }) => {
                              const isBlock = !!className;
                              if (isBlock) {
                                return <code className={`font-mono ${className ?? ''}`}>{children}</code>;
                              }
                              return (
                                <code className="bg-ojas/10 text-ojas px-1.5 py-0.5 rounded text-[0.875em] font-mono border border-ojas/15">
                                  {children}
                                </code>
                              );
                            },
                            // GFM tables — the wrapper scrolls so a wide table can't stretch
                            // the message column.
                            table: ({ children }) => (
                              <div className="my-4 overflow-x-auto rounded-xl border border-border/40">
                                <table className="w-full text-[0.93em] border-collapse">{children}</table>
                              </div>
                            ),
                            thead: ({ children }) => <thead className="bg-muted/50">{children}</thead>,
                            th: ({ children }) => (
                              <th className="text-left font-semibold px-3 py-2 border-b border-border/40 whitespace-nowrap">{children}</th>
                            ),
                            td: ({ children }) => (
                              <td className="px-3 py-2 border-b border-border/25 align-top last:border-b-0">{children}</td>
                            ),
                            strong: ({ children }) => (
                              <strong className="font-semibold text-foreground">{children}</strong>
                            ),
                            em: ({ children }) => <em className="italic text-foreground/90">{children}</em>,
                            hr: () => (
                              <hr className="border-0 border-t border-border/40 my-6" />
                            ),
                            // Links + citation buttons
                            a: ({ href, children, ...rest }) => {
                              const match = typeof href === 'string' ? href.match(/^#cite-(\d+)$/) : null;
                              if (match) {
                                const n = parseInt(match[1], 10);
                                const citationData = (message.citations ?? [])[n - 1];
                                const discourseCitation: DiscourseCitation = {
                                  index: n,
                                  url: citationData?.url || '#',
                                  title: citationData?.title || citationData?.source || 'Sacred Discourse Teaching',
                                  speaker: 'Ekams Wisdom',
                                  startTimestamp: citationData?.timestampSeconds,
                                  quote: citationData?.textSnippet || citationData?.quote,
                                };
                                return (
                                  <CitationBadge
                                    citation={discourseCitation}
                                    onOpenVideoModal={(c) => {
                                      setActiveVideoCitation(c);
                                      onCitationClick?.(message.id, n - 1);
                                    }}
                                    onOpenSearchModal={(c) => {
                                      setActiveSearchCitation(c);
                                      onCitationClick?.(message.id, n - 1);
                                    }}
                                  />
                                );
                              }
                              return (
                                <a href={href} {...rest} target="_blank" rel="noopener noreferrer" className="text-ojas underline-offset-2 hover:underline">
                                  {children}
                                </a>
                              );
                            },
                          }}
                        >
                          {injectCitationLinks(displayContent, (message.citations ?? []).length)}
                        </ReactMarkdown>
                      )}
                    </div>
                  )
                ) : isEditing ? (
                  <div className="flex flex-col gap-2.5 w-full">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-ojas animate-pulse" />
                      <p className="text-[11px] text-ojas/70 font-medium">
                        Editing — earlier replies will be regenerated
                      </p>
                    </div>
                    <textarea
                      ref={editTextareaRef}
                      value={editValue}
                      onChange={(e) => {
                        setEditValue(e.target.value);
                        // immediate height sync on change
                        const el = e.currentTarget;
                        el.style.height = 'auto';
                        el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
                      }}
                      rows={2}
                      className="w-full bg-background/80 border border-ojas/30 rounded-xl p-3 text-[14px] text-foreground placeholder:text-muted-foreground outline-none focus:border-ojas/60 focus:ring-2 focus:ring-ojas/15 resize-none leading-relaxed overflow-y-auto"
                      style={{ minHeight: '64px', maxHeight: '260px' }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          if (editValue.trim() && editValue.trim() !== message.content) {
                            onSubmitEdit?.(message.id, editValue.trim());
                          }
                          setIsEditing(false);
                        }
                        if (e.key === 'Escape') {
                          setEditValue(message.content);
                          setIsEditing(false);
                        }
                      }}
                    />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] text-muted-foreground/60">
                        ⌘↵ save · Esc cancel
                      </span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => { setEditValue(message.content); setIsEditing(false); }}
                          className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-muted-foreground hover:bg-muted/70 transition-colors"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const trimmed = editValue.trim();
                            if (trimmed && trimmed !== message.content) {
                              onSubmitEdit?.(message.id, trimmed);
                            }
                            setIsEditing(false);
                          }}
                          disabled={!editValue.trim() || editValue.trim() === message.content}
                          className="px-3 py-1.5 rounded-lg text-[12px] font-semibold bg-ojas text-primary-foreground hover:bg-ojas-light disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
                        >
                          Save &amp; resend
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <span className="font-medium">{message.content}</span>
                )}
                {isGuru && isSpeaking && plainText && (
                  <span className="block mt-2 text-foreground/80" aria-live="polite">
                    {renderHighlightedText()}
                  </span>
                )}
                {isStreaming && (
                  <span className="inline-flex items-center gap-1 ml-0.5 align-text-bottom">
                    {/* Serene UI: warm-sand breathing ring around the cursor.
                        Uses tailwind animate-breathe + animate-pulse-soft keyframes
                        registered in tailwind.config.ts (serene namespace). */}
                    <span
                      className="inline-block w-2 h-2 rounded-full bg-ojas/30 animate-breathe"
                      aria-hidden
                    />
                    <motion.span
                      animate={{ opacity: [1, 0] }}
                      transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
                      className="inline-block w-[2px] h-[1em] bg-ojas"
                    />
                  </span>
                )}
              </div>

              {/* Inline action buttons for the latest guru message only.
                  Suppressed on crisis/helpline answers (see isCrisisAnswer). */}
              {isGuru && isLastGuru && message.content && !isStreaming && onAction && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && (
                <InlineActions messageContent={message.content} onAction={onAction} />
              )}

              {/* Engagement card: "Did this help?" — shown for the last guru answer.
                  Never shown on crisis/helpline answers — a feedback widget under a
                  helpline is unsafe (see isCrisisAnswer). */}
              {isGuru && isLastGuru && message.content && !isStreaming && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && (
                <EngagementCard
                  messageId={message.id}
                  messageContent={message.content}
                  queryText={queryText}
                  qualityMetadata={{
                    message_id: message.id,
                    trace_id: message.traceId,
                    latency_ms: message.latencyMs,
                    model_used: message.modelUsed,
                    model_provider: message.modelProvider,
                    query_tier: message.queryTier,
                    faithfulness_score: message.faithfulnessScore,
                    relevancy_score: message.relevancyScore,
                    hallucination_flag: message.hallucinationFlag,
                    verification: message.verification,
                    citations_verified: message.citationsVerified,
                    citation_count: message.citations?.length ?? 0,
                    answer_length_chars: message.content.length,
                    answer_length_words: message.content.trim() ? message.content.trim().split(/\s+/).length : 0,
                    grounding_state: message.groundingState,
                    route_decision: message.queryTier,
                  }}
                />
              )}

              {/* Practice nudge: offer to turn the last answer into a guided Serene
                  Mind session. Suppressed on crisis/helpline answers like the rest
                  of this footer. */}
              {isGuru && isLastGuru && message.content && !isStreaming && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && (
                <div
                  className="mt-2 flex items-center gap-2 text-[12px]"
                  title={t('chat.practiceNudge.body')}
                >
                  <span className="text-muted-foreground">{t('chat.practiceNudge.title')}</span>
                  <button
                    onClick={() => openSereneMind('audio', true)}
                    className="flex-shrink-0 rounded-full border border-ojas/30 px-2.5 py-1 text-[11px] font-medium text-ojas hover:bg-ojas/10 transition-colors whitespace-nowrap"
                  >
                    {t('chat.practiceNudge.cta')}
                  </button>
                </div>
              )}

              {/* Hover-only timestamp */}
              <time className="opacity-0 group-hover:opacity-60 text-[11px] text-muted-foreground transition-opacity mt-1 block">
                {formatTime(message.timestamp)}
              </time>

              {/* Guru hover actions */}
              {isGuru && message.content && !isStreaming && !message.content.includes('_Stopped by you._') && (
                <div className="flex items-center gap-0.5 mt-2 opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 max-md:opacity-100 transition-opacity duration-200">
                  {isLastGuru && onRegenerate && (
                    <button
                      onClick={onRegenerate}
                      className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                      title={t('chat.regenerate')}
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={handleCopy}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={copied ? t('common.copied') : t('chat.copyResponse')}
                  >
                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </button>
                  {ttsSupported && (
                    <button
                      onClick={handleSpeak}
                      aria-pressed={isSpeaking}
                      className={`p-1 rounded-full transition-colors ${isSpeaking
                          ? 'bg-ojas/15 text-ojas'
                          : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                        }`}
                      title={isSpeaking ? t('chat.stopReading') : t('chat.readAloud')}
                    >
                      {isSpeaking ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                    </button>
                  )}
                  <button
                    onClick={handleSaveToMemory}
                    disabled={saved || savingMemory}
                    className={`p-1 rounded-full transition-colors ${saved
                        ? 'bg-prana/15 text-prana'
                        : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                      } ${savingMemory ? 'opacity-60' : ''}`}
                    title={saved ? t('chat.savedToMemory') : t('chat.saveToMemory')}
                  >
                    <Bookmark className={`w-4 h-4 ${saved ? 'fill-current' : ''}`} />
                  </button>
                  <button
                    onClick={handleSaveAsNote}
                    className={`p-1 rounded-full transition-colors ${noteSaved
                        ? 'bg-prana/15 text-prana'
                        : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                      }`}
                    title={noteSaved ? t('chat.savedToNotes') : t('chat.saveAsNote')}
                  >
                    <StickyNote className={`w-4 h-4 ${noteSaved ? 'fill-current' : ''}`} />
                  </button>
                  <button
                    onClick={() => setShowWisdomCard(true)}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={t('chat.shareWisdomCard')}
                  >
                    <Share2 className="w-4 h-4" />
                  </button>
                  <LanguageTranslateButton message={message} />
                </div>
              )}

            </div>

            {/* EU AI Act Article 50 Disclosure & Provenance Badge */}
            {isGuru && !message.error && (message.content || !isStreaming) && (
              <div className="mt-2 select-none flex items-center gap-2">
                <EuAiBadge
                  originType="ai_generated"
                  onClick={() => setProvenanceOpen(true)}
                  size="sm"
                />
              </div>
            )}

            {/* User hover actions */}
            {!isGuru && message.content && !isStreaming && !isEditing && (
              <div className="flex items-center justify-end gap-0.5 opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 max-md:opacity-100 transition-opacity duration-200 mt-1 mr-1">
                <button
                  onClick={handleCopy}
                  className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                  title={copied ? t('common.copied') : t('chat.copyQuestion')}
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </button>
                {(onSubmitEdit || onEditUserMessage) && (
                  <button
                    onClick={() => {
                      if (onSubmitEdit) {
                        setEditValue(message.content);
                        setIsEditing(true);
                      } else if (onEditUserMessage) {
                        onEditUserMessage(message);
                      }
                    }}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={t('chat.editResend')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                )}
              </div>
            )}

            {/* Memory provenance — surfaces facts the Guru recalled from your reflections */}
            {isGuru && message.memoriesUsed && message.memoriesUsed.length > 0 && (
              <details className="w-full rounded-lg border border-ojas/15 bg-ojas/5 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-medium text-ojas/80 select-none">
                  {t('chat.recalledFromReflections', { count: message.memoriesUsed.length })}
                </summary>
                <ul className="mt-2 space-y-1 list-disc pl-4 text-muted-foreground">
                  {message.memoriesUsed.slice(0, 6).map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Follow-up suggestions as clickable chips */}
            {FEATURE_FLAGS.suggestedFollowUps && isGuru && message.followUpSuggestions && message.followUpSuggestions.length > 0 && !isStreaming && onAction && !message.content.includes('_Stopped by you._') && (
              <div className="w-full mt-1">
                <p className="text-[10px] text-muted-foreground/60 mb-2 pl-0.5">{t('chat.suggestedFollowUps')}</p>
                <div className="flex flex-wrap gap-1.5">
                  {message.followUpSuggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => onAction(suggestion)}
                      className="text-[11px] px-2.5 py-1 rounded-full border border-ojas/20 bg-ojas/5 hover:bg-ojas/10 hover:border-ojas/40 text-foreground/80 hover:text-foreground transition-all"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Sources / Citations status. When there ARE citations, this merges into
                the REFERENCES <details> summary below instead of rendering here —
                same "grounded, N sources" fact was showing twice in two stacked
                boxes. Zero-citation states (reflective guidance, safety redirect,
                unverified attribution, system error) have nothing to expand into,
                so they keep their own standalone row. */}
            {FEATURE_FLAGS.responseProvenance && isGuru && !isStreaming && citations.length === 0 && (message.content || typeof message.confidenceScore === 'number' || hasUnverifiedAttribution) && (
              <div
                data-testid="response-provenance"
                role="status"
                className={cn(
                  'w-full flex items-center gap-2.5 rounded-xl border px-3 py-2 text-xs text-muted-foreground',
                  groundingState === 'grounded'
                    ? 'border-ojas/15 bg-ojas/[0.045]'
                    : 'border-amber-500/40 bg-amber-500/[0.07]',
                )}
              >
                <Shield
                  className={cn('h-3.5 w-3.5 shrink-0', groundingState === 'grounded' ? 'text-ojas' : 'text-amber-500')}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1 leading-tight">
                  <p className="font-medium text-foreground/80">
                    {groundingState === 'safety_redirect'
                      ? 'Safety support'
                      : groundingState === 'system_error'
                        ? 'Verification unavailable'
                        : hasUnverifiedAttribution
                          ? 'Unverified attribution'
                          : 'Reflective guidance'}
                  </p>
                  <p>
                    {groundingState === 'safety_redirect'
                      ? 'Safety guidance is shown instead of doctrine attribution.'
                      : groundingState === 'system_error'
                        ? 'The response could not be verified. Please retry before relying on it.'
                        : hasUnverifiedAttribution
                          ? 'This answer quotes a teacher without a linked source — treat the wording as paraphrase, not a verified quotation.'
                          : 'No grounded teaching was found for this response; treat it as reflective guidance.'}
                  </p>
                </div>
                {typeof message.confidenceScore === 'number' && Number.isFinite(message.confidenceScore) && (
                  <span
                    className="shrink-0 rounded-full bg-card px-2 py-1 font-medium text-foreground/80"
                    title={message.confidenceReason || evidenceSupport(message.confidenceScore).description}
                    aria-label={`Response support: ${evidenceSupport(message.confidenceScore).label}`}
                  >
                    {evidenceSupport(message.confidenceScore).label}
                  </span>
                )}
              </div>
            )}
            {isGuru && !isStreaming && <LiveLogisticsCards events={message.liveLogisticsEvents} />}
            {/* Attribution-only guidance ("Guidance inspired by retrieved teachings")
                already duplicates the response-provenance grounding badge below —
                only render this card when it carries actionable content. */}
            {isGuru && !isStreaming && message.guidancePlan
              && (message.guidancePlan.action_step || message.guidancePlan.reflection_prompt)
              && !isCrisisAnswer(message.content) && (
              <GuidancePlanCard plan={message.guidancePlan} />
            )}
            {isGuru && !isStreaming && message.sereneMindOffer?.triggered && !isCrisisAnswer(message.content) && (
              <SereneMindOfferCard offer={message.sereneMindOffer} />
            )}
            {isGuru && citations.length > 0 && (
              <details className="w-full rounded-xl border border-ojas/20 bg-gradient-to-br from-card/85 to-card/50 backdrop-blur-md px-4 py-3 group/details shadow-md transition-all duration-300">
                <summary className="flex items-center gap-2.5 cursor-pointer list-none select-none">
                  <BookOpen className="w-4 h-4 text-ojas shrink-0" />
                  <div className="min-w-0 leading-tight">
                    <span className="block text-[12px] font-semibold uppercase tracking-wider text-ojas/90">
                      {t('chat.references')}
                    </span>
                    <span className="block text-[11px] text-muted-foreground/80">
                      Grounded — {citations.length} verified {citations.length === 1 ? 'source' : 'sources'}
                    </span>
                  </div>
                  {typeof message.confidenceScore === 'number' && Number.isFinite(message.confidenceScore) && (
                    <span
                      className="shrink-0 rounded-full bg-card px-2 py-1 text-[10px] font-medium text-foreground/80"
                      title={message.confidenceReason || evidenceSupport(message.confidenceScore).description}
                      aria-label={`Response support: ${evidenceSupport(message.confidenceScore).label}`}
                    >
                      {evidenceSupport(message.confidenceScore).label}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); setSourcesOpen(true); }}
                    className="text-[10px] text-muted-foreground/80 ml-auto bg-muted/40 hover:bg-ojas/15 hover:text-ojas px-2.5 py-0.5 rounded-full transition-colors font-medium shrink-0"
                    aria-label="View all sources in panel"
                  >
                    Open →
                  </button>
                </summary>

                <div className="mt-3.5 space-y-4">
                  {/* YouTube Videos Section */}
                  {(() => {
                    const ytUrls = citations
                      .map((c) => ({ videoId: getYouTubeId(c.url), url: c.url }))
                      .filter((item): item is { videoId: string; url: string } => item.videoId !== null);

                    if (ytUrls.length === 0) return null;

                    return (
                      <div className="space-y-2">
                        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/85 flex items-center gap-1.5 pl-0.5">
                          <Youtube className="w-3.5 h-3.5 text-red-500" />
                          Video Lessons ({ytUrls.length})
                        </p>
                        
                        {ytUrls.length === 1 ? (
                          <div className="w-full max-w-[400px]">
                            <LazyYouTube videoId={ytUrls[0].videoId} url={ytUrls[0].url} />
                          </div>
                        ) : (
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {ytUrls.map(({ videoId, url }) => (
                              <div key={videoId} className="w-full">
                                <LazyYouTube videoId={videoId} url={url} />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* Document/Link References Section */}
                  <div className="space-y-2">
                    <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground/85 pl-0.5">
                      Source Documents
                    </p>
                    <div className="flex flex-col gap-2">
                      {citations.slice(0, 3).map((c, i) => {
                        const url = c.url;
                        const ytId = getYouTubeId(url);
                        const isYT = isYouTubeUrl(url);
                        const displayName = getSourceDisplayName(c, i);
                        const domain = getDomain(url);

                        return (
                          <div
                            key={`${url}-${i}`}
                            className="group/card rounded-lg border border-border/30 bg-background/30 hover:border-ojas/25 hover:bg-background/60 transition-all duration-200 overflow-hidden"
                          >
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-start gap-3 p-2.5"
                            >
                              <div className="flex-shrink-0">
                                {isYT && ytId ? (
                                  <div className="relative w-12 h-9 rounded-md overflow-hidden bg-black/60">
                                    <img
                                      src={`https://img.youtube.com/vi/${ytId}/mqdefault.jpg`}
                                      alt="Video thumbnail"
                                      className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                                      loading="lazy"
                                    />
                                    <div className="absolute inset-0 flex items-center justify-center">
                                      <Play className="w-3.5 h-3.5 text-white drop-shadow-md" fill="white" />
                                    </div>
                                  </div>
                                ) : (
                                  <div className="w-12 h-9 rounded-md bg-ojas/5 flex items-center justify-center border border-ojas/10">
                                    {isYT ? (
                                      <Youtube className="w-3.5 h-3.5 text-red-500" />
                                    ) : (
                                      <ExternalLink className="w-3 h-3 text-ojas/60" />
                                    )}
                                  </div>
                                )}
                              </div>

                              <div className="flex-1 min-w-0 pt-0.5">
                                <p className="text-[12px] font-medium text-ojas group-hover/card:text-ojas-light transition-colors line-clamp-1 leading-snug">
                                  {displayName}
                                </p>
                                <div className="flex items-center gap-1.5 mt-0.5">
                                  <span className="text-[10px] text-muted-foreground/60 truncate max-w-[200px]">
                                    {domain}
                                  </span>
                                  <span className="text-[10px] text-ojas/50 opacity-0 group-hover/card:opacity-100 transition-opacity flex items-center gap-0.5">
                                    <ExternalLink className="w-2.5 h-2.5" />
                                  </span>
                                </div>
                              </div>
                            </a>
                          </div>
                        );
                      })}

                      {citations.length > 3 && (
                        <details className="mt-1">
                          <summary className="text-[11px] text-ojas/70 hover:text-ojas cursor-pointer list-none flex items-center gap-1 py-1 select-none">
                            <ExternalLink className="w-3 h-3" />
                            Show {citations.length - 3} more source{citations.length > 4 ? 's' : ''}
                          </summary>
                          <div className="flex flex-col gap-2 mt-2">
                            {citations.slice(3).map((c, i) => {
                              const url = c.url;
                              const displayName = getSourceDisplayName(c, i + 3);
                              const domain = getDomain(url);
                              return (
                                <a
                                  key={`${url}-${i + 3}`}
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center gap-2 px-2 py-1.5 rounded-md border border-border/20 bg-background/30 hover:bg-background/60 transition-colors"
                                >
                                  <ExternalLink className="w-3 h-3 text-ojas/60 flex-shrink-0" />
                                  <div className="min-w-0">
                                    <p className="text-[11px] font-medium text-ojas line-clamp-1">{displayName}</p>
                                    <p className="text-[10px] text-muted-foreground truncate max-w-[200px]">{domain}</p>
                                  </div>
                                </a>
                              );
                            })}
                          </div>
                        </details>
                      )}
                    </div>
                  </div>
                </div>
              </details>
            )}

            {/* ponytail: CitationPanel = richer source view (YouTube embeds + quotes) triggered from References badge */}
            {isGuru && citations.length > 0 && (
              <CitationPanel
                isOpen={sourcesOpen}
                onClose={() => setSourcesOpen(false)}
                citations={citations}
              />
            )}

            {/* EU AI Act Article 50 Provenance Drawer */}
            {isGuru && (
              <ProvenanceDrawer
                isOpen={provenanceOpen}
                onClose={() => setProvenanceOpen(false)}
                message={message}
              />
            )}

            {/* Timestamped YouTube Discourse Video Player Modal */}
            <DiscourseVideoModal
              isOpen={!!activeVideoCitation}
              onClose={() => setActiveVideoCitation(null)}
              citation={activeVideoCitation}
            />

            {/* In-Situ Link & Wisdom Inspector Modal */}
            <LinkSearchModal
              isOpen={!!activeSearchCitation}
              onClose={() => setActiveSearchCitation(null)}
              citation={activeSearchCitation}
              onPlayVideo={(c) => {
                setActiveSearchCitation(null);
                setActiveVideoCitation(c as DiscourseCitation);
              }}
            />
          </div>

        </motion.div>

        {/* Wisdom Card Modal — lazy-loaded chunk (P1-AI-16); Suspense keeps the
            open state snappy while the chunk loads. */}
        {showWisdomCard && createPortal(
          <Suspense fallback={null}>
            <LazyWisdomCardGenerator
              isOpen={showWisdomCard}
              onClose={() => setShowWisdomCard(false)}
              content={message.content}
            />
          </Suspense>,
          document.body
        )}
      </>
    );
  }
);

ChatMessageInner.displayName = 'ChatMessageInner';

// React.memo to skip re-renders when props haven't changed.
// During streaming, only the actively-streaming message changes.
// P1-AI-17: comparator previously omitted queryText / onSubmitEdit /
// onEditUserMessage — a changing query (e.g. the next message's question)
// or a fresh edit handler then kept rendering stale output and captured
// stale closures for edit/submit. All are primitives or stable identities
// from MessageList, so reference comparison is safe. (Streaming content
// flows through `message.content`, which is compared above.)
export const ChatMessage = memo(ChatMessageInner, (prev, next) => {
  return (
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.feedback === next.message.feedback &&
    prev.isStreaming === next.isStreaming &&
    prev.index === next.index &&
    prev.isLastGuru === next.isLastGuru &&
    prev.message.language === next.message.language &&
    prev.message.guidancePlan === next.message.guidancePlan &&
    prev.message.answerEvidence === next.message.answerEvidence &&
    prev.message.groundingState === next.message.groundingState &&
    prev.queryText === next.queryText &&
    prev.onAction === next.onAction &&
    prev.onRegenerate === next.onRegenerate &&
    prev.onSubmitEdit === next.onSubmitEdit &&
    prev.onEditUserMessage === next.onEditUserMessage &&
    prev.onCitationClick === next.onCitationClick
  );
}) as typeof ChatMessageInner;
(ChatMessage as { displayName?: string }).displayName = 'ChatMessage';

const toBcp47LanguageTag = (language: string | undefined): string => {
  const normalized = (language || 'en').trim();
  if (normalized.includes('-')) return normalized;
  return normalized === 'en' ? 'en-IN' : `${normalized}-IN`;
};


export const LanguageTranslateButton = ({ message }: { message: Message }) => {
  const { t } = useTranslation();
  const { profile } = useProfile();
  const [translated, setTranslated] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const sourceLanguage = toBcp47LanguageTag(message.language);
  const preferredTarget = toBcp47LanguageTag(profile?.preferredLanguage);
  const targetLanguage = sourceLanguage === preferredTarget ? 'en-IN' : preferredTarget;
  if (targetLanguage === sourceLanguage) return <></>;

  const handleTranslate = async () => {
    if (translated) {
      setTranslated(null);
      return;
    }
    setLoading(true);
    const result = await translateText(message.content, targetLanguage, sourceLanguage);
    setTranslated(result || t('chat.translationUnavailable'));
    setLoading(false);
  };

  return (
    <div className="relative">
      <button
        onClick={handleTranslate}
        disabled={loading}
        className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
        title={translated ? t('chat.showOriginal') : t('chat.translateTo', { lang: targetLanguage.split('-')[0] })}
      >
        {loading ? (
          <span className="w-3 h-3 block rounded-full border border-ojas border-t-transparent animate-spin" />
        ) : (
          <Languages className="w-4 h-4" />
        )}
      </button>
      <AnimatePresence>
        {translated && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute bottom-full right-0 mb-2 w-72 p-2 rounded-lg bg-popover border border-border shadow-lg text-xs text-popover-foreground z-50"
          >
            <p className="leading-relaxed">{translated}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
