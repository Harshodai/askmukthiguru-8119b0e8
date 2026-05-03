import { forwardRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ExternalLink, Share2, ThumbsUp, ThumbsDown, X, Shield } from 'lucide-react';
import { Message, saveFeedback, type MessageFeedback } from '@/lib/chatStorage';
import { useProfile } from '@/hooks/useProfile';
import { getInitials } from '@/lib/profileStorage';
import { WisdomCardGenerator } from './WisdomCardGenerator';

interface ChatMessageProps {
  message: Message;
  index?: number;
  isStreaming?: boolean;
}

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const FEEDBACK_TAGS = ['Clear answer', 'Relevant sources', 'Calming tone', 'Insightful'];

export const ChatMessage = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, index = 0, isStreaming = false }, ref) => {
    const isGuru = message.role === 'guru';
    const { profile } = useProfile();
    const citations = message.citations ?? [];
    const [showWisdomCard, setShowWisdomCard] = useState(false);
    const [feedback, setFeedback] = useState<MessageFeedback | null>(message.feedback ?? null);
    const [showFeedbackPanel, setShowFeedbackPanel] = useState(false);
    const [selectedTags, setSelectedTags] = useState<string[]>([]);
    const [feedbackComment, setFeedbackComment] = useState('');

    const handleVote = useCallback((vote: 'up' | 'down') => {
      if (feedback) return; // Already voted
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
    }, [feedback, selectedTags, feedbackComment, message.id]);

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
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.2) }}
          className={`group flex items-start gap-2.5 ${isGuru ? 'justify-start' : 'justify-end'}`}
        >
          {isGuru && (
            <div className="w-8 h-8 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center flex-shrink-0 dark:shadow-[0_0_8px_hsl(43_96%_56%/0.2)]">
              <Sparkles className="w-4 h-4 text-ojas" />
            </div>
          )}

          <div className={`max-w-[82%] sm:max-w-[75%] flex flex-col gap-1.5 ${isGuru ? 'items-start' : 'items-end'}`}>
            <div
              className={`relative px-4 py-2.5 ${
                isGuru
                  ? 'glass-card rounded-2xl rounded-tl-md shadow-sm dark:shadow-inner dark:shadow-ojas/5'
                  : 'bg-gradient-to-br from-ojas to-ojas-light text-primary-foreground rounded-2xl rounded-tr-md shadow-md'
              }`}
            >
              <p
                className={`text-[14px] leading-relaxed whitespace-pre-wrap break-words ${
                  isGuru ? 'text-foreground' : ''
                }`}
              >
                {message.content}
                {isStreaming && (
                  <motion.span
                    animate={{ opacity: [1, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
                    className="inline-block w-[2px] h-[1em] bg-ojas ml-0.5 align-text-bottom"
                  />
                )}
              </p>
              <div className="flex items-center justify-between mt-1.5 gap-2">
                <p
                  className={`text-[10px] ${
                    isGuru ? 'text-muted-foreground/70' : 'text-primary-foreground/70'
                  }`}
                >
                  {formatTime(message.timestamp)}
                </p>
                {/* Action buttons on guru messages */}
                {isGuru && message.content && !isStreaming && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    {/* Thumbs up */}
                    <button
                      onClick={() => handleVote('up')}
                      className={`p-1 rounded-full transition-colors ${
                        feedback?.vote === 'up'
                          ? 'bg-green-500/15 text-green-600'
                          : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                      }`}
                      title="Helpful"
                      disabled={!!feedback}
                    >
                      <ThumbsUp className="w-3 h-3" />
                    </button>
                    {/* Thumbs down */}
                    <button
                      onClick={() => handleVote('down')}
                      className={`p-1 rounded-full transition-colors ${
                        feedback?.vote === 'down'
                          ? 'bg-red-500/15 text-red-600'
                          : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                      }`}
                      title="Not helpful"
                      disabled={!!feedback}
                    >
                      <ThumbsDown className="w-3 h-3" />
                    </button>
                    {/* Share */}
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

            {/* Feedback panel (expanded after voting) */}
            <AnimatePresence>
              {showFeedbackPanel && feedback && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="w-full rounded-xl border border-border/60 bg-card/80 backdrop-blur-sm px-3 py-2.5 space-y-2 overflow-hidden"
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
                            : 'border-border text-muted-foreground hover:border-ojas/30'
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
                    className="w-full bg-transparent border-b border-border/40 text-[12px] py-1 outline-none focus:border-ojas/40 text-foreground placeholder:text-muted-foreground/50"
                  />
                  <button
                    onClick={handleSubmitFeedback}
                    className="text-[11px] font-medium text-ojas hover:text-ojas-light transition-colors"
                  >
                    Submit
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Confidence score badge */}
            {isGuru && message.confidenceScore != null && message.confidenceScore > 0 && (
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-prana/10 border border-prana/20">
                <Shield className="w-3 h-3 text-prana" />
                <span className="text-[10px] font-medium text-prana">
                  Confidence: {message.confidenceScore}/10
                </span>
              </div>
            )}

            {/* Sources card */}
            {isGuru && citations.length > 0 && (
              <div className="w-full rounded-xl border border-border/60 bg-card/60 backdrop-blur-sm px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                  Sources
                </p>
                <div className="flex flex-col gap-1">
                  {citations.slice(0, 3).map((url, i) => (
                    <a
                      key={`${url}-${i}`}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-[11px] text-ojas hover:text-ojas-light transition-colors group"
                    >
                      <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      <span className="truncate group-hover:underline">{getDomain(url)}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>

          {!isGuru && (
            <div className="w-8 h-8 rounded-full bg-prana/15 border border-prana/25 flex items-center justify-center flex-shrink-0 overflow-hidden">
              {profile.avatarDataUrl ? (
                <img src={profile.avatarDataUrl} alt={profile.displayName} className="w-full h-full object-cover" />
              ) : (
                <span className="text-[10px] font-semibold text-prana-dark">
                  {getInitials(profile.displayName)}
                </span>
              )}
            </div>
          )}
        </motion.div>

        {/* Wisdom Card Generator Modal */}
        <WisdomCardGenerator
          isOpen={showWisdomCard}
          onClose={() => setShowWisdomCard(false)}
          content={message.content}
        />
      </>
    );
  }
);

ChatMessage.displayName = 'ChatMessage';

const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
