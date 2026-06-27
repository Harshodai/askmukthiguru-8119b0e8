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

const ALL_COMMANDS: SlashCommand[] = [
  {
    id: 'serene',
    label: '/serene',
    hint: 'Start the 3-minute Serene Mind practice',
    icon: Flame,
    keywords: ['serene', 'mind', 'calm', 'breath'],
  },
  {
    id: 'meditate',
    label: '/meditate',
    hint: 'Open the guided meditation flow',
    icon: Sparkles,
    keywords: ['meditate', 'meditation', 'practice'],
  },
  {
    id: 'retry',
    label: '/retry',
    hint: 'Regenerate the Guru’s last answer',
    icon: RefreshCw,
    keywords: ['retry', 'regenerate', 'again'],
  },
  {
    id: 'share',
    label: '/share',
    hint: 'Share the last answer as a wisdom card',
    icon: Share2,
    keywords: ['share', 'card', 'wisdom'],
  },
  {
    id: 'clear',
    label: '/clear',
    hint: 'Start a fresh conversation',
    icon: Trash2,
    keywords: ['clear', 'new', 'reset'],
  },
  {
    id: 'lang',
    label: '/lang',
    hint: 'Open the language picker',
    icon: Languages,
    keywords: ['lang', 'language', 'hindi', 'telugu', 'malayalam'],
  },
  {
    id: 'teach',
    label: '/teach',
    hint: 'Ask the Guru to explain a concept step-by-step',
    icon: GraduationCap,
    keywords: ['teach', 'explain', 'step', 'breakdown', 'learn'],
  },
  {
    id: 'reflect',
    label: '/reflect',
    hint: 'Get a reflection question based on this conversation',
    icon: MessageSquare,
    keywords: ['reflect', 'question', 'introspect', 'ponder'],
  },
];

interface Props {
  input: string;
  open: boolean;
  onSelect: (cmd: SlashCommandId) => void;
  onClose: () => void;
}

/**
 * Lightweight slash-command palette anchored above the composer.
 * Activates whenever the input starts with `/`. Filters by typed query.
 * Keyboard: ArrowUp/Down to navigate, Enter to select, Esc to dismiss.
 */
export const SlashCommandMenu = ({ input, open, onSelect, onClose }: Props) => {
  const query = input.startsWith('/') ? input.slice(1).toLowerCase().trim() : '';
  const filtered = useMemo(() => {
    if (!query) return ALL_COMMANDS;
    return ALL_COMMANDS.filter(
      (c) =>
        c.label.toLowerCase().includes(query) ||
        c.keywords.some((k) => k.includes(query)),
    );
  }, [query]);

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
      aria-label="Slash commands"
      className="mb-2 rounded-xl border border-ojas/25 bg-card/95 backdrop-blur-md shadow-lg overflow-hidden divide-y divide-border/40"
    >
      <div className="px-3 py-1.5 text-[10px] uppercase tracking-widest text-muted-foreground/80 bg-ojas/5">
        Slash commands
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
        <span>↑↓ navigate · ↵ select · esc dismiss</span>
        <span>{filtered.length} result{filtered.length === 1 ? '' : 's'}</span>
      </div>
    </div>
  );
};
