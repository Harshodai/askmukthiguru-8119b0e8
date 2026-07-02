/**
 * ConversationSourcesPanel — ChatGPT-style right-side "Sources" panel that
 * aggregates every citation across all guru turns in the current conversation.
 *
 *  • De-duplicates by URL.
 *  • Shows a "Used in" pointer chip per source (answer #3, #7…). Clicking a
 *    chip closes the panel, scrolls to that message, and briefly highlights it.
 *  • Renders a YouTube thumbnail when applicable; otherwise a compact link card.
 */
import { useMemo } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Library, ExternalLink, Youtube, Globe } from 'lucide-react';

interface MinimalMessage {
  id: string;
  role: 'user' | 'assistant' | string;
  citations?: string[];
}

interface AggregatedSource {
  url: string;
  domain: string;
  ytId: string | null;
  usedIn: Array<{ messageId: string; answerNumber: number }>;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  messages: MinimalMessage[];
  onJumpToMessage: (messageId: string) => void;
}

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const getYouTubeId = (url: string): string | null => {
  try {
    if (url.includes('youtu.be/')) return url.split('youtu.be/')[1]?.split('?')[0] ?? null;
    if (url.includes('v=')) return url.split('v=')[1]?.split('&')[0] ?? null;
    return null;
  } catch {
    return null;
  }
};

export function ConversationSourcesPanel({ isOpen, onClose, messages, onJumpToMessage }: Props) {
  const sources = useMemo<AggregatedSource[]>(() => {
    const map = new Map<string, AggregatedSource>();
    let answerNumber = 0;
    for (const m of messages) {
      if (m.role !== 'assistant') continue;
      answerNumber += 1;
      const cites = m.citations ?? [];
      for (const url of cites) {
        if (!url) continue;
        const existing = map.get(url);
        if (existing) {
          if (!existing.usedIn.some((p) => p.messageId === m.id)) {
            existing.usedIn.push({ messageId: m.id, answerNumber });
          }
        } else {
          map.set(url, {
            url,
            domain: getDomain(url),
            ytId: getYouTubeId(url),
            usedIn: [{ messageId: m.id, answerNumber }],
          });
        }
      }
    }
    return Array.from(map.values());
  }, [messages]);

  const handleJump = (messageId: string) => {
    onClose();
    // Wait for the sheet close animation to finish before scrolling.
    window.setTimeout(() => onJumpToMessage(messageId), 220);
  };

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-md p-0 flex flex-col">
        <SheetHeader className="px-5 pt-5 pb-3 border-b border-border/60">
          <SheetTitle className="flex items-center gap-2 text-h3">
            <Library className="w-5 h-5 text-ojas" />
            Sources in this conversation
          </SheetTitle>
          <p className="text-caption mt-1">
            {sources.length === 0
              ? 'No sources cited yet in this conversation.'
              : `${sources.length} unique ${sources.length === 1 ? 'source' : 'sources'} across ${
                  sources.reduce((n, s) => n + s.usedIn.length, 0)
                } citation${sources.reduce((n, s) => n + s.usedIn.length, 0) === 1 ? '' : 's'}.`}
          </p>
        </SheetHeader>

        <ScrollArea className="flex-1 px-5 py-4">
          {sources.length === 0 ? (
            <div className="text-center py-16 text-muted-foreground">
              <Library className="w-10 h-10 mx-auto mb-3 text-muted-foreground/30" />
              <p className="text-body-sm">Sources will appear here as the Guru cites teachings.</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {sources.map((s, idx) => (
                <li
                  key={s.url}
                  className="group rounded-xl border border-border/60 bg-card/40 hover:border-ojas/40 hover:bg-card/70 transition-colors p-3"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full bg-ojas/10 text-ojas text-[11px] font-semibold flex items-center justify-center tabular-nums">
                      {idx + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-foreground hover:text-ojas transition-colors group-hover:underline underline-offset-2 max-w-full"
                      >
                        {s.ytId ? (
                          <Youtube className="w-3.5 h-3.5 text-ojas shrink-0" />
                        ) : (
                          <Globe className="w-3.5 h-3.5 text-ojas shrink-0" />
                        )}
                        <span className="truncate">{s.domain}</span>
                        <ExternalLink className="w-3 h-3 opacity-60 shrink-0" />
                      </a>
                      <p className="text-[11px] text-muted-foreground mt-0.5 truncate" title={s.url}>
                        {s.url}
                      </p>

                      {s.ytId && (
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block mt-2 rounded-lg overflow-hidden border border-border/50 aspect-video bg-muted"
                        >
                          <img
                            src={`https://img.youtube.com/vi/${s.ytId}/mqdefault.jpg`}
                            alt=""
                            loading="lazy"
                            className="w-full h-full object-cover"
                          />
                        </a>
                      )}

                      {/* Pointers — which answers used this source */}
                      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                        <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-medium">
                          Used in
                        </span>
                        {s.usedIn.map((p) => (
                          <button
                            key={p.messageId}
                            type="button"
                            onClick={() => handleJump(p.messageId)}
                            className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-ojas/10 text-ojas hover:bg-ojas/20 border border-ojas/20 transition-colors"
                            aria-label={`Jump to answer ${p.answerNumber}`}
                          >
                            answer #{p.answerNumber}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
