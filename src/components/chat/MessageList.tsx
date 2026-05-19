import React from 'react';
import { Message } from '@/lib/chatStorage';
import { ChatMessage } from './ChatMessage';

// ── Date separator helpers ──────────────────────────────────────────
const isSameDay = (a: Date, b: Date): boolean =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

const formatDateLabel = (date: Date): string => {
  const now = new Date();
  if (isSameDay(date, now)) return 'Today';
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (isSameDay(date, yesterday)) return 'Yesterday';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

export const MessageList = React.memo(({
  messages,
  streamingId,
  streamingContent,
  onRegenerate,
  onEditUserMessage,
}: {
  messages: Message[];
  streamingId?: string;
  streamingContent?: string;
  onRegenerate?: () => void;
  onEditUserMessage?: (message: Message) => void;
}) => {
  // Find the ID of the last guru message for the regenerate button
  let lastGuruId: string | undefined;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'guru') { lastGuruId = messages[i].id; break; }
  }

  const groups: { label: string; messages: Message[] }[] = [];
  let currentLabel = '';
  messages.forEach((msg) => {
    const ts = msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp);
    const label = formatDateLabel(ts);
    if (label !== currentLabel) {
      currentLabel = label;
      groups.push({ label, messages: [msg] });
    } else {
      groups[groups.length - 1].messages.push(msg);
    }
  });


  return (
    <>
      {groups.map((group) => (
        <React.Fragment key={group.label}>
          {/* Date separator */}
          <div className="flex items-center gap-4 py-3">
            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
            <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50 select-none px-2">
              {group.label}
            </span>
            <div className="flex-1 h-px bg-gradient-to-r from-transparent via-border/40 to-transparent" />
          </div>
          {group.messages.map((message, index) => {
            let queryText = '';
            if (message.role === 'guru') {
              const flatIndex = messages.findIndex((m) => m.id === message.id);
              for (let i = flatIndex - 1; i >= 0; i--) {
                if (messages[i].role === 'user') {
                  queryText = messages[i].content;
                  break;
                }
              }
            }
            return (
              <ChatMessage 
                key={message.id} 
                message={message.id === streamingId && streamingContent !== undefined ? { ...message, content: streamingContent } : message} 
                queryText={queryText}
                index={index}
                isStreaming={message.id === streamingId && (streamingContent ? streamingContent.length > 0 : message.content.length > 0)}
                isLastGuru={message.id === lastGuruId && !streamingId}
                onRegenerate={message.id === lastGuruId && !streamingId ? onRegenerate : undefined}
                onEditUserMessage={message.role === 'user' ? onEditUserMessage : undefined}
              />
            );
          })}
        </React.Fragment>
      ))}
    </>
  );
});
MessageList.displayName = 'MessageList';
