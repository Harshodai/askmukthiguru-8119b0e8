import { useTranslation } from 'react-i18next';
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X, Plus, Flame, MessageCircle, Trash2, EyeOff,
  BookOpen, Brain, Compass, HardDrive, MessageSquare, LayoutGrid,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { buildChatOwnedPath } from '@/lib/workspaceNavigation';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { MeditationStats } from './MeditationStats';
import {
  Conversation,
  loadConversations,
  deleteConversation,
  formatRelativeTime
} from '@/lib/chatStorage';

interface MobileConversationSheetProps {
  isOpen: boolean;
  onClose: () => void;
  onNewConversation: () => void;
  onNewIncognitoConversation?: () => void;
  onOpenSereneMind: () => void;
  onSelectConversation?: (conversation: Conversation) => void;
  currentConversationId?: string;
}

export const MobileConversationSheet = ({
  isOpen,
  onClose,
  onNewConversation,
  onNewIncognitoConversation,
  onOpenSereneMind,
  onSelectConversation,
  currentConversationId,
}: MobileConversationSheetProps) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeTab, setActiveTab] = useState<'chat' | 'explore'>('chat');

  useEffect(() => {
    if (isOpen) {
      loadConversations().then(setConversations);
      // Always open on Chat tab
      setActiveTab('chat');
    }
  }, [isOpen]);

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteConversation(id);
    setConversations(await loadConversations());
  };

  const handleSelectConversation = (conv: Conversation) => {
    if (onSelectConversation) {
      onSelectConversation(conv);
    }
    onClose();
  };

  const groupedConversations = conversations.reduce((groups, conv) => {
    const timeGroup = formatRelativeTime(conv.updatedAt);
    if (!groups[timeGroup]) {
      groups[timeGroup] = [];
    }
    groups[timeGroup].push(conv);
    return groups;
  }, {} as Record<string, Conversation[]>);

  // All explore destinations — same as desktop sidebar
  const exploreItems = [
    {
      id: 'serene',
      icon: Flame,
      label: t('meditation.sereneMind'),
      description: t('chat.breathworkDesc'),
      onClick: () => { onOpenSereneMind(); onClose(); },
      color: 'ojas',
      tour: 'mobile-serene',
    },
    {
      id: 'practices',
      icon: Compass,
      label: t('nav.practices'),
      description: t('nav.practicesDesc', 'Guided spiritual practices'),
      onClick: () => { navigate(buildChatOwnedPath('/practices', { conversationId: currentConversationId })); onClose(); },
      color: 'ojas',
      tour: 'mobile-practices',
    },
    {
      id: 'notebooks',
      icon: BookOpen,
      label: t('nav.notebooks'),
      description: t('nav.notebooksDesc', 'Your study notes & highlights'),
      onClick: () => { navigate(buildChatOwnedPath('/notebooks', { conversationId: currentConversationId })); onClose(); },
      color: 'ojas',
      tour: 'mobile-notebook',
    },
    {
      id: 'kg',
      icon: Brain,
      label: t('nav.knowledgeGraph', 'Wisdom Map'),
      description: t('nav.knowledgeGraphDesc', 'Explore teachings as a living map'),
      onClick: () => { navigate(buildChatOwnedPath('/knowledge-graph', { conversationId: currentConversationId })); onClose(); },
      color: 'ojas',
      tour: 'mobile-kg',
    },
    {
      id: 'second-brain',
      icon: HardDrive,
      label: t('nav.secondBrain', 'My Reflections'),
      description: t('nav.secondBrainDesc', 'Your personal spiritual memory vault'),
      onClick: () => { navigate(buildChatOwnedPath('/second-brain', { conversationId: currentConversationId })); onClose(); },
      color: 'ojas',
      tour: 'mobile-reflections',
    },
    {
      id: 'incognito',
      icon: EyeOff,
      label: t('chat.incognito'),
      description: t('chat.incognitoDescription'),
      onClick: () => { onNewIncognitoConversation?.(); onClose(); },
      color: 'amber',
      tour: 'mobile-incognito',
    },
  ] as const;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 z-50 bg-foreground/20 backdrop-blur-sm"
          />

          {/* Bottom Sheet */}
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed bottom-0 left-0 right-0 z-50 bg-card border-t border-border rounded-t-3xl max-h-[88vh] flex flex-col overflow-hidden shadow-xl"
          >
            {/* Drag handle */}
            <div className="flex justify-center pt-3 pb-1 flex-shrink-0">
              <div className="w-10 h-1 rounded-full bg-border" />
            </div>

            {/* Header */}
            <div className="px-5 py-3 border-b border-border flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-ojas/30 shadow-md flex-shrink-0">
                    <img
                      src={gurusPhoto}
                      alt="Sri Preethaji & Sri Krishnaji"
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div>
                    <h2 className="font-semibold text-foreground text-sm">{t('nav.appName')}</h2>
                    <p className="text-xs text-muted-foreground">{t('chat.yourSpiritualCompanion')}</p>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  aria-label="Close menu"
                  className="p-2 rounded-full hover:bg-muted transition-colors"
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>

              {/* Tab switcher */}
              <div className="flex gap-1 mt-3 p-1 bg-muted/60 rounded-xl">
                <button
                  onClick={() => setActiveTab('chat')}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'chat'
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  {t('chat.tabChat', 'Chat')}
                </button>
                <button
                  onClick={() => setActiveTab('explore')}
                  data-tour="mobile-explore-tab"
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    activeTab === 'explore'
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <LayoutGrid className="w-3.5 h-3.5" />
                  {t('chat.tabExplore', 'Explore')}
                </button>
              </div>
            </div>

            {/* Tab content — scrollable */}
            <div className="flex-1 overflow-y-auto scrollbar-spiritual pb-[env(safe-area-inset-bottom,16px)]">
              <AnimatePresence mode="wait">
                {activeTab === 'chat' ? (
                  <motion.div
                    key="chat-tab"
                    initial={{ opacity: 0, x: -12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: -12 }}
                    transition={{ duration: 0.18 }}
                    className="p-4 space-y-3"
                  >
                    {/* Meditation stats strip */}
                    <MeditationStats />

                    {/* New Conversation */}
                    <button
                      onClick={() => { onNewConversation(); onClose(); }}
                      className="w-full flex items-center gap-3 p-4 rounded-xl bg-ojas/10 border border-ojas/20 hover:border-ojas/40 hover:bg-ojas/15 transition-all group"
                    >
                      <div className="w-9 h-9 rounded-full bg-ojas/20 flex items-center justify-center group-hover:bg-ojas/30 transition-colors flex-shrink-0">
                        <Plus className="w-4 h-4 text-ojas" />
                      </div>
                      <div className="text-left">
                        <p className="font-medium text-foreground text-sm">{t('chat.newConversation')}</p>
                        <p className="text-xs text-muted-foreground">{t('chat.startFreshWithGurus')}</p>
                      </div>
                    </button>

                    {/* Conversation History */}
                    {Object.keys(groupedConversations).length > 0 ? (
                      <div>
                        <p className="text-xs text-muted-foreground uppercase tracking-wider mb-2 font-medium px-1">
                          {t('chat.recentConversations')}
                        </p>
                        <div className="space-y-4">
                          {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                            <div key={timeGroup}>
                              <p className="text-xs text-muted-foreground/70 mb-1.5 px-1">{timeGroup}</p>
                              <div className="space-y-1.5">
                                {convs.map((conv) => (
                                  <motion.div
                                    key={conv.id}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    role="button"
                                    tabIndex={0}
                                    aria-label={`Open conversation: ${conv.preview || 'New conversation'}`}
                                    className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas ${
                                      conv.id === currentConversationId
                                        ? 'bg-ojas/15 border border-ojas/30'
                                        : 'bg-muted/30 hover:bg-muted/50 border border-transparent'
                                    }`}
                                    onClick={() => handleSelectConversation(conv)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault();
                                        handleSelectConversation(conv);
                                      }
                                    }}
                                  >
                                    <MessageCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                                    <div className="flex-1 min-w-0">
                                      <p className="text-sm text-foreground truncate">
                                        {conv.preview || t('chat.newConversation')}
                                      </p>
                                      <p className="text-xs text-muted-foreground">
                                        {t('chat.messagesCount', { count: conv.messageCount })}
                                      </p>
                                    </div>
                                    <button
                                      onClick={(e) => handleDeleteConversation(conv.id, e)}
                                      aria-label="Delete conversation"
                                      className="p-1.5 rounded-full opacity-0 group-hover:opacity-60 hover:!opacity-100 active:opacity-100 hover:bg-destructive/20 transition-all"
                                    >
                                      <Trash2 className="w-3.5 h-3.5 text-destructive" />
                                    </button>
                                  </motion.div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-8 gap-2 text-center">
                        <MessageCircle className="w-8 h-8 text-muted-foreground/30" />
                        <p className="text-sm text-muted-foreground/60">{t('desktopSidebar.noConversations')}</p>
                      </div>
                    )}
                  </motion.div>
                ) : (
                  <motion.div
                    key="explore-tab"
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 12 }}
                    transition={{ duration: 0.18 }}
                    className="p-4"
                  >
                    <p className="text-xs text-muted-foreground/60 uppercase tracking-widest font-semibold mb-3 px-1">
                      {t('desktopSidebar.explore', 'Explore')}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {exploreItems.map(({ id, icon: Icon, label, description, onClick, color, tour }) => (
                        <button
                          key={id}
                          onClick={onClick}
                          data-tour={tour}
                          className={`flex flex-col items-start gap-2 p-3.5 rounded-2xl border transition-all text-left ${
                            color === 'amber'
                              ? 'bg-amber-950/10 border-amber-600/20 hover:bg-amber-950/20 hover:border-amber-600/40'
                              : 'bg-muted/40 border-border/40 hover:bg-ojas/10 hover:border-ojas/30'
                          }`}
                        >
                          <div className={`w-8 h-8 rounded-xl flex items-center justify-center ${
                            color === 'amber' ? 'bg-amber-950/20' : 'bg-ojas/15'
                          }`}>
                            <Icon className={`w-4 h-4 ${color === 'amber' ? 'text-amber-600' : 'text-ojas'}`} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-foreground leading-tight">{label}</p>
                            <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug line-clamp-2">{description}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
