/**
 * ConversationSourcesPanel — right-side "Sources" sheet + full modal view.
 *
 *  • De-duplicates by URL across every guru turn.
 *  • Optional filter by a specific message (from inline citation click).
 *  • Copy-URL per source + Copy-all-as-markdown for the whole conversation.
 *  • "View all in modal" opens a larger dialog for deep review.
 *  • Full keyboard + screen-reader support: labelled list, focusable rows,
 *    autofocus on first item when opened, visible focus rings, AA contrast.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from '@/components/ui/sheet';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Library, ExternalLink, Youtube, Globe, Copy, Check, Filter, Maximize2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

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
  /** When set, only sources cited in this message are shown. */
  filterMessageId?: string | null;
  onClearFilter?: () => void;
}

const getDomain = (url: string): string => {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
};

const getYouTubeId = (url: string): string | null => {
  try {
    if (url.includes('youtu.be/')) return url.split('youtu.be/')[1]?.split('?')[0] ?? null;
    if (url.includes('v=')) return url.split('v=')[1]?.split('&')[0] ?? null;
    return null;
  } catch { return null; }
};

function aggregate(messages: MinimalMessage[]): AggregatedSource[] {
  const map = new Map<string, AggregatedSource>();
  let answerNumber = 0;
  for (const m of messages) {
    if (m.role !== 'assistant' && m.role !== 'guru') continue;
    answerNumber += 1;
    for (const url of m.citations ?? []) {
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
}

function SourceRow({
  source,
  index,
  onJump,
  onCopy,
  copiedUrl,
  autoFocus,
}: {
  source: AggregatedSource;
  index: number;
  onJump: (id: string) => void;
  onCopy: (url: string) => void;
  copiedUrl: string | null;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    if (autoFocus) {
      const btn = ref.current?.querySelector<HTMLElement>('a, button');
      btn?.focus();
    }
  }, [autoFocus]);

  return (
    <li
      ref={ref}
      className="group rounded-xl border border-border/60 bg-card/40 hover:border-ojas/40 hover:bg-card/70 focus-within:border-ojas focus-within:ring-2 focus-within:ring-ojas/40 transition-colors p-3"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="flex-shrink-0 w-6 h-6 rounded-full bg-ojas/10 text-ojas text-[11px] font-semibold flex items-center justify-center tabular-nums"
        >
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[13px] font-medium text-foreground hover:text-ojas focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas rounded max-w-full"
              aria-label={t('chat.openSourceAria', { number: index + 1, domain: source.domain })}
            >
              {source.ytId ? (
                <Youtube className="w-3.5 h-3.5 text-ojas shrink-0" aria-hidden />
              ) : (
                <Globe className="w-3.5 h-3.5 text-ojas shrink-0" aria-hidden />
              )}
              <span className="truncate underline-offset-2 group-hover:underline">{source.domain}</span>
              <ExternalLink className="w-3 h-3 opacity-70 shrink-0" aria-hidden />
            </a>
            <button
              type="button"
              onClick={() => onCopy(source.url)}
              className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] text-muted-foreground hover:text-foreground hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
              aria-label={t('chat.copyUrlAria', { number: index + 1 })}
            >
              {copiedUrl === source.url ? (
                <><Check className="w-3 h-3" aria-hidden /> {t('common.copied')}</>
              ) : (
                <><Copy className="w-3 h-3" aria-hidden /> {t('common.copy')}</>
              )}
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5 truncate" title={source.url}>
            {source.url}
          </p>

          {source.ytId && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block mt-2 rounded-lg overflow-hidden border border-border/50 aspect-video bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
              aria-label={t('chat.openSourceAria', { number: index + 1, domain: 'YouTube' })}
              tabIndex={-1}
            >
              <img
                src={`https://img.youtube.com/vi/${source.ytId}/mqdefault.jpg`}
                alt=""
                loading="lazy"
                className="w-full h-full object-cover"
              />
            </a>
          )}

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground font-medium">
              {t('chat.references')}
            </span>
            {source.usedIn.map((p) => (
              <button
                key={p.messageId}
                type="button"
                onClick={() => onJump(p.messageId)}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-ojas/10 text-ojas hover:bg-ojas/20 border border-ojas/20 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
                aria-label={t('chat.scrollToAnswerAria', { number: p.answerNumber })}
              >
                {t('chat.answerHash', { number: p.answerNumber })}
              </button>
            ))}
          </div>
        </div>
      </div>
    </li>
  );
}

export function ConversationSourcesPanel({
  isOpen,
  onClose,
  messages,
  onJumpToMessage,
  filterMessageId,
  onClearFilter,
}: Props) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const allSources = useMemo(() => aggregate(messages), [messages]);
  const filtered = useMemo(() => {
    if (!filterMessageId) return allSources;
    return allSources.filter((s) => s.usedIn.some((u) => u.messageId === filterMessageId));
  }, [allSources, filterMessageId]);

  const totalCites = filtered.reduce((n, s) => n + s.usedIn.length, 0);

  const copyOne = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(url);
      window.setTimeout(() => setCopiedUrl((c) => (c === url ? null : c)), 1500);
    } catch {
      toast({ title: t('chat.couldNotCopy'), variant: 'destructive' });
    }
  };

  const copyAll = async (source: AggregatedSource[]) => {
    if (source.length === 0) return;
    const md = source
      .map((s, i) => `${i + 1}. [${s.domain}](${s.url})`)
      .join('\n');
    try {
      await navigator.clipboard.writeText(md);
      toast({ title: t('common.copied') });
    } catch {
      toast({ title: t('chat.couldNotCopy'), variant: 'destructive' });
    }
  };

  const handleJump = (messageId: string) => {
    onClose();
    setModalOpen(false);
    window.setTimeout(() => onJumpToMessage(messageId), 220);
  };

  const HeaderMeta = (
    <div className="flex items-center justify-between gap-3 flex-wrap">
      <p className="text-caption text-muted-foreground">
        {filtered.length === 0
          ? t('chat.noSources')
          : t('chat.sourceCount', { count: filtered.length, citationCount: totalCites })}
      </p>
      <div className="flex items-center gap-1.5">
        {filterMessageId && (
          <button
            type="button"
            onClick={() => onClearFilter?.()}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-ojas hover:text-ojas/80 border border-ojas/30 rounded-md px-2 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
          >
            <Filter className="w-3 h-3" aria-hidden />
            {t('chat.showingOneAnswer')}
          </button>
        )}
        <button
          type="button"
          onClick={() => copyAll(filtered)}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-foreground hover:text-ojas border border-border rounded-md px-2 py-1 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
          aria-label={t('chat.copyAll')}
        >
          <Copy className="w-3 h-3" aria-hidden />
          {t('chat.copyAll')}
        </button>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-foreground hover:text-ojas border border-border rounded-md px-2 py-1 disabled:opacity-40 focus:outline-none focus-visible:ring-2 focus-visible:ring-ojas"
          aria-label={t('chat.fullConversationSources')}
        >
          <Maximize2 className="w-3 h-3" aria-hidden />
          {t('chat.fullView')}
        </button>
      </div>
    </div>
  );

  const List = ({ inModal }: { inModal?: boolean }) => (
    <>
      {filtered.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground" role="status">
          <Library className="w-10 h-10 mx-auto mb-3 opacity-40" aria-hidden />
          <p className="text-body-sm">{t('chat.sourcesWillAppear')}</p>
        </div>
      ) : (
        <ul
          role="list"
          aria-label={t('chat.sourceCount', { count: filtered.length, citationCount: totalCites })}
          className="space-y-3"
        >
          {filtered.map((s, idx) => (
            <SourceRow
              key={s.url}
              source={s}
              index={idx}
              onJump={handleJump}
              onCopy={copyOne}
              copiedUrl={copiedUrl}
              autoFocus={!inModal && idx === 0 && isOpen}
            />
          ))}
        </ul>
      )}
    </>
  );

  return (
    <>
      <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <SheetContent
          className="w-full sm:max-w-md p-0 flex flex-col"
          aria-label={t('chat.sources')}
        >
          <SheetHeader className="px-5 pt-5 pb-3 border-b border-border/60 space-y-2">
            <SheetTitle className="flex items-center gap-2 text-h3">
              <Library className="w-5 h-5 text-ojas" aria-hidden />
              {t('chat.sources')}
            </SheetTitle>
            <SheetDescription className="sr-only">
              {t('chat.sourcesWillAppear')}
            </SheetDescription>
            {HeaderMeta}
          </SheetHeader>
          <ScrollArea className="flex-1 px-5 py-4">
            <List />
          </ScrollArea>
        </SheetContent>
      </Sheet>

      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-2xl w-[92vw] p-0 overflow-hidden">
          <DialogHeader className="px-6 pt-5 pb-3 border-b border-border/60 space-y-2">
            <DialogTitle className="flex items-center gap-2">
              <Library className="w-5 h-5 text-ojas" aria-hidden />
              {t('chat.fullConversationSources')}
            </DialogTitle>
            <DialogDescription className="sr-only">
              {t('chat.sourcesWillAppear')}
            </DialogDescription>
            {HeaderMeta}
          </DialogHeader>
          <ScrollArea className="max-h-[70vh] px-6 py-4">
            <List inModal />
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </>
  );
}
