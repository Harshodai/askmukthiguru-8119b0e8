import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Plus, Flame, MessageCircle, Trash2, Edit2, Search, X,
  ChevronLeft, ChevronRight, BookOpen
} from 'lucide-react';
import { Link } from 'react-router-dom';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { MeditationStats } from './MeditationStats';
import {
  Conversation, loadConversations, deleteConversation,
  renameConversation, formatRelativeTime
} from '@/lib/chatStorage';

// ── Constants ──────────────────────────────────────────────────────────────
const SIDEBAR_PREF_KEY = 'askmukthiguru_sidebar_collapsed';
const COLLAPSED_WIDTH = 56; // px — icon rail
const EXPANDED_WIDTH = 280; // px — full sidebar

// ── Props ─────────────────────────────────────────────────────────────────
interface DesktopSidebarProps {
  onNewConversation: () => void;
  onOpenSereneMind: () => void;
  onSelectConversation?: (conversation: Conversation) => void;
  currentConversationId?: string;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

// ── Sidebar ────────────────────────────────────────────────────────────────
export const DesktopSidebar = ({
  onNewConversation,
  onOpenSereneMind,
  onSelectConversation,
  currentConversationId,
  isCollapsed,
  onToggleCollapse,
}: DesktopSidebarProps) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');

  const reload = useCallback(() => setConversations(loadConversations()), []);

  useEffect(() => {
    reload();
    // Listen for localStorage changes from any component (new message, new conversation, delete)
    window.addEventListener('storage', reload);
    // Custom event fired by ChatInterface when conversation state changes
    window.addEventListener('conversation:updated', reload);
    return () => {
      window.removeEventListener('storage', reload);
      window.removeEventListener('conversation:updated', reload);
    };
  }, [reload]);

  // Keyboard shortcut: Cmd+B / Ctrl+B
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        onToggleCollapse();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onToggleCollapse]);

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(id);
    reload();
  };

  const handleRename = (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditValue(conv.preview || 'New conversation');
  };

  const commitRename = (id: string) => {
    if (editValue.trim()) {
      renameConversation(id, editValue.trim());
      reload();
    }
    setEditingId(null);
  };

  const filtered = search
    ? conversations.filter(c =>
        c.preview.toLowerCase().includes(search.toLowerCase())
      )
    : conversations;

  const grouped = filtered.reduce((acc, conv) => {
    const label = formatRelativeTime(conv.updatedAt);
    if (!acc[label]) acc[label] = [];
    acc[label].push(conv);
    return acc;
  }, {} as Record<string, Conversation[]>);

  return (
    <motion.aside
      className="hidden sm:flex flex-col h-full border-r border-border/40 bg-card/40 backdrop-blur-sm overflow-hidden flex-shrink-0"
      animate={{ width: isCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
    >
      {isCollapsed ? (
        /* ── Icon Rail ──────────────────────────────────────────────── */
        <div className="flex flex-col items-center gap-2 py-3 flex-1">
          {/* Brand mark */}
          <div className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-ojas/20 mb-1">
            <img src={gurusPhoto} alt="Gurus" className="w-full h-full object-cover" />
          </div>

          {/* New Chat */}
          <button
            onClick={onNewConversation}
            title="New conversation (⌘B to expand)"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Plus className="w-4 h-4" />
          </button>

          {/* Serene Mind */}
          <button
            onClick={onOpenSereneMind}
            title="Serene Mind Meditation"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-prana/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Flame className="w-4 h-4" />
          </button>

          {/* Recent chats indicator — stacked dots */}
          {conversations.length > 0 && (
            <div className="flex flex-col items-center gap-0.5 mt-1">
              {conversations.slice(0, 4).map((c, i) => (
                <button
                  key={c.id}
                  onClick={() => { onSelectConversation?.(c); }}
                  title={c.preview || 'Conversation'}
                  className={`w-1.5 h-1.5 rounded-full transition-all ${
                    c.id === currentConversationId ? 'bg-ojas scale-150' : 'bg-muted-foreground/30 hover:bg-ojas/50'
                  }`}
                />
              ))}
              {conversations.length > 4 && (
                <span className="text-[9px] text-muted-foreground/40 mt-0.5">+{conversations.length - 4}</span>
              )}
            </div>
          )}

          <div className="flex-1" />

          {/* Expand toggle */}
          <button
            onClick={onToggleCollapse}
            title="Expand sidebar (⌘B)"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-all mb-2"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        /* ── Full Sidebar ───────────────────────────────────────────── */
        <div className="flex flex-col h-full min-w-0">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-3 py-3 border-b border-border/30">
            <div className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-ojas/20 flex-shrink-0">
              <img src={gurusPhoto} alt="Gurus" className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">AskMukthiGuru</p>
              <p className="text-[10px] text-muted-foreground">Your Spiritual Companion</p>
            </div>
            {/* Collapse toggle */}
            <button
              onClick={onToggleCollapse}
              title="Collapse sidebar (⌘B)"
              className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-muted text-muted-foreground transition-all flex-shrink-0"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Action buttons */}
          <div className="px-2 pt-2 pb-1 space-y-1">
            <button
              onClick={onNewConversation}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm font-medium bg-ojas/10 hover:bg-ojas/15 text-ojas border border-ojas/20 hover:border-ojas/35 transition-all"
            >
              <Plus className="w-3.5 h-3.5 flex-shrink-0" />
              New Conversation
            </button>
            <button
              onClick={onOpenSereneMind}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-prana/10 hover:text-ojas border border-transparent hover:border-prana/20 transition-all"
            >
              <Flame className="w-3.5 h-3.5 flex-shrink-0" />
              Serene Mind
            </button>
          </div>

          {/* Search */}
          <div className="px-2 pb-1">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-muted/50 border border-border/40">
              <Search className="w-3 h-3 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                placeholder="Search conversations…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground/60 outline-none"
              />
              {search && (
                <button onClick={() => setSearch('')} className="p-0.5 rounded hover:bg-muted">
                  <X className="w-3 h-3 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>

          {/* Meditation stats */}
          <div className="px-2 pb-1">
            <MeditationStats compact />
          </div>

          {/* Conversation history */}
          <div className="flex-1 overflow-y-auto scrollbar-spiritual px-1 pb-2">
            {Object.keys(grouped).length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <BookOpen className="w-6 h-6 text-muted-foreground/30" />
                <p className="text-xs text-muted-foreground/50 text-center">
                  {search ? 'No results' : 'No conversations yet.\nStart a new one above.'}
                </p>
              </div>
            ) : (
              Object.entries(grouped).map(([label, convs]) => (
                <div key={label} className="mb-2">
                  <p className="px-2 py-1 text-[10px] uppercase tracking-widest text-muted-foreground/50 font-semibold select-none">
                    {label}
                  </p>
                  <div className="space-y-0.5">
                    {convs.map(conv => (
                      <div
                        key={conv.id}
                        onClick={() => onSelectConversation?.(conv)}
                        className={`group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                          conv.id === currentConversationId
                            ? 'bg-ojas/12 text-ojas'
                            : 'hover:bg-muted/60 text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        <MessageCircle className="w-3.5 h-3.5 flex-shrink-0 opacity-60" />
                        <div className="flex-1 min-w-0">
                          {editingId === conv.id ? (
                            <input
                              autoFocus
                              value={editValue}
                              onChange={e => setEditValue(e.target.value)}
                              onBlur={() => commitRename(conv.id)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') commitRename(conv.id);
                                if (e.key === 'Escape') setEditingId(null);
                              }}
                              onClick={e => e.stopPropagation()}
                              className="w-full bg-transparent text-xs outline-none border-b border-ojas/40 py-0.5"
                            />
                          ) : (
                            <p className="text-xs truncate">
                              {conv.preview || 'New conversation'}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={e => handleRename(conv, e)}
                            className="p-1 rounded hover:bg-muted/80 text-muted-foreground hover:text-foreground"
                            title="Rename"
                          >
                            <Edit2 className="w-2.5 h-2.5" />
                          </button>
                          <button
                            onClick={e => handleDelete(conv.id, e)}
                            className="p-1 rounded hover:bg-destructive/15 text-muted-foreground hover:text-destructive"
                            title="Delete"
                          >
                            <Trash2 className="w-2.5 h-2.5" />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Footer nav */}
          <div className="border-t border-border/30 px-2 py-2">
            <Link
              to="/"
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all"
            >
              Back to Home
            </Link>
          </div>
        </div>
      )}
    </motion.aside>
  );
};

// ── Hook for consuming collapsed state ────────────────────────────────────
export const useSidebarCollapsed = () => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(SIDEBAR_PREF_KEY);
      return saved !== null ? JSON.parse(saved) : true; // default: collapsed
    } catch { return true; }
  });

  const toggle = useCallback(() => {
    setIsCollapsed(v => {
      const next = !v;
      try { localStorage.setItem(SIDEBAR_PREF_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  return { isCollapsed, toggle };
};
