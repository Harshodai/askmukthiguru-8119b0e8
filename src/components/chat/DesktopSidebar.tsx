import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Flame, MessageCircle, Trash2, ChevronRight, PanelLeft } from 'lucide-react';
import { 
  Conversation, 
  loadConversations, 
  deleteConversation,
  formatRelativeTime 
} from '@/lib/chatStorage';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

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
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  useEffect(() => {
    setConversations(loadConversations());
  }, [refreshTrigger]);

  const confirmDelete = useCallback(() => {
    if (!deleteTarget) return;
    deleteConversation(deleteTarget);
    setConversations(loadConversations());
    onDeleteConversation?.(deleteTarget);
    setDeleteTarget(null);
  }, [deleteTarget, onDeleteConversation]);

  const groupedConversations = conversations.reduce((groups, conv) => {
    const timeGroup = formatRelativeTime(conv.updatedAt);
    if (!groups[timeGroup]) {
      groups[timeGroup] = [];
    }
    groups[timeGroup].push(conv);
    return groups;
  }, {} as Record<string, Conversation[]>);

  return (
    <>
      {/* Sidebar panel */}
      <AnimatePresence>
        {!isCollapsed && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
            className="hidden sm:flex flex-col h-full bg-card/95 backdrop-blur-xl border-r border-border/50 relative z-20"
            data-testid="desktop-sidebar"
          >


            {/* Header - ChatGPT Style */}
            <div className="h-14 flex items-center justify-between px-3.5">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-ojas/10 flex items-center justify-center">
                  <Flame className="w-5 h-5 text-ojas" />
                </div>
              </div>
              <button
                onClick={onToggleCollapse}
                className="p-2 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                aria-label="Collapse sidebar"
              >
                <PanelLeft className="w-5 h-5" />
              </button>
            </div>

            {/* Scrollable Content */}
            <ScrollArea className="flex-1">
              <div className="p-2.5 space-y-1.5">
                {/* Action Buttons */}
                <SidebarActionButton
                  onClick={onNewConversation}
                  icon={Plus}
                  label="New Conversation"
                  variant="ojas"
                  prominent
                />
                <SidebarActionButton
                  onClick={onOpenSereneMind}
                  icon={Flame}
                  label="Serene Mind"
                  variant="prana"
                />

                {/* Divider */}
                <div className="h-px bg-border/30 my-2" />

                {/* Conversation History */}
                {Object.keys(groupedConversations).length > 0 && (
                  <div>
                    <p className="text-[10px] text-muted-foreground/70 uppercase tracking-wider mb-2 font-medium px-2">
                      History
                    </p>
                    <div className="space-y-0.5">
                      {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                        <div key={timeGroup}>
                          <p className="text-[10px] text-muted-foreground/50 mb-1 px-2 mt-2 first:mt-0">
                            {timeGroup}
                          </p>
                          <div className="space-y-0.5">
                            {convs.map((conv) => (
                              <ConversationItem
                                key={conv.id}
                                conversation={conv}
                                isActive={conv.id === currentConversationId}
                                onSelect={() => onSelectConversation(conv)}
                                onDelete={() => setDeleteTarget(conv.id)}
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
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This conversation will be permanently removed. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-cancel">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmDelete();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              data-testid="delete-confirm"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

// ── Conversation item ───────────────────────────────────────────────
const ConversationItem = ({
  conversation,
  isActive,
  onSelect,
  onDelete,
}: {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) => {
  const preview = conversation.preview || 'New conversation';

  return (
    <div
      className={`group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
        isActive
          ? 'bg-muted/80 text-foreground'
          : 'hover:bg-muted/40 text-muted-foreground hover:text-foreground'
      }`}
      onClick={onSelect}
      title={preview}
    >
      <p className="flex-1 text-sm truncate">
        {preview}
      </p>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className={`p-1 rounded-md transition-all flex-shrink-0 ${
          isActive 
            ? 'opacity-100' 
            : 'opacity-0 group-hover:opacity-100'
        } hover:bg-red-500/10 hover:text-red-500`}
        aria-label="Delete conversation"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
};

// ── Sidebar action button ───────────────────────────────────────────
const SidebarActionButton = ({
  onClick,
  icon: Icon,
  label,
  variant,
  prominent = false,
}: {
  onClick: () => void;
  icon: React.ElementType;
  label: string;
  variant: 'ojas' | 'prana';
  prominent?: boolean;
}) => {
  if (prominent) {
    return (
      <button
        onClick={onClick}
        className="w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-200 hover:bg-muted group"
      >
        <div className="w-8 h-8 rounded-full border border-border flex items-center justify-center flex-shrink-0 group-hover:border-foreground transition-colors">
          <Icon className="w-4 h-4 text-foreground" />
        </div>
        <span className="font-medium text-foreground text-sm">
          {label}
        </span>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 rounded-xl transition-all duration-200 hover:bg-muted/50 group"
    >
      <Icon className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors" />
      <span className="text-muted-foreground group-hover:text-foreground text-sm transition-colors">
        {label}
      </span>
    </button>
  );
};
