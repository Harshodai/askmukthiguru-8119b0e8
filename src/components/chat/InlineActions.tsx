import { useTranslation } from 'react-i18next';
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Button } from '@/components/ui/button';
import { Lightbulb, Sparkles, User, ThumbsUp, Meh, ThumbsDown } from 'lucide-react';
import { submitFeedbackToBackend } from '@/lib/chat';

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

type EngagementChoice = 'yes' | 'needs_work' | 'no';

interface EngagementCardProps {
  messageContent: string;
  queryText?: string;
  disabled?: boolean;
}

const CHOICE_META: { id: EngagementChoice; icon: typeof ThumbsUp; rating: number }[] = [
  { id: 'yes', icon: ThumbsUp, rating: 2 },
  { id: 'needs_work', icon: Meh, rating: 1 },
  { id: 'no', icon: ThumbsDown, rating: 0 },
];

export function EngagementCard({ messageContent, queryText, disabled }: EngagementCardProps) {
  const { t } = useTranslation();
  const [submitted, setSubmitted] = useState<EngagementChoice | null>(null);

  const handleChoice = (choice: EngagementChoice) => {
    const meta = CHOICE_META.find((c) => c.id === choice);
    if (!meta) return;
    void submitFeedbackToBackend({
      query: queryText ?? '',
      answer: messageContent,
      rating: meta.rating,
    })
      .then(() => {
        setSubmitted(choice);
      })
      .catch(() => {
        // Leave submitted as null so user can retry
      });
  };

  return (
    <div
      role="group"
      aria-label={t('chat.engagement.didThisHelp')}
      className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground"
    >
      <AnimatePresence mode="wait" initial={false}>
        {submitted ? (
          <motion.span
            key="thanks"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            className="inline-flex items-center gap-1.5"
          >
            <span aria-hidden>{submitted === 'yes' ? '🙏' : submitted === 'no' ? '💛' : '✨'}</span>
            <span>{t('chat.engagement.thanks')}</span>
          </motion.span>
        ) : (
          <motion.span
            key="prompt"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="inline-flex items-center gap-1.5"
          >
            <span>{t('chat.engagement.didThisHelp')}</span>
            {CHOICE_META.map(({ id, icon: Icon, rating }) => (
              <button
                key={id}
                type="button"
                disabled={disabled}
                onClick={() => handleChoice(id)}
                aria-label={t(`chat.engagement.${id === 'yes' ? 'yes' : id === 'needs_work' ? 'needsWork' : 'no'}`)}
                title={t(`chat.engagement.${id === 'yes' ? 'yes' : id === 'needs_work' ? 'needsWork' : 'no'}`)}
                className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
}
