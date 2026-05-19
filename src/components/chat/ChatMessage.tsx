import { forwardRef, useState, useCallback, memo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ExternalLink, Share2, ThumbsUp, ThumbsDown, X, Shield, Copy, Check, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Message, saveFeedback, type MessageFeedback } from '@/lib/chatStorage';
import { useProfile } from '@/hooks/useProfile';
import { getInitials } from '@/lib/profileStorage';
import { submitFeedbackToBackend } from '@/lib/aiService';
import { WisdomCardGenerator } from './WisdomCardGenerator';
import { createPortal } from 'react-dom';

interface ChatMessageProps {
  message: Message;
  queryText?: string;
  index?: number;
  isStreaming?: boolean;
  isLastGuru?: boolean;
  onRegenerate?: () => void;
}

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const FEEDBACK_TAGS = ['Clear answer', 'Relevant sources', 'Calming tone', 'Insightful'];

const ChatMessageInner = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, queryText, index = 0, isStreaming = false, isLastGuru = false, onRegenerate }, ref) => {
    const isGuru = message.role === 'guru';
    const { profile } = useProfile();
    // Extract any https:// URL from the guru's response as a fallback citation.
    // Covers: YouTube links, source references like "Source: https://...", inline citations.
    const inlineUrls = isGuru
      ? Array.from(new Set(
          (message.content.match(/https?:\/\/[^\s\)"'<>]+/g) ?? [])
            .filter(u => { try { new URL(u); return true; } catch { return false; } })
        ))
      : [];
    const citations = (message.citations && message.citations.length > 0)
      ? message.citations
      : inlineUrls;

    const [showWisdomCard, setShowWisdomCard] = useState(false);
    const [copied, setCopied] = useState(false);
    const [feedback, setFeedback] = useState<MessageFeedback | null>(message.feedback ?? null);
    const [showFeedbackPanel, setShowFeedbackPanel] = useState(false);
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [feedbackComment, setFeedbackComment] = useState('');

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
          className={`group flex items-start gap-2.5 ${isGuru ? 'justify-start' : 'justify-end'}`}
        >
          {/* Guru avatar */}
          {isGuru && (
            <div className="w-7 h-7 rounded-full bg-ojas/12 border border-ojas/20 flex items-center justify-center flex-shrink-0 mt-0.5">
              <Sparkles className="w-3 h-3 text-ojas" />
            </div>
          )}

          <div className={`max-w-[85%] sm:max-w-[75%] flex flex-col gap-1 ${isGuru ? 'items-start' : 'items-end'}`}>
            {/* Message body */}
            <div
              className={`message-bubble relative w-full transition-all duration-300 ${
                isGuru
                  ? 'border-l-[3px] border-ojas/30 pl-4 pr-1 py-1 hover:border-ojas/50'
                  : 'bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 shadow-sm hover:shadow-md'
              }`}
            >
              <div
                className={`text-[14px] leading-relaxed break-words ${
                  isGuru ? 'text-foreground/90' : 'whitespace-pre-wrap'
                }`}
              >
                {isGuru ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none 
                    prose-p:mb-2.5 prose-p:mt-0 prose-p:leading-relaxed
                    prose-li:mb-1 prose-strong:text-ojas prose-strong:font-semibold
                    prose-headings:text-foreground prose-headings:font-bold prose-headings:text-base prose-headings:mb-2
                    prose-a:text-ojas prose-a:no-underline hover:prose-a:underline
                    selection:bg-ojas/20">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
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

              {/* YouTube Embeds (Triggered videos) */}
              {isGuru && citations.length > 0 && (
                <div className="space-y-2.5 mt-2">
                  {citations
                    .filter(url => url.includes('youtube.com/watch') || url.includes('youtu.be/'))
                    .map((url, i) => {
                      const videoId = url.includes('v=') 
                        ? url.split('v=')[1]?.split('&')[0] 
                        : url.split('/').pop();
                      if (!videoId) return null;
                      return (
                        <div key={videoId} className="rounded-xl overflow-hidden shadow-md border border-border/30 bg-black/5 aspect-video w-full max-w-[400px]">
                          <iframe
                            width="100%"
                            height="100%"
                            src={`https://www.youtube.com/embed/${videoId}`}
                            title="YouTube video player"
                            frameBorder="0"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                          ></iframe>
                        </div>
                      );
                    })}
                </div>
              )}

              {/* Timestamp + action buttons */}
              <div className="flex items-center justify-between mt-1 gap-2">
                <p className={`text-[10px] ${isGuru ? 'text-muted-foreground/50' : 'text-primary-foreground/50'}`}>
                  {formatTime(message.timestamp)}
                </p>
                {isGuru && message.content && !isStreaming && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                    {/* Regenerate — only on last guru message */}
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
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(message.content);
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1500);
                        } catch { /* ignore */ }
                      }}
                      className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                      title={copied ? 'Copied!' : 'Copy response'}
                    >
                      {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                    </button>
                    <button
                      onClick={() => setShowWisdomCard(true)}
                      className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                      title="Share as Wisdom Card"
                    >
                      <Share2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
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
                    className="w-full bg-transparent border-b border-border/30 text-[12px] py-1 outline-none focus:border-ojas/40 text-foreground placeholder:text-muted-foreground/50"
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

            {/* Confidence score */}
            {isGuru && message.confidenceScore != null && message.confidenceScore > 0 && (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-prana/10 border border-prana/20">
                <Shield className="w-3 h-3 text-prana" />
                <span className="text-[10px] font-medium text-prana">
                  Confidence: {message.confidenceScore}/10
                </span>
              </div>
            )}

            {/* Sources */}
            {isGuru && citations.length > 0 && (
              <div className="w-full rounded-xl border border-border/40 bg-card/60 backdrop-blur-sm px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Sources
                </p>
                <div className="flex flex-col gap-1">
                  {citations.map((url, i) => (
                    <a
                      key={`${url}-${i}`}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-[11px] text-ojas hover:text-ojas-light transition-colors group/link"
                    >
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate group-hover/link:underline">{getDomain(url)}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* User avatar */}
          {!isGuru && (
            <div className="w-7 h-7 rounded-full bg-prana/12 border border-prana/20 flex items-center justify-center flex-shrink-0 overflow-hidden mt-0.5">
              {profile.avatarDataUrl ? (
                <img src={profile.avatarDataUrl} alt={profile.displayName} className="w-full h-full object-cover" />
              ) : (
                <span className="text-[10px] font-semibold text-prana-dark dark:text-prana">
                  {getInitials(profile.displayName)}
                </span>
              )}
            </div>
          )}
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

const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
