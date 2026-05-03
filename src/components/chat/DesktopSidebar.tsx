import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Flame, MessageCircle, Trash2, ChevronLeft, ChevronRight, Home } from 'lucide-react';
import { Link } from 'react-router-dom';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { 
  Conversation, 
  loadConversations, 
  deleteConversation,
  formatRelativeTime 
} from '@/lib/chatStorage';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

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

  const SidebarButton = ({ 
    onClick, icon: Icon, label, variant = 'default', title 
  }: { 
    onClick: () => void; 
    icon: React.ElementType; 
    label: string; 
    variant?: 'ojas' | 'prana' | 'default';
    title: string;
  }) => {
    const colors = {
      ojas: 'bg-ojas/10 border-ojas/20 hover:border-ojas/40 hover:bg-ojas/15',
      prana: 'bg-prana/10 border-prana/20 hover:border-prana/40 hover:bg-prana/15',
      default: 'bg-muted/30 border-border hover:bg-muted/50',
    };
    const iconColors = {
      ojas: 'bg-ojas/20 group-hover:bg-ojas/30',
      prana: 'bg-prana/20 group-hover:bg-prana/30',
      default: 'bg-muted group-hover:bg-muted/80',
    };

    const button = (
      <button
        onClick={onClick}
        className={`w-full flex items-center gap-3 p-2.5 rounded-xl border transition-all group ${colors[variant]} ${
          isCollapsed ? 'justify-center' : ''
        }`}
        title={title}
      >
        <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors flex-shrink-0 ${iconColors[variant]}`}>
          <Icon className="w-4 h-4 text-ojas" />
        </div>
        <AnimatePresence>
          {!isCollapsed && (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 'auto' }}
              exit={{ opacity: 0, width: 0 }}
              className="text-left overflow-hidden"
            >
              <p className="font-medium text-foreground text-sm whitespace-nowrap">{label}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </button>
    );

    if (isCollapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent side="right" sideOffset={12}>
            <p>{label}</p>
          </TooltipContent>
        </Tooltip>
      );
    }

    return button;
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 64 : 280 }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      style={{ willChange: 'width' }}
      className="hidden sm:flex flex-col h-full bg-card/90 backdrop-blur-lg border-r border-border/60 relative z-20"
    >
      {/* Collapse Toggle — larger hit target */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onToggleCollapse}
            className="absolute -right-4 top-20 z-30 w-8 h-8 rounded-full bg-card border border-border/80 shadow-lg flex items-center justify-center hover:bg-muted hover:scale-105 transition-all"
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronLeft className="w-4 h-4 text-muted-foreground" />
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p>{isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}</p>
        </TooltipContent>
      </Tooltip>

      {/* Header */}
      <div className={`p-4 border-b border-border/40 ${isCollapsed ? 'px-3' : ''}`}>
        <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}`}>
          <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-ojas/30 shadow-md flex-shrink-0 dark:shadow-[0_0_12px_hsl(43_96%_56%/0.15)]">
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
        <div className={`p-3 space-y-2 ${isCollapsed ? 'px-2' : ''}`}>
          {/* Action Buttons */}
          <SidebarButton
            onClick={onNewConversation}
            icon={Plus}
            label="New Conversation"
            variant="ojas"
            title="New Conversation"
          />
          <SidebarButton
            onClick={onOpenSereneMind}
            icon={Flame}
            label="Serene Mind"
            variant="prana"
            title="Serene Mind Meditation"
          />

          {/* Divider */}
          <div className="h-px bg-border/40 my-2" />

          {/* Conversation History */}
          {Object.keys(groupedConversations).length > 0 && (
            <div>
              <AnimatePresence>
                {!isCollapsed && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2 font-medium px-1"
                  >
                    History
                  </motion.p>
                )}
              </AnimatePresence>
              <div className="space-y-0.5">
                {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                  <div key={timeGroup}>
                    <AnimatePresence>
                      {!isCollapsed && (
                        <motion.p
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="text-[10px] text-muted-foreground/70 mb-1 px-1 mt-2"
                        >
                          {timeGroup}
                        </motion.p>
                      )}
                    </AnimatePresence>
                    <div className="space-y-0.5">
                      {convs.map((conv) => {
                        const isActive = conv.id === currentConversationId;
                        const item = (
                          <motion.div
                            key={conv.id}
                            className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-all group ${
                              isActive
                                ? 'bg-ojas/12 border border-ojas/25 shadow-sm'
                                : 'hover:bg-muted/40 border border-transparent'
                            } ${isCollapsed ? 'justify-center' : ''}`}
                            onClick={() => onSelectConversation(conv)}
                            title={conv.preview || 'New conversation'}
                          >
                            <MessageCircle className={`w-4 h-4 flex-shrink-0 ${
                              isActive ? 'text-ojas' : 'text-muted-foreground'
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
                        );

                        if (isCollapsed) {
                          return (
                            <Tooltip key={conv.id}>
                              <TooltipTrigger asChild>{item}</TooltipTrigger>
                              <TooltipContent side="right" sideOffset={12}>
                                <p className="max-w-[200px] truncate">{conv.preview || 'New conversation'}</p>
                              </TooltipContent>
                            </Tooltip>
                          );
                        }
                        return item;
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Footer Navigation */}
      <div className={`p-3 border-t border-border/40 ${isCollapsed ? 'px-2' : ''}`}>
        {isCollapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                to="/"
                className="flex items-center justify-center p-2 rounded-lg hover:bg-muted/50 transition-colors"
                title="Back to Home"
              >
                <Home className="w-4 h-4 text-muted-foreground" />
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={12}>
              <p>Back to Home</p>
            </TooltipContent>
          </Tooltip>
        ) : (
          <Link
            to="/"
            className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 transition-colors"
            title="Back to Home"
          >
            <Home className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-foreground">Back to Home</span>
          </Link>
        )}
      </div>
    </motion.aside>
  );
};
