import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Plus, 
  Flame, 
  MessageCircle, 
  Trash2, 
  PanelLeft, 
  Search, 
  Edit2, 
  Check, 
  X,
  MoreVertical
} from 'lucide-react';
import { 
  Conversation, 
  loadConversations, 
  deleteConversation,
  renameConversation,
  formatRelativeTime 
} from '@/lib/chatStorage';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

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

  const handleRename = useCallback((id: string) => {
    if (!editTitle.trim()) {
      setEditingId(null);
      return;
    }
    renameConversation(id, editTitle.trim());
    setConversations(loadConversations());
    setEditingId(null);
  }, [editTitle]);

  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    return conversations.filter(c => 
      c.preview.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [conversations, searchQuery]);

  const groupedConversations = filteredConversations.reduce((groups, conv) => {
    const timeGroup = formatRelativeTime(conv.updatedAt);
    if (!groups[timeGroup]) {
      groups[timeGroup] = [];
    }
    groups[timeGroup].push(conv);
    return groups;
  }, {} as Record<string, Conversation[]>);

  return (
    <>
      <AnimatePresence>
        {!isCollapsed && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 280, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.25, 0.1, 0.25, 1] }}
            className="hidden sm:flex flex-col h-full bg-card/95 backdrop-blur-xl border-r border-border/50 relative z-20"
          >
            {/* Header */}
            <div className="h-14 flex items-center justify-between px-3.5 border-b border-border/10">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-ojas/10 flex items-center justify-center">
                  <Flame className="w-5 h-5 text-ojas" />
                </div>
                <span className="font-semibold text-sm tracking-tight">AskMukthiGuru</span>
              </div>
              <button
                onClick={onToggleCollapse}
                className="p-2 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                aria-label="Collapse sidebar"
                data-testid="sidebar-toggle"
              >
                <PanelLeft className="w-5 h-5" />
              </button>
            </div>

            {/* Top Actions */}
            <div className="p-3 space-y-1">
              <button
                onClick={onNewConversation}
                className="w-full flex items-center gap-3 p-2.5 rounded-xl bg-primary/10 text-primary hover:bg-primary/15 transition-all group border border-primary/20"
              >
                <div className="w-6 h-6 rounded-full bg-primary/20 flex items-center justify-center group-hover:bg-primary/30">
                  <Plus className="w-3.5 h-3.5" />
                </div>
                <span className="font-medium text-sm">New Chat</span>
              </button>
              
              <div className="relative mt-2">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search chats..."
                  className="pl-9 h-9 bg-muted/30 border-transparent focus-visible:bg-muted/50 focus-visible:ring-ojas/30 transition-all text-xs"
                />
              </div>
            </div>

            {/* Scrollable Content */}
            <ScrollArea className="flex-1 px-2">
              <div className="py-2 space-y-4">
                {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                  <div key={timeGroup} className="space-y-1">
                    <p className="text-[10px] text-muted-foreground/60 uppercase tracking-widest font-bold px-2 mb-1">
                      {timeGroup}
                    </p>
                    <div className="space-y-0.5">
                      {convs.map((conv) => (
                        <div key={conv.id} className="relative group" data-testid="conversation-item">
                          {editingId === conv.id ? (
                            <div className="flex items-center gap-1 px-2 py-1.5 bg-muted/60 rounded-xl border border-ojas/30">
                              <Input
                                autoFocus
                                value={editTitle}
                                onChange={(e) => setEditTitle(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') handleRename(conv.id);
                                  if (e.key === 'Escape') setEditingId(null);
                                }}
                                className="h-6 text-xs px-1 bg-transparent border-none focus-visible:ring-0"
                              />
                              <button onClick={() => handleRename(conv.id)} className="p-1 text-ojas hover:bg-ojas/10 rounded">
                                <Check className="w-3 h-3" />
                              </button>
                              <button onClick={() => setEditingId(null)} className="p-1 text-muted-foreground hover:bg-muted rounded">
                                <X className="w-3 h-3" />
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => onSelectConversation(conv)}
                              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 relative group ${
                                conv.id === currentConversationId
                                  ? 'bg-muted text-foreground'
                                  : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground'
                              }`}
                            >
                              <MessageCircle className={`w-4 h-4 flex-shrink-0 ${conv.id === currentConversationId ? 'text-ojas' : 'opacity-50'}`} />
                              <p className="flex-1 text-xs truncate pr-6 font-medium">
                                {conv.preview || 'New conversation'}
                              </p>
                              
                              <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 transition-opacity ${
                                conv.id === currentConversationId ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                              }`}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setEditingId(conv.id);
                                    setEditTitle(conv.preview);
                                  }}
                                  className="p-1 rounded-md hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                                  title="Rename"
                                >
                                  <Edit2 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setDeleteTarget(conv.id);
                                  }}
                                  className="p-1 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                                  title="Delete"
                                  aria-label="Delete conversation"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>

            {/* Footer — Serene Mind */}
            <div className="p-3 border-t border-border/10">
              <button
                onClick={onOpenSereneMind}
                className="w-full flex items-center gap-3 p-2.5 rounded-xl hover:bg-muted/50 transition-all group"
              >
                <div className="w-7 h-7 rounded-full bg-prana/10 flex items-center justify-center text-prana group-hover:bg-prana/20 transition-colors">
                  <Flame className="w-4 h-4" />
                </div>
                <div className="text-left overflow-hidden">
                  <p className="text-[11px] font-semibold truncate text-foreground">Serene Mind</p>
                  <p className="text-[10px] text-muted-foreground truncate">Guided Breathing</p>
                </div>
              </button>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

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
