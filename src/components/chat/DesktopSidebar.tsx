import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Flame, MessageCircle, Trash2, ChevronLeft, ChevronRight, Home } from 'lucide-react';
import { Link } from 'react-router-dom';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { MeditationStats } from './MeditationStats';
import { 
  Conversation, 
  loadConversations, 
  deleteConversation,
  formatRelativeTime 
} from '@/lib/chatStorage';
import { ScrollArea } from '@/components/ui/scroll-area';

interface DesktopSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onNewConversation: () => void;
  onOpenSereneMind: () => void;
  onSelectConversation: (conversation: Conversation) => void;
  currentConversationId?: string;
  refreshTrigger?: number;
}

export const DesktopSidebar = ({
  isCollapsed,
  onToggleCollapse,
  onNewConversation,
  onOpenSereneMind,
  onSelectConversation,
  currentConversationId,
  refreshTrigger,
}: DesktopSidebarProps) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    setConversations(loadConversations());
  }, [refreshTrigger]);

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(id);
    setConversations(loadConversations());
  };

  // Group conversations by relative time
  const groupedConversations = conversations.reduce((groups, conv) => {
    const timeGroup = formatRelativeTime(conv.updatedAt);
    if (!groups[timeGroup]) {
      groups[timeGroup] = [];
    }
    groups[timeGroup].push(conv);
    return groups;
  }, {} as Record<string, Conversation[]>);

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 64 : 280 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="hidden lg:flex flex-col h-full bg-card/80 backdrop-blur-md border-r border-border relative z-20"
    >
      {/* Collapse Toggle */}
      <button
        onClick={onToggleCollapse}
        className="absolute -right-3 top-20 z-30 w-6 h-6 rounded-full bg-card border border-border shadow-md flex items-center justify-center hover:bg-muted transition-colors"
        aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {isCollapsed ? (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
        ) : (
          <ChevronLeft className="w-3.5 h-3.5 text-muted-foreground" />
        )}
      </button>

      {/* Header */}
      <div className={`p-4 border-b border-border ${isCollapsed ? 'px-3' : ''}`}>
        <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}`}>
          <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-ojas/30 shadow-md flex-shrink-0">
            <img
              src={gurusPhoto}
              alt="Sri Preethaji & Sri Krishnaji"
              className="w-full h-full object-cover"
            />
          </div>
          <AnimatePresence>
            {!isCollapsed && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                className="overflow-hidden"
              >
                <h2 className="font-semibold text-foreground text-sm whitespace-nowrap">AskMukthiGuru</h2>
                <p className="text-xs text-muted-foreground whitespace-nowrap">Your Spiritual Companion</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Scrollable Content */}
      <ScrollArea className="flex-1">
        <div className={`p-3 space-y-3 ${isCollapsed ? 'px-2' : ''}`}>
          {/* New Conversation */}
          <button
            onClick={onNewConversation}
            className={`w-full flex items-center gap-3 p-3 rounded-xl bg-ojas/10 border border-ojas/20 hover:border-ojas/40 hover:bg-ojas/15 transition-all group ${
              isCollapsed ? 'justify-center' : ''
            }`}
            title="New Conversation"
          >
            <div className="w-8 h-8 rounded-full bg-ojas/20 flex items-center justify-center group-hover:bg-ojas/30 transition-colors flex-shrink-0">
              <Plus className="w-4 h-4 text-ojas" />
            </div>
            <AnimatePresence>
              {!isCollapsed && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  className="text-left overflow-hidden"
                >
                  <p className="font-medium text-foreground text-sm whitespace-nowrap">New Conversation</p>
                </motion.div>
              )}
            </AnimatePresence>
          </button>

          {/* Serene Mind Quick Access */}
          <button
            onClick={onOpenSereneMind}
            className={`w-full flex items-center gap-3 p-3 rounded-xl bg-prana/10 border border-prana/20 hover:border-prana/40 hover:bg-prana/15 transition-all group ${
              isCollapsed ? 'justify-center' : ''
            }`}
            title="Serene Mind Meditation"
          >
            <div className="w-8 h-8 rounded-full bg-prana/20 flex items-center justify-center group-hover:bg-prana/30 transition-colors flex-shrink-0">
              <Flame className="w-4 h-4 text-ojas" />
            </div>
            <AnimatePresence>
              {!isCollapsed && (
                <motion.div
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  className="text-left overflow-hidden"
                >
                  <p className="font-medium text-foreground text-sm whitespace-nowrap">Serene Mind</p>
                </motion.div>
              )}
            </AnimatePresence>
          </button>

          {/* Meditation Stats - Only show when expanded */}
          <AnimatePresence>
            {!isCollapsed && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <MeditationStats />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Conversation History */}
          {Object.keys(groupedConversations).length > 0 && (
            <div className="pt-2">
              <AnimatePresence>
                {!isCollapsed && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-xs text-muted-foreground uppercase tracking-wider mb-2 font-medium px-1"
                  >
                    History
                  </motion.p>
                )}
              </AnimatePresence>
              <div className="space-y-1">
                {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                  <div key={timeGroup}>
                    <AnimatePresence>
                      {!isCollapsed && (
                        <motion.p
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="text-xs text-muted-foreground mb-1 px-1"
                        >
                          {timeGroup}
                        </motion.p>
                      )}
                    </AnimatePresence>
                    <div className="space-y-1">
                      {convs.map((conv) => (
                        <motion.div
                          key={conv.id}
                          className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-all group ${
                            conv.id === currentConversationId
                              ? 'bg-ojas/15 border border-ojas/30'
                              : 'hover:bg-muted/50 border border-transparent'
                          } ${isCollapsed ? 'justify-center' : ''}`}
                          onClick={() => onSelectConversation(conv)}
                          title={conv.preview || 'New conversation'}
                        >
                          <MessageCircle className={`w-4 h-4 text-muted-foreground flex-shrink-0 ${
                            conv.id === currentConversationId ? 'text-ojas' : ''
                          }`} />
                          <AnimatePresence>
                            {!isCollapsed && (
                              <motion.div
                                initial={{ opacity: 0, width: 0 }}
                                animate={{ opacity: 1, width: 'auto' }}
                                exit={{ opacity: 0, width: 0 }}
                                className="flex-1 min-w-0 overflow-hidden"
                              >
                                <p className="text-sm text-foreground truncate">
                                  {conv.preview || 'New conversation'}
                                </p>
                              </motion.div>
                            )}
                          </AnimatePresence>
                          <AnimatePresence>
                            {!isCollapsed && (
                              <motion.button
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 0 }}
                                whileHover={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                onClick={(e) => handleDeleteConversation(conv.id, e)}
                                className="p-1 rounded-full opacity-0 group-hover:opacity-100 hover:bg-destructive/20 transition-all flex-shrink-0"
                              >
                                <Trash2 className="w-3 h-3 text-destructive" />
                              </motion.button>
                            )}
                          </AnimatePresence>
                        </motion.div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Footer Navigation */}
      <div className={`p-3 border-t border-border ${isCollapsed ? 'px-2' : ''}`}>
        <Link
          to="/"
          className={`flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 transition-colors ${
            isCollapsed ? 'justify-center' : ''
          }`}
          title="Back to Home"
        >
          <Home className="w-4 h-4 text-muted-foreground" />
          <AnimatePresence>
            {!isCollapsed && (
              <motion.span
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                className="text-sm text-foreground whitespace-nowrap overflow-hidden"
              >
                Back to Home
              </motion.span>
            )}
          </AnimatePresence>
        </Link>
      </div>
    </motion.aside>
  );
};
