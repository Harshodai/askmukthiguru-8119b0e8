import React, { useState, useEffect, useRef } from 'react';
import { Message } from '@/lib/chatStorage';
import { ChatMessage } from './ChatMessage';

// ── VirtualMessageWrapper for list virtualization (dynamic heights) ──────────────────
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
}) => {
  const [isVisible, setIsVisible] = useState(true);
  const [height, setHeight] = useState(defaultHeight);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (alwaysVisible) {
      setIsVisible(true);
      return;
    }

    const el = containerRef.current;
    if (!el) return;

    // Measure the actual height dynamically as the item loads or changes size
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const measuredHeight = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height;
        if (measuredHeight > 0) {
          setHeight(measuredHeight);
        }
      }
    });
    resizeObserver.observe(el);

    // Unmount content when far outside the viewport to keep DOM size small and re-renders fast
    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsVisible(entry.isIntersecting);
      },
      {
        rootMargin: '1000px 0px 1000px 0px', // large buffer to ensure smooth scrolling
      }
    );
    observer.observe(el);

    return () => {
      resizeObserver.disconnect();
      observer.disconnect();
    };
  }, [alwaysVisible]);

  return (
    <div
      ref={containerRef}
      style={{
        minHeight: `${height}px`,
        contentVisibility: 'auto',
        containIntrinsicSize: `auto ${height}px`,
      }}
    >
      {alwaysVisible || isVisible ? children : <div style={{ height: `${height}px` }} />}
    </div>
  );
};

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
  onSubmitEdit,
}: {
  messages: Message[];
  streamingId?: string;
  streamingContent?: string;
  onRegenerate?: () => void;
  onEditUserMessage?: (message: Message) => void;
  onSubmitEdit?: (messageId: string, newContent: string) => void;
  scrollContainerRef?: React.RefObject<HTMLDivElement>;
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
            <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/75 select-none px-2">
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
            const isStreamingMsg = message.id === streamingId;
            const isEmptyStreaming = isStreamingMsg && !(streamingContent && streamingContent.length > 0) && message.content.length === 0;
            return (
              <VirtualMessageWrapper
                key={message.id}
                id={message.id}
                defaultHeight={isEmptyStreaming ? 24 : (message.role === 'user' ? 60 : 140)}
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
                />
              </VirtualMessageWrapper>
            );
          })}
        </React.Fragment>
      ))}
    </>
  );
});
MessageList.displayName = 'MessageList';
