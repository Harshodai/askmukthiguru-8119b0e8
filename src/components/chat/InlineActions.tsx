import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Lightbulb, Sparkles, User, X } from 'lucide-react';
import { submitFeedbackToBackend } from '@/lib/chat';
import { saveFeedback, isIncognitoMode } from '@/lib/chatStorage';

interface InlineActionsProps {
  messageContent: string;
  onAction: (query: string) => void;
}

export function InlineActions({ messageContent, onAction }: InlineActionsProps) {
  const { t } = useTranslation();

  // PROD-CQ-08 / AMK-B-003: Truncate message excerpt to <= 120 chars to prevent prompt-stuffing
  // and downstream distress classifier false-positives on follow-up quick-actions.
  const truncateExcerpt = (text: string, maxLen: number = 120): string => {
    const cleaned = text.replace(/\s+/g, ' ').trim();
    if (cleaned.length <= maxLen) return cleaned;
    return cleaned.slice(0, maxLen).trim() + '...';
  };

  const excerpt = truncateExcerpt(messageContent, 120);

  const ACTIONS = [
    { label: t('chat.tellMeMore'), icon: Sparkles, getQuery: (content: string) => t('chat.tellMeMoreQuery', { content }) },
    { label: t('chat.explainSimply'), icon: Lightbulb, getQuery: (content: string) => t('chat.explainSimplyQuery', { content }) },
    { label: t('chat.howRelates'), icon: User, getQuery: (content: string) => t('chat.howRelatesQuery', { content }) },
  ];

  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {ACTIONS.map((action) => (
        <Button
          key={action.label}
          variant="outline"
          size="sm"
          className="text-xs min-h-[44px] sm:min-h-[32px] px-3 active:scale-[0.98] transition-all duration-200 ease-out rounded-full border-muted-foreground/20"
          onClick={() => onAction(action.getQuery(excerpt))}
        >
          <action.icon className="w-3 h-3 mr-1" />
          {action.label}
        </Button>
      ))}
    </div>
  );
}

type EngagementChoice = 'yes' | 'not_quite';

interface EngagementCardProps {
  messageId: string;
  messageContent: string;
  queryText?: string;
  disabled?: boolean;
  qualityMetadata?: Record<string, unknown>;
}

// Single consolidated feedback surface — no separate hover thumbs elsewhere.
// "Yes" submits immediately; "Not quite" opens the same tag+comment picker the
// old per-message thumbs used to gate behind a duplicate control.
const FEEDBACK_TAG_KEYS = ['chat.clearAnswer', 'chat.relevantSources', 'chat.calmingTone', 'chat.insightful'] as const;
const FEEDBACK_TAG_FALLBACKS: Record<(typeof FEEDBACK_TAG_KEYS)[number], string> = {
  'chat.clearAnswer': 'Clear answer',
  'chat.relevantSources': 'Relevant sources',
  'chat.calmingTone': 'Calming tone',
  'chat.insightful': 'Insightful',
};

export function EngagementCard({ messageId, messageContent, queryText, disabled, qualityMetadata }: EngagementCardProps) {
  const { t } = useTranslation();
  const [submitted, setSubmitted] = useState<EngagementChoice | null>(null);
  const [showRefine, setShowRefine] = useState(false);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [comment, setComment] = useState('');

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((x) => x !== tag) : [...prev, tag]));
  };

  const submit = (choice: EngagementChoice, tags: string[], commentText: string) => {
    // Incognito promises nothing from the session is saved — skip both the
    // local feedback store and the backend POST (which would otherwise ship
    // the query/answer pair off-device). Still show the "thanks" state so
    // the control doesn't look broken.
    if (!isIncognitoMode()) {
      saveFeedback(messageId, {
        vote: choice === 'yes' ? 'up' : 'down',
        tags,
        comment: commentText.trim() || undefined,
        timestamp: new Date(),
      });
      void submitFeedbackToBackend({
        query: queryText ?? '',
        answer: messageContent,
        rating: choice === 'yes' ? 1 : -1,
        feedback_text: commentText.trim() || tags.join(', ') || undefined,
        metadata_json: {
          ...(qualityMetadata ?? {}),
          feedback_tags: tags,
          feedback_choice: choice,
        },
      });
    }
    setShowRefine(false);
    setSubmitted(choice);
  };

  const handleChoice = (choice: EngagementChoice) => {
    // Guards a rapid double-click during the AnimatePresence exit transition
    // (buttons stay mounted/clickable for the fade-out duration) from firing
    // submit() twice — a second feedback POST + saveFeedback for one click.
    if (submitted) return;
    if (choice === 'yes') {
      submit(choice, [], '');
    } else {
      setShowRefine(true);
    }
  };

  return (
    <div className="mt-2 text-[11px] text-muted-foreground">
      <div role="group" aria-label={t('chat.engagement.didThisHelp')} className="flex items-center gap-2">
        <AnimatePresence mode="wait" initial={false}>
          {submitted ? (
            <motion.span
              key="thanks"
              data-testid="engagement-thanks"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="inline-flex items-center gap-1.5"
            >
              <span aria-hidden>{submitted === 'yes' ? '🙏' : '💛'}</span>
              <span>{t('chat.engagement.thanks')}</span>
            </motion.span>
          ) : (
            <motion.span
              key="prompt"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="inline-flex items-center gap-2"
            >
              <span>{t('chat.engagement.didThisLand')}</span>
              <button
                type="button"
                data-testid="engagement-yes"
                disabled={disabled}
                onClick={() => handleChoice('yes')}
                className="inline-flex items-center gap-1 rounded-full border border-border/60 min-h-[44px] sm:min-h-[32px] px-3 hover:border-ojas/40 hover:text-ojas active:scale-[0.98] transition-all duration-200 ease-out disabled:opacity-40 disabled:cursor-not-allowed"
              >
                🙏 {t('chat.engagement.yes')}
              </button>
              <button
                type="button"
                data-testid="engagement-not-quite"
                disabled={disabled}
                onClick={() => handleChoice('not_quite')}
                className="inline-flex items-center gap-1 rounded-full border border-border/60 min-h-[44px] sm:min-h-[32px] px-3 hover:border-ojas/40 hover:text-ojas active:scale-[0.98] transition-all duration-200 ease-out disabled:opacity-40 disabled:cursor-not-allowed"
              >
                🤍 {t('chat.engagement.notQuite')}
              </button>
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {showRefine && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 w-full rounded-xl border border-border/50 bg-card/90 backdrop-blur-sm px-3 py-2.5 space-y-2 overflow-hidden"
          >
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium text-muted-foreground">{t('chat.engagement.whatWouldServe')}</p>
              <button
                type="button"
                onClick={() => setShowRefine(false)}
                aria-label={t('chat.closeFeedbackPanel') || 'Close feedback panel'}
                className="min-h-[44px] min-w-[44px] sm:min-h-[28px] sm:min-w-[28px] p-2 rounded flex items-center justify-center hover:bg-muted active:scale-95 transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
              >
                <X className="w-3 h-3 text-muted-foreground" />
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {FEEDBACK_TAG_KEYS.map((key) => {
                const translated = t(key);
                const tag = translated === key ? FEEDBACK_TAG_FALLBACKS[key] : translated;
                return (
                  <button
                    key={key}
                    onClick={() => toggleTag(tag)}
                    className={`min-h-[44px] sm:min-h-[28px] px-2.5 py-1 rounded-full text-[11px] border active:scale-[0.98] transition-all duration-200 ease-out ${
                      selectedTags.includes(tag)
                        ? 'border-ojas/50 bg-ojas/10 text-ojas-ink dark:text-ojas font-medium'
                        : 'border-border/60 text-muted-foreground hover:border-ojas/30'
                    }`}
                  >
                    {tag}
                  </button>
                );
              })}
            </div>
            <input
              type="text"
              placeholder={t('chat.feedbackCommentPlaceholder')}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="w-full bg-transparent border-b border-border/30 text-[12px] py-1 outline-none focus:border-ojas/40 text-foreground placeholder:text-muted-foreground/75"
            />
            <button
              type="button"
              onClick={() => submit('not_quite', selectedTags, comment)}
              className="min-h-[44px] sm:min-h-[32px] px-3 py-1.5 flex items-center text-[11px] font-medium text-ojas-ink dark:text-ojas hover:text-ojas-light active:scale-[0.98] transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 rounded-md"
            >
              {t('chat.submitFeedback')}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
