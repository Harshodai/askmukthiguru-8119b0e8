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

  return (
    <motion.aside
      initial={false}
      animate={{ width: isCollapsed ? 64 : 280 }}
      transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
      className="hidden sm:flex flex-col h-full bg-card/95 backdrop-blur-xl border-r border-border/50 relative z-20 overflow-hidden"
    >
      {/* Collapse Toggle */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onToggleCollapse}
            className="absolute -right-3.5 top-20 z-30 w-7 h-7 rounded-full bg-card border border-border/80 shadow-md flex items-center justify-center hover:bg-muted hover:scale-110 transition-all active:scale-95"
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <motion.div
              animate={{ rotate: isCollapsed ? 0 : 180 }}
              transition={{ duration: 0.3 }}
            >
              <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
            </motion.div>
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          <p>{isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}</p>
        </TooltipContent>
      </Tooltip>

      {/* Header */}
      <div className="p-3 border-b border-border/30">
        <div className={`flex items-center gap-3 ${isCollapsed ? 'justify-center' : ''}`}>
          <div className="w-10 h-10 rounded-full overflow-hidden ring-2 ring-ojas/20 shadow-sm flex-shrink-0">
            <img
              src={gurusPhoto}
              alt="Sri Preethaji & Sri Krishnaji"
              className="w-full h-full object-cover"
            />
          </div>
          {!isCollapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, delay: 0.1 }}
              className="min-w-0"
            >
              <h2 className="font-semibold text-foreground text-sm truncate">AskMukthiGuru</h2>
              <p className="text-[11px] text-muted-foreground truncate">Your Spiritual Companion</p>
            </motion.div>
          )}
        </div>
      </div>

      {/* Scrollable Content */}
      <ScrollArea className="flex-1">
        <div className={`p-2.5 space-y-1.5 ${isCollapsed ? 'px-1.5' : ''}`}>
          {/* Action Buttons */}
          <SidebarActionButton
            onClick={onNewConversation}
            icon={Plus}
            label="New Conversation"
            isCollapsed={isCollapsed}
            variant="ojas"
          />
          <SidebarActionButton
            onClick={onOpenSereneMind}
            icon={Flame}
            label="Serene Mind"
            isCollapsed={isCollapsed}
            variant="prana"
          />

          {/* Divider */}
          <div className="h-px bg-border/30 my-2" />

          {/* Conversation History */}
          {Object.keys(groupedConversations).length > 0 && (
            <div>
              {!isCollapsed && (
                <p className="text-[10px] text-muted-foreground/70 uppercase tracking-wider mb-2 font-medium px-2">
                  History
                </p>
              )}
              <div className="space-y-0.5">
                {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                  <div key={timeGroup}>
                    {!isCollapsed && (
                      <p className="text-[10px] text-muted-foreground/50 mb-1 px-2 mt-2 first:mt-0">
                        {timeGroup}
                      </p>
                    )}
                    <div className="space-y-0.5">
                      {convs.map((conv) => {
                        const isActive = conv.id === currentConversationId;
                        const item = (
                          <div
                            key={conv.id}
                            className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-all duration-200 ${
                              isActive
                                ? 'bg-ojas/10 border border-ojas/20 shadow-sm'
                                : 'hover:bg-muted/40 border border-transparent'
                            } ${isCollapsed ? 'justify-center' : ''}`}
                            onClick={() => onSelectConversation(conv)}
                            title={conv.preview || 'New conversation'}
                          >
                            <MessageCircle className={`w-4 h-4 flex-shrink-0 transition-colors ${
                              isActive ? 'text-ojas' : 'text-muted-foreground'
                            }`} />
                            {!isCollapsed && (
                              <>
                                <p className="flex-1 text-sm text-foreground truncate min-w-0">
                                  {conv.preview || 'New conversation'}
                                </p>
                                <button
                                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                                  className="p-1 rounded-full opacity-0 group-hover:opacity-100 hover:bg-destructive/20 transition-all flex-shrink-0"
                                >
                                  <Trash2 className="w-3 h-3 text-destructive" />
                                </button>
                              </>
                            )}
                          </div>
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
                        return <div key={conv.id}>{item}</div>;
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
      <div className={`p-2.5 border-t border-border/30 ${isCollapsed ? 'px-1.5' : ''}`}>
        {isCollapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link
                to="/"
                className="flex items-center justify-center p-2 rounded-lg hover:bg-muted/50 transition-colors"
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
          >
            <Home className="w-4 h-4 text-muted-foreground" />
            <span className="text-sm text-foreground">Back to Home</span>
          </Link>
        )}
      </div>
    </motion.aside>
  );
};

// ── Sidebar action button component ─────────────────────────────────
const SidebarActionButton = ({
  onClick,
  icon: Icon,
  label,
  isCollapsed,
  variant,
}: {
  onClick: () => void;
  icon: React.ElementType;
  label: string;
  isCollapsed: boolean;
  variant: 'ojas' | 'prana';
}) => {
  const colors = {
    ojas: 'bg-ojas/8 border-ojas/15 hover:border-ojas/30 hover:bg-ojas/12',
    prana: 'bg-prana/8 border-prana/15 hover:border-prana/30 hover:bg-prana/12',
  };
  const iconColors = {
    ojas: 'text-ojas',
    prana: 'text-prana',
  };

  const button = (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 p-2.5 rounded-xl border transition-all duration-200 ${colors[variant]} ${
        isCollapsed ? 'justify-center' : ''
      }`}
    >
      <div className="w-8 h-8 rounded-full bg-background/50 flex items-center justify-center flex-shrink-0">
        <Icon className={`w-4 h-4 ${iconColors[variant]}`} />
      </div>
      {!isCollapsed && (
        <span className="font-medium text-foreground text-sm whitespace-nowrap">{label}</span>
      )}
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
