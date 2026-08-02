import React from 'react';
import { Message } from '@/lib/chatStorage';
import { ChatMessage } from './ChatMessage';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from 'react-i18next';

/**
 * Native CSS virtualization.
 *
 * The previous implementation attached a ResizeObserver *and* an
 * IntersectionObserver to every message — 2N observers plus N pieces of React
 * state, all of which re-rendered the list on scroll. `content-visibility:auto`
 * hands the exact same work (skip layout/paint for off-screen subtrees) to the
 * compositor for free, and `contain-intrinsic-size: auto <h>` makes the browser
 * remember the last rendered height so the scrollbar never jumps.
 *
 * The streaming message opts out: it must stay painted so autoscroll and the
 * thinking indicator keep working.
 */
const VirtualMessageWrapper = ({
  id,
  children,
  defaultHeight = 150,
  alwaysVisible = false,
}: {
  id: string;
  children: React.ReactNode;
  defaultHeight?: number;
  alwaysVisible?: boolean;
}) => (
  <div
    data-message-id={id}
    style={
      alwaysVisible
        ? undefined
        : {
            contentVisibility: 'auto',
            containIntrinsicSize: `auto ${defaultHeight}px`,
          }
    }
  >
    {children}
  </div>
);

// ── Date separator helpers ──────────────────────────────────────────
const isSameDay = (a: Date, b: Date): boolean =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

const formatDateLabel = (
  date: Date,
  t: (key: string) => string,
  locale: string,
): string => {
  const now = new Date();
  if (isSameDay(date, now)) return t('common.today');
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (isSameDay(date, yesterday)) return t('common.yesterday');
  return date.toLocaleDateString(locale, { month: 'short', day: 'numeric', year: 'numeric' });
};


export const MessageList = React.memo(({
  messages,
  streamingId,
  streamingContent,
  onRegenerate,
  onEditUserMessage,
  onSubmitEdit,
  onAction,
  onCitationClick,
  loading = false,
}: {
  messages: Message[];
  streamingId?: string;
  streamingContent?: string;
  onRegenerate?: () => void;
  onEditUserMessage?: (message: Message) => void;
  onSubmitEdit?: (messageId: string, newContent: string) => void;
  scrollContainerRef?: React.RefObject<HTMLDivElement>;
  onAction?: (query: string) => void;
  onCitationClick?: (messageId: string, citationIndex: number) => void;
  /** E6.3: when true and there are no messages yet, render shadcn skeletons. */
  loading?: boolean;
}) => {
  const { t, i18n } = useTranslation();

  // E6.3: skeleton placeholder during an async initial load with no messages yet.
  if (loading && messages.length === 0) {
    return (
      <div className="space-y-4 py-2" data-testid="message-list-skeleton">
        <div className="flex justify-end">
          <Skeleton className="h-10 w-[55%] rounded-2xl" />
        </div>
        <div className="flex justify-start gap-2.5">
          <Skeleton className="h-7 w-7 rounded-full flex-shrink-0" />
          <div className="space-y-2 flex-1 max-w-[80%]">
            <Skeleton className="h-3 w-[90%]" />
            <Skeleton className="h-3 w-[75%]" />
            <Skeleton className="h-3 w-[60%]" />
          </div>
        </div>
        <div className="flex justify-start gap-2.5">
          <Skeleton className="h-7 w-7 rounded-full flex-shrink-0" />
          <Skeleton className="h-3 w-[50%]" />
        </div>
      </div>
    );
  }

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
    <div className="space-y-3 sm:space-y-4 scrollbar-thin scrollbar-thumb-muted-foreground/20">
      {groups.map((group) => (
        <React.Fragment key={group.label}>
          {/* Date separator — Claude.ai style */}
          <div className="flex items-center gap-3 my-2">
            <hr className="flex-1 border-border/30" />
            <span className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground select-none">
              {group.label}
            </span>
            <hr className="flex-1 border-border/30" />
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
            const isStreamingMsg = message.id === streamingId;
            const isEmptyStreaming = isStreamingMsg && !(streamingContent && streamingContent.length > 0) && message.content.length === 0;
            if (isEmptyStreaming) {
              return <div key={message.id} data-message-id={message.id} className="h-0" />;
            }
            return (
              <VirtualMessageWrapper
                key={message.id}
                id={message.id}
                defaultHeight={isStreamingMsg ? 0 : message.role === 'user' ? 40 : 80}
                alwaysVisible={isStreamingMsg}
              >
                {/* During the entire streaming period (including before the first token arrives)
                    mark the streaming message as active so ChatMessage can render a thinking indicator. */}
                <ChatMessage
                  message={isStreamingMsg && streamingContent !== undefined ? { ...message, content: streamingContent } : message}
                  queryText={queryText}
                  index={index}
                  isStreaming={isStreamingMsg}
                  isLastGuru={message.id === lastGuruId && !streamingId}
                  onRegenerate={message.id === lastGuruId && !streamingId ? onRegenerate : undefined}
                  onEditUserMessage={message.role === 'user' ? onEditUserMessage : undefined}
                  onSubmitEdit={message.role === 'user' ? onSubmitEdit : undefined}
                  onAction={message.role === 'guru' && message.id === lastGuruId && !streamingId ? onAction : undefined}
                  onCitationClick={message.role === 'guru' ? onCitationClick : undefined}

                />
              </VirtualMessageWrapper>
            );
          })}
        </React.Fragment>
      ))}
    </div>
  );
});
MessageList.displayName = 'MessageList';
