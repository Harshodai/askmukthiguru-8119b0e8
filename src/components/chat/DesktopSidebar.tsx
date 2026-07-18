import { useTranslation } from 'react-i18next';
import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Plus, Flame, MessageCircle, Trash2, Edit2, Search, X,
  ChevronLeft, ChevronRight, BookOpen, Brain, Compass, Lock, HardDrive
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { MeditationStats } from './MeditationStats';
import { UserMenu } from '@/components/common/UserMenu';
import {
  Conversation, loadConversations, deleteConversation,
  renameConversation
} from '@/lib/chatStorage';
import { groupConversations } from '@/lib/conversationGrouping';
import { memoryApi } from '@/lib/memoryApi';

const SIDEBAR_PREF_KEY = 'askmukthiguru_sidebar_collapsed';
const COLLAPSED_WIDTH = 56;
const EXPANDED_WIDTH = 280;

interface DesktopSidebarProps {
  onNewConversation: () => void;
  onOpenSereneMind: () => void;
  onSelectConversation?: (conversation: Conversation) => void;
  currentConversationId?: string;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onDeleteConversation?: (id: string) => void;
}

export const DesktopSidebar = ({
  onNewConversation,
  onOpenSereneMind,
  onSelectConversation,
  currentConversationId,
  isCollapsed,
  onToggleCollapse,
  onDeleteConversation,
}: DesktopSidebarProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [search, setSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [memoryCount, setMemoryCount] = useState<number>(0);

  useEffect(() => {
    memoryApi.list(1, 1).then(res => {
      if (res && typeof res.total === 'number') setMemoryCount(res.total);
    }).catch(() => {});
  }, []);

  const reload = useCallback(async () => {
    setConversations(await loadConversations());
  }, []);

  useEffect(() => {
    reload();
    window.addEventListener('storage', reload);
    window.addEventListener('conversation:updated', reload);
    return () => {
      window.removeEventListener('storage', reload);
      window.removeEventListener('conversation:updated', reload);
    };
  }, [reload]);

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

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteConversation(id);
    reload();
  };

  const handleRename = (conv: Conversation, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(conv.id);
    setEditValue(conv.preview || t('desktopSidebar.newConversation'));
  };

  const commitRename = async (id: string) => {
    if (editValue.trim()) {
      await renameConversation(id, editValue.trim());
      reload();
    }
    setEditingId(null);
  };

  const filtered = search
    ? conversations.filter(c =>
        c.preview.toLowerCase().includes(search.toLowerCase())
      )
    : conversations;

  const groups = groupConversations(filtered);

  return (
    <motion.aside
      className="hidden sm:flex flex-col h-full border-r border-hairline bg-card/40 backdrop-blur-sm overflow-hidden flex-shrink-0 safe-top"
      animate={{ width: isCollapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
    >
      {isCollapsed ? (
        <div className="flex flex-col items-center gap-2 py-3 flex-1">
          <div className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-ojas/20 mb-1">
            <img src={gurusPhoto} alt={t('desktopSidebar.gurusAlt')} className="w-full h-full object-cover" />
          </div>

          <button
            onClick={onNewConversation}
            title={t('desktopSidebar.newConvTooltip')}
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Plus className="w-4 h-4" />
          </button>

          <button
            onClick={onOpenSereneMind}
            title={t('desktopSidebar.sereneMindTooltip')}
            data-tour="meditation"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-prana/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Flame className="w-4 h-4" />
          </button>

          <button
            onClick={() => navigate('/practices')}
            title={t('nav.practices')}
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Compass className="w-4 h-4" />
          </button>

          <button
            onClick={() => navigate('/notebooks')}
            title={t('nav.notebooks')}
            data-tour="notebook"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <BookOpen className="w-4 h-4" />
          </button>

          <button
            onClick={() => navigate('/knowledge-graph')}
            title={t('nav.knowledgeGraph')}
            data-tour="knowledge-graph"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Brain className="w-4 h-4" />
          </button>

          <button
            onClick={() => navigate('/second-brain')}
            title={t('nav.secondBrain', 'Your Second Brain')}
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-all"
          >
            <Lock className="w-4 h-4" />
          </button>

          {conversations.length > 0 && (
            <div className="flex flex-col items-center gap-0.5 mt-1">
              {conversations.slice(0, 4).map((c, i) => (
                <button
                  key={c.id}
                  onClick={() => { onSelectConversation?.(c); }}
                  title={c.preview || t('desktopSidebar.conversation')}
                  className={`w-1.5 h-1.5 rounded-full transition-all ${
                    c.id === currentConversationId ? 'bg-ojas scale-150' : 'bg-muted-foreground/30 hover:bg-ojas/50'
                  }`}
                />
              ))}
              {conversations.length > 4 && (
                <span className="text-[9px] text-muted-foreground/70 mt-0.5">+{conversations.length - 4}</span>
              )}
            </div>
          )}

          <div className="flex-1" />

          <button
            onClick={onToggleCollapse}
            title={t('desktopSidebar.expandTooltip')}
            data-testid="sidebar-toggle"
            className="w-9 h-9 rounded-xl flex items-center justify-center hover:bg-muted text-muted-foreground hover:text-foreground transition-all mb-2"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      ) : (
        <div className="flex flex-col h-full min-w-0 relative">
          <div className="flex items-center gap-2.5 px-3 py-3 border-b border-hairline">
            <div className="w-8 h-8 rounded-full overflow-hidden ring-1 ring-ojas/20 flex-shrink-0">
              <img src={gurusPhoto} alt={t('desktopSidebar.gurusAlt')} className="w-full h-full object-cover" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">{t('nav.appName') === 'nav.appName' ? 'AskMukthiGuru' : t('nav.appName')}</p>
              <p className="text-[10px] text-muted-foreground">{t('desktopSidebar.tagline')}</p>
            </div>
            <button
              onClick={onToggleCollapse}
              title={t('desktopSidebar.collapseTooltip')}
              data-testid="sidebar-toggle"
              className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-muted text-muted-foreground transition-all flex-shrink-0"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="px-2 pt-2 pb-1 space-y-1">
            <button
              onClick={onNewConversation}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm font-medium bg-ojas/[0.08] hover:bg-ojas/[0.14] text-ojas border border-hairline hover:border-ojas/25 transition-all"
            >
              <Plus className="w-3.5 h-3.5 flex-shrink-0" />
              {t('desktopSidebar.newConversation') === 'desktopSidebar.newConversation' ? 'New Conversation' : t('desktopSidebar.newConversation')}
            </button>
            <button
              onClick={onOpenSereneMind}
              data-tour="meditation"
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-prana/10 hover:text-ojas border border-transparent hover:border-prana/20 transition-all"
            >
              <Flame className="w-3.5 h-3.5 flex-shrink-0" />
              {t('meditation.sereneMind')}
            </button>
            <button
              onClick={() => navigate('/practices')}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-ojas/10 hover:text-ojas border border-transparent hover:border-ojas/20 transition-all"
            >
              <Compass className="w-3.5 h-3.5 flex-shrink-0" />
              {t('nav.practices')}
            </button>
            <button
              onClick={() => navigate('/notebooks')}
              data-tour="notebook"
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-ojas/10 hover:text-ojas border border-transparent hover:border-ojas/20 transition-all"
            >
              <BookOpen className="w-3.5 h-3.5 flex-shrink-0" />
              {t('nav.notebooks')}
            </button>
            <button
              onClick={() => navigate('/knowledge-graph')}
              data-tour="knowledge-graph"
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-ojas/10 hover:text-ojas border border-transparent hover:border-ojas/20 transition-all"
            >
              <Brain className="w-3.5 h-3.5 flex-shrink-0" />
              {t('nav.knowledgeGraph')}
            </button>
            <button
              onClick={() => navigate('/second-brain')}
              className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl text-sm text-muted-foreground hover:bg-ojas/10 hover:text-ojas border border-transparent hover:border-ojas/20 transition-all"
            >
              <HardDrive className="w-3.5 h-3.5 flex-shrink-0" />
              {t('nav.secondBrain', 'Second Brain')}
            </button>
          </div>

          <div className="px-2 pb-1">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-muted/50 border border-border/40">
              <Search className="w-3 h-3 text-muted-foreground flex-shrink-0" />
              <input
                type="text"
                placeholder={t('desktopSidebar.searchPlaceholder')}
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

          <div className="px-2 pb-1">
            <MeditationStats compact />
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-spiritual px-1 pb-2">
            {groups.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <BookOpen className="w-6 h-6 text-muted-foreground/60" />
                <p className="text-xs text-muted-foreground/75 text-center">
                  {search ? t('desktopSidebar.noResults') : t('desktopSidebar.noConversations')}
                </p>
              </div>
            ) : (
              groups.map(group => (
                <div key={group.label} className="mb-2">
                  <p className="px-2 py-1 text-[10px] uppercase tracking-[0.15em] text-muted-foreground/60 select-none">
                    {group.label}
                  </p>
                  <div className="space-y-0.5">
                    {group.conversations.map(conv => (
                      <div
                        key={conv.id}
                        data-testid="conversation-item"
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
                              {conv.preview || t('desktopSidebar.newConversation')}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={e => handleRename(conv, e)}
                            className="p-1 rounded hover:bg-muted/80 text-muted-foreground hover:text-foreground"
                            title={t('desktopSidebar.rename')}
                            aria-label={t('desktopSidebar.renameConv') === 'desktopSidebar.renameConv' ? 'Rename conversation' : t('desktopSidebar.renameConv')}
                          >
                            <Edit2 className="w-2.5 h-2.5" />
                          </button>
                          <button
                            onClick={e => {
                              e.stopPropagation();
                              setDeleteConfirmId(conv.id);
                            }}
                            className="p-1 rounded hover:bg-destructive/15 text-muted-foreground hover:text-destructive"
                            title={t('common.delete')}
                            aria-label={t('desktopSidebar.deleteConv') === 'desktopSidebar.deleteConv' ? 'Delete conversation' : t('desktopSidebar.deleteConv')}
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

          <div className="border-t border-border/30 px-2 py-1.5 flex items-center gap-1.5">
            <UserMenu />
            <button
              className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-all text-[11px]"
            >
              <Brain className="w-3 h-3" />
              <span>{t('desktopSidebar.memories', { count: memoryCount })}</span>
            </button>
          </div>

          {deleteConfirmId && (
            <div className="absolute inset-0 bg-background/80 backdrop-blur-sm z-50 flex flex-col items-center justify-center p-4 text-center">
              <div className="bg-card border border-border/50 rounded-2xl p-4 shadow-xl max-w-[240px] space-y-3">
                <p className="text-xs font-semibold text-foreground">{t('desktopSidebar.deleteTitle') === 'desktopSidebar.deleteTitle' ? 'Delete conversation?' : t('desktopSidebar.deleteTitle')}</p>
                <p className="text-[10px] text-muted-foreground">{t('desktopSidebar.deleteWarning')}</p>
                <div className="flex items-center gap-2 justify-center">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteConfirmId(null);
                    }}
                    data-testid="delete-cancel"
                    className="px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-muted hover:bg-muted/80 text-muted-foreground transition-colors"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      if (onDeleteConversation) {
                        onDeleteConversation(deleteConfirmId);
                      } else {
                        await deleteConversation(deleteConfirmId);
                        reload();
                      }
                      setDeleteConfirmId(null);
                    }}
                    data-testid="delete-confirm"
                    className="px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors shadow-sm"
                  >
                    {t('common.delete')}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </motion.aside>
  );
};

export const useSidebarCollapsed = () => {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(SIDEBAR_PREF_KEY);
      return saved !== null ? JSON.parse(saved) : false;
    } catch { return true; }
  });

  const toggle = useCallback(() => {
    setIsCollapsed(v => {
      const next = !v;
      try {
        localStorage.setItem(SIDEBAR_PREF_KEY, JSON.stringify(next));
      } catch {
      }
      return next;
    });
  }, []);

  return { isCollapsed, toggle };
};
