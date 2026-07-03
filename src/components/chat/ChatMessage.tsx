import { forwardRef, useState, useCallback, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ExternalLink, Share2, ThumbsUp, ThumbsDown, X, Shield, Copy, Check, RotateCcw, Pencil, BookOpen, Youtube, Play, AlertTriangle, LogIn, RefreshCw, Bookmark, StickyNote, Languages } from 'lucide-react';
import { useNotes } from '@/hooks/useNotes';
import { useStudyNotebooks } from '@/hooks/useStudyNotebooks';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import { Message, saveFeedback, type MessageFeedback } from '@/lib/chatStorage';
import { useProfile } from '@/hooks/useProfile';
import { submitFeedbackToBackend, translateText } from '@/lib/aiService';
import { WisdomCardGenerator } from './WisdomCardGenerator';
import { InlineActions } from './InlineActions';
import { createPortal } from 'react-dom';
import { memoryApi } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';
import { CitationPanel, type Citation } from './CitationPanel';

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


const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

/** Extract YouTube video ID from various YouTube URL formats */
const getYouTubeId = (url: string): string | null => {
  try {
    if (url.includes('youtu.be/')) {
      return url.split('youtu.be/')[1]?.split('?')[0];
    }
    if (url.includes('v=')) {
      return url.split('v=')[1]?.split('&')[0];
    }
    if (url.includes('/embed/')) {
      return url.split('/embed/')[1]?.split('?')[0];
    }
    return null;
  } catch {
    return null;
  }
};

/** Check if a URL is a YouTube link */
const isYouTubeUrl = (url: string): boolean => {
  return url.includes('youtube.com') || url.includes('youtu.be');
};

/** Lazy YouTube embed: thumbnail → click → iframe */
const LazyYouTube = ({ videoId, url }: { videoId: string; url: string }) => {
  const [loaded, setLoaded] = useState(false);
  const thumbnail = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

  if (loaded) {
    return (
      <div className="rounded-xl overflow-hidden shadow-md border border-border/30 bg-black/5 aspect-video w-full max-w-[400px]">
        <iframe
          width="100%"
          height="100%"
          src={`https://www.youtube.com/embed/${videoId}?autoplay=1`}
          title="YouTube video player"
          frameBorder="0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
    );
  }

  return (
    <div
      className="rounded-xl overflow-hidden shadow-md border border-border/30 bg-black/5 aspect-video w-full max-w-[400px] relative cursor-pointer group"
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
        <div className="w-12 h-12 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
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

/** Get a display name for a source URL (e.g., 'YouTube — YouTube Domain') */
const getSourceDisplayName = (url: string, index: number): string => {
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
      return `Teaching Reference`;
    }
    return hostname;
  } catch {
    return `Source ${index + 1}`;
  }
};

const FEEDBACK_TAGS = ['Clear answer', 'Relevant sources', 'Calming tone', 'Insightful'];

const ChatMessageInner = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, queryText, index = 0, isStreaming = false, isLastGuru = false, onRegenerate, onEditUserMessage, onSubmitEdit, onAction, onCitationClick }, ref) => {
    const isGuru = message.role === 'guru';
    const navigate = useNavigate();
    const { profile } = useProfile();
    // Extract any https:// URL from the guru's response as a fallback citation.
    // Covers: YouTube links, source references like "Source: https://...", inline citations.
    const inlineUrls = isGuru
      ? Array.from(new Set(
          (message.content.match(/https?:\/\/[^\s)"'<>]+/g) ?? [])
            .filter(u => { try { new URL(u); return true; } catch { return false; } })
        ))
      : [];
    const citations = (message.citations && message.citations.length > 0)
      ? message.citations
      : inlineUrls;

    const [showWisdomCard, setShowWisdomCard] = useState(false);
    const [copied, setCopied] = useState(false);
    const [saved, setSaved] = useState(false);
    const [savingMemory, setSavingMemory] = useState(false);
    const [feedback, setFeedback] = useState<MessageFeedback | null>(message.feedback ?? null);
    const [showFeedbackPanel, setShowFeedbackPanel] = useState(false);
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [feedbackComment, setFeedbackComment] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(message.content);
    const [noteSaved, setNoteSaved] = useState(false);
    const [sourcesOpen, setSourcesOpen] = useState(false);
    const { toast } = useToast();
    const { createNote } = useNotes();
    const { notebooks, createNotebook, addItem } = useStudyNotebooks();

    const handleSaveAsNote = useCallback(async () => {
      const snippet = (queryText ? `**Question:** ${queryText}\n\n**Teaching:**\n` : '') + message.content;
      // Prefer study notebooks; fall back to legacy notes table
      try {
        let target: typeof notebooks[number] | undefined = notebooks[0];
        if (!target) {
          target = (await createNotebook('Saved from Chat')) ?? undefined;
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
        title: queryText ? queryText.slice(0, 80) : 'Teaching',
        body: snippet,
        tags: ['from-chat'],
        source_message_id: message.id,
      });
      if (note) {
        setNoteSaved(true);
        setTimeout(() => setNoteSaved(false), 2000);
        toast({ title: 'Saved to Notes', description: 'Find it under Profile → Notes.' });
      } else {
        toast({ title: 'Sign in to save notes', variant: 'destructive' });
      }
    }, [createNote, createNotebook, addItem, notebooks, message.content, message.id, queryText, toast]);

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      } catch { /* ignore */ }
    }, [message.content]);

    const handleSaveToMemory = useCallback(async () => {
      if (saved || savingMemory) return;
      setSavingMemory(true);
      try {
        // Use the user's question + a short slice of the answer as the saved fact.
        const snippet = (queryText ? `Q: ${queryText}\nA: ` : '') + message.content.slice(0, 600);
        await memoryApi.add(snippet);
        setSaved(true);
        toast({ title: 'Saved to your memory', description: 'The Guru will recall this in future conversations.' });
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
    }, [saved, savingMemory, queryText, message.content, toast]);

    const handleVote = useCallback((vote: 'up' | 'down') => {
      if (feedback) return;
      setFeedback({ vote, tags: [], timestamp: new Date() });
      setShowFeedbackPanel(true);
    }, [feedback]);

    const handleSubmitFeedback = useCallback(() => {
      if (!feedback) return;
      const finalFeedback: MessageFeedback = {
        ...feedback,
        tags: selectedTags,
        comment: feedbackComment.trim() || undefined,
      };
      saveFeedback(message.id, finalFeedback);
      setFeedback(finalFeedback);
      setShowFeedbackPanel(false);

      if (queryText && message.content) {
        submitFeedbackToBackend({
          query: queryText,
          answer: message.content,
          rating: finalFeedback.vote === 'up' ? 1 : -1,
          comment: finalFeedback.comment || finalFeedback.tags.join(', ')
        });
      }
    }, [feedback, selectedTags, feedbackComment, message.id, queryText, message.content]);

    const handleDismissFeedback = useCallback(() => {
      if (!feedback) return;
      saveFeedback(message.id, feedback);
      setShowFeedbackPanel(false);
    }, [feedback, message.id]);

    const toggleTag = (tag: string) => {
      setSelectedTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag]);
    };

    return (
      <>
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.15) }}
          className={`group flex items-start gap-3 ${isGuru ? 'justify-start' : 'justify-end'}`}
          data-message-id={message.id}
        >
          <div className={`${isEditing ? 'w-full max-w-[95%] sm:max-w-[85%]' : isGuru ? 'w-full max-w-full' : 'max-w-[75%]'} flex flex-col gap-1 ${isGuru ? 'items-start' : 'items-end'}`}>
            {/* Message body */}
            <div
              className={`relative w-full transition-all duration-300 ${
                isGuru
                  ? 'text-[15.5px] leading-[1.75] text-foreground/90 font-normal'
                  : isEditing
                  ? 'bg-card border border-ojas/40 rounded-2xl px-4 py-3 shadow-md'
                  : 'bg-ojas/[0.10] border border-ojas/20 rounded-2xl rounded-tr-md px-4 py-2.5 text-[15px] text-foreground leading-relaxed'
              }`}
            >
              {isGuru && !message.error && (
                <div className="w-5 h-5 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 float-left mr-2 mt-1">
                  <Sparkles className="w-2.5 h-2.5 text-ojas/70" />
                </div>
              )}
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
                  <div className="prose prose-sm dark:prose-invert max-w-none
                    prose-p:mb-2.5 prose-p:mt-0 prose-p:leading-relaxed
                    prose-li:mb-1 prose-strong:text-ojas prose-strong:font-semibold
                    prose-headings:text-foreground prose-headings:font-bold prose-headings:text-base prose-headings:mb-2
                    prose-a:text-ojas prose-a:no-underline hover:prose-a:underline
                    prose-pre:overflow-x-auto prose-pre:max-w-full
                    selection:bg-ojas/20">
                    {/* While streaming with no content, render nothing — the single
                        ThinkingPills indicator in ChatInterface is the source of truth.
                        This prevents two simultaneous "thinking" indicators. */}
                    {isStreaming && !message.content ? null : (
                      <ReactMarkdown
                        components={{
                          a: ({ href, children, ...rest }) => {
                            const match = typeof href === 'string' ? href.match(/^#cite-(\d+)$/) : null;
                            if (match) {
                              const n = parseInt(match[1], 10);
                              return (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.preventDefault();
                                    onCitationClick?.(message.id, n - 1);
                                  }}
                                  className="inline-flex items-center justify-center align-super mx-[1px] px-[5px] min-w-[18px] h-[18px] rounded-md text-[10px] font-semibold tabular-nums bg-ojas/10 text-ojas border border-ojas/30 hover:bg-ojas/20 hover:border-ojas/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas transition-colors"
                                  aria-label={`Show source ${n} in the sources panel`}
                                  title={`Source ${n} — click to open in Sources`}
                                >
                                  {n}
                                </button>
                              );
                            }
                            return (
                              <a href={href} {...rest} target="_blank" rel="noopener noreferrer">
                                {children}
                              </a>
                            );
                          },
                        }}
                      >
                        {injectCitationLinks(message.content, (message.citations ?? []).length)}
                      </ReactMarkdown>
                    )}

                  </div>
                  )
                ) : isEditing ? (
                  <div className="flex flex-col gap-2 w-full">
                    <p className="text-[11px] text-muted-foreground font-sans italic">
                      Edit your question — earlier replies below will be regenerated.
                    </p>
                    <textarea
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      autoFocus
                      rows={Math.max(2, Math.min(10, editValue.split('\n').length + 1))}
                      ref={(el) => { if (el) { el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 240)}px`; el.setSelectionRange(el.value.length, el.value.length); } }}
                      className="w-full bg-background border border-border rounded-lg p-3 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-ojas/60 focus:ring-2 focus:ring-ojas/20 resize-none leading-relaxed"
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
                      <span className="text-[10px] text-muted-foreground/70">
                        ⌘↵ to save · Esc to cancel
                      </span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => { setEditValue(message.content); setIsEditing(false); }}
                          className="px-3 py-1.5 rounded-md text-[12px] font-medium text-muted-foreground hover:bg-muted transition-colors"
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
                          className="px-3 py-1.5 rounded-md text-[12px] font-semibold bg-ojas text-primary-foreground hover:bg-ojas-light disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          Save &amp; resend
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <span className="font-medium">{message.content}</span>
                )}
                {isStreaming && (
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
                    className="inline-block w-[2px] h-[1em] bg-ojas ml-0.5 align-text-bottom"
                  />
                )}
              </div>

              {/* Inline action buttons for guru messages */}
              {isGuru && message.content && !isStreaming && onAction && !message.error && !message.content.includes('_Stopped by you._') && (
                <InlineActions messageContent={message.content} onAction={onAction} />
              )}

              {/* Lazy YouTube Thumbnails — show max 2 inline, rest in references */}
              {isGuru && citations.length > 0 && (() => {
                const ytUrls = citations
                  .filter(url => url.includes('youtube.com/watch') || url.includes('youtu.be/'))
                  .map((url) => {
                    const videoId = url.includes('v=')
                      ? url.split('v=')[1]?.split('&')[0]
                      : url.split('/').pop();
                    return videoId ? { videoId, url } : null;
                  })
                  .filter(Boolean) as { videoId: string; url: string }[];
                const inline = ytUrls.slice(0, 2);
                const extra = ytUrls.slice(2);
                return inline.length > 0 ? (
                  <div className="space-y-2.5 mt-2">
                    {inline.map(({ videoId, url }) => (
                      <LazyYouTube key={videoId} videoId={videoId} url={url} />
                    ))}
                    {extra.length > 0 && (
                      <details className="mt-1.5 rounded-lg border border-ojas/15 bg-ojas/5 px-3 py-2">
                        <summary className="text-[11px] font-medium text-ojas/80 cursor-pointer select-none flex items-center gap-1.5">
                          <Youtube className="w-3 h-3" />
                          {extra.length} more video{extra.length > 1 ? 's' : ''}
                        </summary>
                        <div className="space-y-2.5 mt-2">
                          {extra.map(({ videoId, url }) => (
                            <LazyYouTube key={videoId} videoId={videoId} url={url} />
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                ) : null;
              })()}

              {/* Hover-only timestamp */}
              <time className="opacity-0 group-hover:opacity-60 text-[11px] text-muted-foreground transition-opacity mt-1 block">
                {formatTime(message.timestamp)}
              </time>

              {/* Guru hover actions */}
              {isGuru && message.content && !isStreaming && !message.content.includes('_Stopped by you._') && (
                <div className="flex items-center gap-0.5 mt-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  {isLastGuru && onRegenerate && (
                    <button
                      onClick={onRegenerate}
                      className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                      title="Regenerate response"
                    >
                      <RotateCcw className="w-3 h-3" />
                    </button>
                  )}
                  <button
                    onClick={() => handleVote('up')}
                    className={`p-1 rounded-full transition-colors ${
                      feedback?.vote === 'up'
                        ? 'bg-green-500/15 text-green-600 dark:text-green-400'
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                    }`}
                    title="Helpful"
                    disabled={!!feedback}
                  >
                    <ThumbsUp className="w-3 h-3" />
                  </button>
                  <button
                    onClick={() => handleVote('down')}
                    className={`p-1 rounded-full transition-colors ${
                      feedback?.vote === 'down'
                        ? 'bg-red-500/15 text-red-600 dark:text-red-400'
                        : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                    }`}
                    title="Not helpful"
                    disabled={!!feedback}
                  >
                    <ThumbsDown className="w-3 h-3" />
                  </button>
                  <button
                    onClick={handleCopy}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={copied ? 'Copied!' : 'Copy response'}
                  >
                    {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  </button>
                  <button
                    onClick={handleSaveToMemory}
                    disabled={saved || savingMemory}
                    className={`p-1 rounded-full transition-colors ${
                      saved
                        ? 'bg-prana/15 text-prana'
                        : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                    } ${savingMemory ? 'opacity-60' : ''}`}
                    title={saved ? 'Saved to memory' : 'Save to memory'}
                  >
                    <Bookmark className={`w-3 h-3 ${saved ? 'fill-current' : ''}`} />
                  </button>
                  <button
                    onClick={handleSaveAsNote}
                    className={`p-1 rounded-full transition-colors ${
                      noteSaved
                        ? 'bg-prana/15 text-prana'
                        : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                    }`}
                    title={noteSaved ? 'Saved to Notes' : 'Save as note'}
                  >
                    <StickyNote className={`w-3 h-3 ${noteSaved ? 'fill-current' : ''}`} />
                  </button>
                  <button
                    onClick={() => setShowWisdomCard(true)}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title="Share as Wisdom Card"
                  >
                    <Share2 className="w-3 h-3" />
                  </button>
                  <LanguageTranslateButton message={message} />
                </div>
              )}

              {/* User hover actions */}
              {!isGuru && message.content && !isStreaming && !isEditing && (
                <div className="flex items-center justify-end gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 mt-1">
                  <button
                    onClick={handleCopy}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={copied ? 'Copied!' : 'Copy question'}
                  >
                    {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
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
                      title="Edit & resend"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* Feedback panel */}
            <AnimatePresence>
              {showFeedbackPanel && feedback && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="w-full rounded-xl border border-border/50 bg-card/90 backdrop-blur-sm px-3 py-2.5 space-y-2 overflow-hidden"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-medium text-muted-foreground">
                      {feedback.vote === 'up' ? 'What helped?' : 'What could improve?'}
                    </p>
                    <button onClick={handleDismissFeedback} className="p-0.5 rounded hover:bg-muted">
                      <X className="w-3 h-3 text-muted-foreground" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {FEEDBACK_TAGS.map(tag => (
                      <button
                        key={tag}
                        onClick={() => toggleTag(tag)}
                        className={`px-2.5 py-1 rounded-full text-[11px] border transition-all ${
                          selectedTags.includes(tag)
                            ? 'border-ojas/50 bg-ojas/10 text-ojas font-medium'
                            : 'border-border/60 text-muted-foreground hover:border-ojas/30'
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                  <input
                    type="text"
                    placeholder="Optional: tell us more…"
                    value={feedbackComment}
                    onChange={(e) => setFeedbackComment(e.target.value)}
                    className="w-full bg-transparent border-b border-border/30 text-[12px] py-1 outline-none focus:border-ojas/40 text-foreground placeholder:text-muted-foreground/75"
                  />
                  <button
                    onClick={handleSubmitFeedback}
                    className="text-[11px] font-medium text-ojas hover:text-ojas-light transition-colors"
                  >
                    Submit feedback
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Confidence score — color-coded badge */}
            {isGuru && message.confidenceScore != null && message.confidenceScore > 0 && (() => {
              const score = message.confidenceScore;
              // score is 1-10 from backend
              const pct = Math.round((score / 10) * 100);
              const isHigh = score >= 7;
              const isMed  = score >= 4 && score < 7;
              const colorDot  = isHigh ? 'bg-emerald-400' : isMed ? 'bg-amber-400' : 'bg-rose-400';
              const colorText = isHigh ? 'text-emerald-400' : isMed ? 'text-amber-400' : 'text-rose-400';
              const colorBorder = isHigh ? 'border-emerald-400/25' : isMed ? 'border-amber-400/25' : 'border-rose-400/25';
              const colorBg = isHigh ? 'bg-emerald-400/8' : isMed ? 'bg-amber-400/8' : 'bg-rose-400/8';
              const label = isHigh ? 'High confidence' : isMed ? 'Moderate confidence' : 'Low confidence';
              return (
                <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${colorBorder} ${colorBg}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${colorDot} shrink-0`} />
                  <span className={`text-[10px] font-medium ${colorText}`}>
                    {label} · {pct}%
                  </span>
                </div>
              );
            })()}

            {/* Memory provenance — surfaces facts the Guru recalled from your reflections */}
            {isGuru && message.memoriesUsed && message.memoriesUsed.length > 0 && (
              <details className="w-full rounded-lg border border-ojas/15 bg-ojas/5 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-medium text-ojas/80 select-none">
                  Recalled from your reflections ({message.memoriesUsed.length})
                </summary>
                <ul className="mt-2 space-y-1 list-disc pl-4 text-muted-foreground">
                  {message.memoriesUsed.slice(0, 6).map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Follow-up suggestions as clickable chips */}
            {isGuru && message.followUpSuggestions && message.followUpSuggestions.length > 0 && !isStreaming && onAction && !message.content.includes('_Stopped by you._') && (
              <div className="w-full mt-1">
                <p className="text-[10px] text-muted-foreground/60 mb-2 pl-0.5">Suggested follow-ups</p>
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

            {/* Sources / Citations — collapsed by default, max 3 shown inline */}
            {isGuru && citations.length > 0 && (
              <details className="w-full rounded-xl border border-ojas/20 bg-gradient-to-br from-card/80 to-card/50 backdrop-blur-sm px-4 py-3 group/details">
                <summary className="flex items-center gap-2 cursor-pointer list-none">
                  <BookOpen className="w-3.5 h-3.5 text-ojas" />
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-ojas/80">
                    References
                  </p>
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); setSourcesOpen(true); }}
                    className="text-[10px] text-muted-foreground/75 ml-auto bg-muted/30 hover:bg-ojas/15 hover:text-ojas px-2 py-0.5 rounded-full transition-colors"
                    aria-label="View all sources in panel"
                  >
                    {citations.length} {citations.length === 1 ? 'source' : 'sources'} →
                  </button>
                </summary>

                {/* Citation Cards — show first 3 inline */}
                <div className="flex flex-col gap-2 mt-2">
                  {citations.slice(0, 3).map((url, i) => {
                    const ytId = getYouTubeId(url);
                    const isYT = isYouTubeUrl(url);
                    const displayName = getSourceDisplayName(url, i);
                    const domain = getDomain(url);

                    return (
                      <div
                        key={`${url}-${i}`}
                        className="group rounded-lg border border-border/30 bg-background/40 hover:border-ojas/25 hover:bg-background/60 transition-all duration-200 overflow-hidden"
                      >
                        {/* Main citation card */}
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-start gap-3 p-2.5"
                        >
                          {/* Icon / Thumbnail */}
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
                                  <Play className="w-4 h-4 text-white drop-shadow-md" fill="white" />
                                </div>
                              </div>
                            ) : (
                              <div className="w-12 h-9 rounded-md bg-ojas/8 flex items-center justify-center border border-ojas/10">
                                {isYT ? (
                                  <Youtube className="w-4 h-4 text-red-500" />
                                ) : (
                                  <ExternalLink className="w-3.5 h-3.5 text-ojas/60" />
                                )}
                              </div>
                            )}
                          </div>

                          {/* Text content */}
                          <div className="flex-1 min-w-0 pt-0.5">
                            <p className="text-[12px] font-medium text-ojas group-hover:text-ojas-light transition-colors line-clamp-1 leading-snug">
                              {displayName}
                            </p>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="text-[10px] text-muted-foreground/60 truncate max-w-[180px]">
                                {domain}
                              </span>
                              <span className="text-[10px] text-ojas/40 hidden group-hover:inline-flex items-center gap-0.5 group-hover/link:underline transition-all">
                                <ExternalLink className="w-2.5 h-2.5 inline" />
                              </span>
                            </div>
                          </div>
                        </a>
                      </div>
                    );
                  })}

                  {/* Show more when >3 citations — rest as compact links */}
                  {citations.length > 3 && (
                    <details className="mt-1">
                      <summary className="text-[11px] text-ojas/70 hover:text-ojas cursor-pointer list-none flex items-center gap-1 py-1">
                        <ExternalLink className="w-3 h-3" />
                        Show {citations.length - 3} more source{citations.length > 4 ? 's' : ''}
                      </summary>
                      <div className="flex flex-col gap-2 mt-2">
                        {citations.slice(3).map((url, i) => {
                          const displayName = getSourceDisplayName(url, i + 3);
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
                                <p className="text-[10px] text-muted-foreground/50 truncate max-w-[200px]">{domain}</p>
                              </div>
                            </a>
                          );
                        })}
                      </div>
                    </details>
                  )}
                </div>
              </details>
            )}

            {/* ponytail: CitationPanel = richer source view (YouTube embeds + quotes) triggered from References badge */}
            {isGuru && citations.length > 0 && (
              <CitationPanel
                isOpen={sourcesOpen}
                onClose={() => setSourcesOpen(false)}
                citations={citations.map((url): Citation => ({ url }))}
              />
            )}
          </div>

        </motion.div>

        {/* Wisdom Card Modal */}
        {showWisdomCard && createPortal(
          <WisdomCardGenerator
            isOpen={showWisdomCard}
            onClose={() => setShowWisdomCard(false)}
            content={message.content}
          />,
          document.body
        )}
      </>
    );
  }
);

ChatMessageInner.displayName = 'ChatMessageInner';

// React.memo to skip re-renders when props haven't changed.
// During streaming, only the actively-streaming message changes.
export const ChatMessage = memo(ChatMessageInner, (prev, next) => {
  return (
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.feedback === next.message.feedback &&
    prev.isStreaming === next.isStreaming &&
    prev.index === next.index
  );
}) as typeof ChatMessageInner;
(ChatMessage as { displayName?: string }).displayName = 'ChatMessage';

const LanguageTranslateButton = ({ message }: { message: Message }) => {
  const { profile } = useProfile();
  const [translated, setTranslated] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const lang = profile?.preferredLanguage;
  const isEnglish = !lang || lang === 'en';
  if (isEnglish) return null;

  const handleTranslate = async () => {
    if (translated) {
      setTranslated(null);
      return;
    }
    setLoading(true);
    const result = await translateText(message.content, lang, 'en-IN');
    setTranslated(result || 'Translation unavailable');
    setLoading(false);
  };

  return (
    <div className="relative">
      <button
        onClick={handleTranslate}
        disabled={loading}
        className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
        title={translated ? 'Show original' : `Translate to ${lang}`}
      >
        {loading ? (
          <span className="w-3 h-3 block rounded-full border border-ojas border-t-transparent animate-spin" />
        ) : (
          <Languages className="w-3 h-3" />
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
