import React from 'react';
import { Button } from '@/components/ui/button';
import { Lightbulb, Sparkles, User } from 'lucide-react';

interface InlineActionsProps {
  messageContent: string;
  onAction: (query: string) => void;
}

const ACTIONS = [
  { label: "Tell me more", icon: Sparkles, getQuery: (content: string) => `Tell me more about this: ${content.slice(0, 100)}` },
  { label: "Explain simply", icon: Lightbulb, getQuery: (content: string) => `Explain this in simpler terms: ${content.slice(0, 100)}` },
  { label: "How relates to me", icon: User, getQuery: (content: string) => `How does this relate to my personal journey? ${content.slice(0, 100)}` },
];

export function InlineActions({ messageContent, onAction }: InlineActionsProps) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
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
