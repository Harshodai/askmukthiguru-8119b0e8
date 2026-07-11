import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Flame, RefreshCw, Sparkles, Share2, Trash2, Languages, GraduationCap, MessageSquare } from 'lucide-react';

export type SlashCommandId =
  | 'serene'
  | 'meditate'
  | 'retry'
  | 'share'
  | 'clear'
  | 'lang'
  | 'teach'
  | 'reflect';

export interface SlashCommand {
  id: SlashCommandId;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  keywords: string[];
}

interface Props {
  input: string;
  open: boolean;
  onSelect: (cmd: SlashCommandId) => void;
  onClose: () => void;
}

export const SlashCommandMenu = ({ input, open, onSelect, onClose }: Props) => {
  const { t } = useTranslation();
  const query = input.startsWith('/') ? input.slice(1).toLowerCase().trim() : '';

  const ALL_COMMANDS: SlashCommand[] = useMemo(() => [
    {
      id: 'serene',
      label: '/serene',
      hint: t('chat.slashSereneHint'),
      icon: Flame,
      keywords: ['serene', 'mind', 'calm', 'breath'],
    },
    {
      id: 'meditate',
      label: '/meditate',
      hint: t('chat.slashMeditateHint'),
      icon: Sparkles,
      keywords: ['meditate', 'meditation', 'practice'],
    },
    {
      id: 'retry',
      label: '/retry',
      hint: t('chat.slashRetryHint'),
      icon: RefreshCw,
      keywords: ['retry', 'regenerate', 'again'],
    },
    {
      id: 'share',
      label: '/share',
      hint: t('chat.slashShareHint'),
      icon: Share2,
      keywords: ['share', 'card', 'wisdom'],
    },
    {
      id: 'clear',
      label: '/clear',
      hint: t('chat.slashClearHint'),
      icon: Trash2,
      keywords: ['clear', 'new', 'reset'],
    },
    {
      id: 'lang',
      label: '/lang',
      hint: t('chat.slashLangHint'),
      icon: Languages,
      keywords: ['lang', 'language', 'hindi', 'telugu', 'malayalam'],
    },
    {
      id: 'teach',
      label: '/teach',
      hint: t('chat.slashTeachHint'),
      icon: GraduationCap,
      keywords: ['teach', 'explain', 'step', 'breakdown', 'learn'],
    },
    {
      id: 'reflect',
      label: '/reflect',
      hint: t('chat.slashReflectHint'),
      icon: MessageSquare,
      keywords: ['reflect', 'question', 'introspect', 'ponder'],
    },
  ], [t]);

  const filtered = useMemo(() => {
    if (!query) return ALL_COMMANDS;
    return ALL_COMMANDS.filter(
      (c) =>
        c.label.toLowerCase().includes(query) ||
        c.keywords.some((k) => k.includes(query)),
    );
  }, [query, ALL_COMMANDS]);

  const [active, setActive] = useState(0);
  useEffect(() => setActive(0), [query, open]);

  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (!filtered.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setActive((a) => (a + 1) % filtered.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setActive((a) => (a - 1 + filtered.length) % filtered.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        onSelect(filtered[active].id);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        onClose();
      }
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [open, filtered, active, onSelect, onClose]);

  if (!open || filtered.length === 0) return null;

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label={t('chat.slashCommands')}
      className="mb-2 rounded-xl border border-ojas/25 bg-card/95 backdrop-blur-md shadow-lg overflow-hidden divide-y divide-border/40"
    >
      <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest text-muted-foreground/80 bg-ojas/5">
        {t('chat.slashCommands')}
      </div>
      {filtered.map((cmd, i) => {
        const Icon = cmd.icon;
        const isActive = i === active;
        return (
          <button
            key={cmd.id}
            type="button"
            role="option"
            aria-selected={isActive}
            onMouseEnter={() => setActive(i)}
            onClick={() => onSelect(cmd.id)}
            className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-colors ${
              isActive ? 'bg-ojas/10 text-foreground' : 'hover:bg-ojas/5 text-foreground/80'
            }`}
          >
            <Icon className="w-3.5 h-3.5 text-ojas shrink-0" />
            <span className="text-[13px] font-medium font-mono">{cmd.label}</span>
            <span className="text-[11px] text-muted-foreground truncate">{cmd.hint}</span>
          </button>
        );
      })}
      <div className="px-3 py-1.5 text-[10px] text-muted-foreground/70 bg-background/60 flex items-center justify-between">
        <span>{t('chat.slashKeyboardHint')}</span>
        <span>{t('chat.slashResultsCount', { count: filtered.length })}</span>
      </div>
    </div>
  );
};
