import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Plus, Flame, MessageCircle, ArrowLeft, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
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
  onOpenSereneMind: () => void;
  onSelectConversation?: (conversation: Conversation) => void;
  currentConversationId?: string;
}

export const MobileConversationSheet = ({
  isOpen,
  onClose,
  onNewConversation,
  onOpenSereneMind,
  onSelectConversation,
  currentConversationId,
}: MobileConversationSheetProps) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  useEffect(() => {
    if (isOpen) {
      setConversations(loadConversations());
    }
  }, [isOpen]);

  const handleDeleteConversation = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(id);
    setConversations(loadConversations());
  };

  const handleSelectConversation = (conv: Conversation) => {
    if (onSelectConversation) {
      onSelectConversation(conv);
    }
    onClose();
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
            className="fixed bottom-0 left-0 right-0 z-50 bg-card border-t border-border rounded-t-3xl max-h-[85vh] overflow-hidden shadow-xl"
          >
            {/* Handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-border" />
            </div>

            {/* Header */}
            <div className="px-6 py-4 border-b border-border">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full overflow-hidden ring-2 ring-ojas/30 shadow-md">
                    <img
                      src={gurusPhoto}
                      alt="Sri Preethaji & Sri Krishnaji"
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div>
                    <h2 className="font-semibold text-foreground">AskMukthiGuru</h2>
                    <p className="text-xs text-muted-foreground">Your Spiritual Companion</p>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="p-2 rounded-full hover:bg-muted transition-colors"
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4 overflow-y-auto max-h-[60vh] scrollbar-spiritual">
              {/* Meditation Stats */}
              <MeditationStats />

              {/* New Conversation */}
              <button
                onClick={() => {
                  onNewConversation();
                  onClose();
                }}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-ojas/10 border border-ojas/20 hover:border-ojas/40 hover:bg-ojas/15 transition-all group"
              >
                <div className="w-10 h-10 rounded-full bg-ojas/20 flex items-center justify-center group-hover:bg-ojas/30 transition-colors">
                  <Plus className="w-5 h-5 text-ojas" />
                </div>
                <div className="text-left">
                  <p className="font-medium text-foreground">New Conversation</p>
                  <p className="text-xs text-muted-foreground">Start fresh with the Gurus</p>
                </div>
              </button>

              {/* Serene Mind Quick Access */}
              <button
                onClick={() => {
                  onOpenSereneMind();
                  onClose();
                }}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-prana/10 border border-prana/20 hover:border-prana/40 hover:bg-prana/15 transition-all group"
              >
                <div className="w-10 h-10 rounded-full bg-prana/20 flex items-center justify-center group-hover:bg-prana/30 transition-colors">
                  <Flame className="w-5 h-5 text-ojas" />
                </div>
                <div className="text-left">
                  <p className="font-medium text-foreground">Serene Mind Meditation</p>
                  <p className="text-xs text-muted-foreground">3-minute guided breathwork</p>
                </div>
              </button>

              {/* Conversation History */}
              {Object.keys(groupedConversations).length > 0 && (
                <div className="pt-4">
                  <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3 font-medium">
                    Recent Conversations
                  </p>
                  <div className="space-y-3">
                    {Object.entries(groupedConversations).map(([timeGroup, convs]) => (
                      <div key={timeGroup}>
                        <p className="text-xs text-muted-foreground mb-2">{timeGroup}</p>
                        <div className="space-y-2">
                          {convs.map((conv) => (
                            <motion.div
                              key={conv.id}
                              initial={{ opacity: 0, x: -10 }}
                              animate={{ opacity: 1, x: 0 }}
                              className={`flex items-center gap-3 p-3 rounded-xl cursor-pointer transition-all group ${
                                conv.id === currentConversationId
                                  ? 'bg-ojas/15 border border-ojas/30'
                                  : 'bg-muted/30 hover:bg-muted/50 border border-transparent'
                              }`}
                              onClick={() => handleSelectConversation(conv)}
                            >
                              <MessageCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-foreground truncate">
                                  {conv.preview || 'New conversation'}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {conv.messageCount} messages
                                </p>
                              </div>
                              <button
                                onClick={(e) => handleDeleteConversation(conv.id, e)}
                                className="p-1.5 rounded-full opacity-0 group-hover:opacity-100 hover:bg-destructive/20 transition-all"
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
              )}

              {/* Navigation */}
              <div className="pt-4 border-t border-border">
                <Link
                  to="/"
                  onClick={onClose}
                  className="flex items-center gap-3 p-3 rounded-xl hover:bg-muted/50 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4 text-muted-foreground" />
                  <p className="text-sm text-foreground">Back to Home</p>
                </Link>
              </div>
            </div>

            {/* Safe area padding for iOS */}
            <div className="h-safe-area-inset-bottom" />
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
