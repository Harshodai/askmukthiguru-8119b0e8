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
          className="text-xs h-7 px-2 rounded-full border-muted-foreground/20"
          onClick={() => onAction(action.getQuery(messageContent))}
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

export function EngagementCard({ messageId, messageContent, queryText, disabled }: EngagementCardProps) {
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
        comment: commentText.trim() || tags.join(', ') || undefined,
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
                className="inline-flex items-center gap-1 rounded-full border border-border/60 px-2.5 py-1 hover:border-ojas/40 hover:text-ojas transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                🙏 {t('chat.engagement.yes')}
              </button>
              <button
                type="button"
                data-testid="engagement-not-quite"
                disabled={disabled}
                onClick={() => handleChoice('not_quite')}
                className="inline-flex items-center gap-1 rounded-full border border-border/60 px-2.5 py-1 hover:border-ojas/40 hover:text-ojas transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
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
              <button onClick={() => setShowRefine(false)} aria-label={t('chat.closeFeedbackPanel')} className="p-0.5 rounded hover:bg-muted">
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
                    className={`px-2.5 py-1 rounded-full text-[11px] border transition-all ${
                      selectedTags.includes(tag)
                        ? 'border-ojas/50 bg-ojas/10 text-ojas font-medium'
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
              onClick={() => submit('not_quite', selectedTags, comment)}
              className="text-[11px] font-medium text-ojas hover:text-ojas-light transition-colors"
            >
              {t('chat.submitFeedback')}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
