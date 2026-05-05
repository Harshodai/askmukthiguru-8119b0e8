import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Flame, MessageCircle, Trash2, ChevronLeft, ChevronRight, Home, MoreVertical } from 'lucide-react';
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface DesktopSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  onNewConversation: () => void;
  onOpenSereneMind: () => void;
  onSelectConversation: (conversation: Conversation) => void;
  onDeleteConversation?: (id: string) => void;
  currentConversationId?: string;
  refreshTrigger?: number;
}

export const DesktopSidebar = ({
  isCollapsed,
  onToggleCollapse,
  onNewConversation,
  onOpenSereneMind,
  onSelectConversation,
  onDeleteConversation,
  currentConversationId,
  refreshTrigger,
}: DesktopSidebarProps) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    setConversations(loadConversations());
  }, [refreshTrigger]);

  const handleDeleteConversation = useCallback((id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    deleteConversation(id);
    setConversations(loadConversations());
    onDeleteConversation?.(id);
  }, [onDeleteConversation]);

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
      transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
      className="hidden sm:flex flex-col h-full bg-card/95 backdrop-blur-xl border-r border-border/50 relative z-20 overflow-hidden"
      data-testid="desktop-sidebar"
    >
      {/* Collapse Toggle */}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={onToggleCollapse}
            className="absolute -right-3.5 top-20 z-30 w-7 h-7 rounded-full bg-card border border-border/80 shadow-md flex items-center justify-center hover:bg-muted hover:scale-110 transition-all active:scale-95"
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            data-testid="sidebar-toggle"
          >
            <motion.div
              animate={{ rotate: isCollapsed ? 0 : 180 }}
              transition={{ duration: 0.25 }}
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
          <AnimatePresence mode="wait">
            {!isCollapsed && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="min-w-0 overflow-hidden"
              >
                <h2 className="font-semibold text-foreground text-sm truncate">AskMukthiGuru</h2>
                <p className="text-[11px] text-muted-foreground truncate">Your Spiritual Companion</p>
              </motion.div>
            )}
          </AnimatePresence>
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
              <AnimatePresence>
                {!isCollapsed && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-[10px] text-muted-foreground/70 uppercase tracking-wider mb-2 font-medium px-2"
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
                          className="text-[10px] text-muted-foreground/50 mb-1 px-2 mt-2 first:mt-0"
                        >
                          {timeGroup}
                        </motion.p>
                      )}
                    </AnimatePresence>
                    <div className="space-y-0.5">
                      {convs.map((conv) => (
                        <ConversationItem
                          key={conv.id}
                          conversation={conv}
                          isActive={conv.id === currentConversationId}
                          isCollapsed={isCollapsed}
                          onSelect={() => onSelectConversation(conv)}
                          onDelete={(e) => handleDeleteConversation(conv.id, e)}
                        />
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

// ── Conversation item with delete support in both modes ─────────────
const ConversationItem = ({
  conversation,
  isActive,
  isCollapsed,
  onSelect,
  onDelete,
}: {
  conversation: Conversation;
  isActive: boolean;
  isCollapsed: boolean;
  onSelect: () => void;
  onDelete: (e?: React.MouseEvent) => void;
}) => {
  const preview = conversation.preview || 'New conversation';

  const content = (
    <div
      className={`group flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer transition-all duration-200 ${
        isActive
          ? 'bg-ojas/10 border border-ojas/20 shadow-sm'
          : 'hover:bg-muted/40 border border-transparent'
      } ${isCollapsed ? 'justify-center' : ''}`}
      onClick={onSelect}
      title={preview}
      data-testid="conversation-item"
    >
      <MessageCircle className={`w-4 h-4 flex-shrink-0 transition-colors ${
        isActive ? 'text-ojas' : 'text-muted-foreground'
      }`} />
      {!isCollapsed && (
        <>
          <p className="flex-1 text-sm text-foreground truncate min-w-0">
            {preview}
          </p>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(e);
            }}
            className="p-1 rounded-full opacity-0 group-hover:opacity-100 hover:bg-destructive/20 transition-all flex-shrink-0"
            aria-label="Delete conversation"
            data-testid="delete-conversation"
          >
            <Trash2 className="w-3 h-3 text-destructive" />
          </button>
        </>
      )}
    </div>
  );

  if (isCollapsed) {
    return (
      <DropdownMenu>
        <Tooltip>
          <TooltipTrigger asChild>
            <DropdownMenuTrigger asChild>
              {content}
            </DropdownMenuTrigger>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={12}>
            <p className="max-w-[200px] truncate">{preview}</p>
          </TooltipContent>
        </Tooltip>
        <DropdownMenuContent side="right" align="start" sideOffset={8}>
          <DropdownMenuItem onClick={onSelect}>
            <MessageCircle className="w-3.5 h-3.5 mr-2" />
            Open
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="w-3.5 h-3.5 mr-2" />
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return content;
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
      <AnimatePresence>
        {!isCollapsed && (
          <motion.span
            initial={{ opacity: 0, width: 0 }}
            animate={{ opacity: 1, width: 'auto' }}
            exit={{ opacity: 0, width: 0 }}
            className="font-medium text-foreground text-sm whitespace-nowrap overflow-hidden"
          >
            {label}
          </motion.span>
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
