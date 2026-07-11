import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Lightbulb, Sparkles, User } from 'lucide-react';

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
