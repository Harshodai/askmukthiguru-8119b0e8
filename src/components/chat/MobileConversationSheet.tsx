import { motion, AnimatePresence } from 'framer-motion';
import { X, Plus, Flame, MessageCircle, ArrowLeft, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import gurusPhoto from '@/assets/gurus-photo.jpg';

interface MobileConversationSheetProps {
  isOpen: boolean;
  onClose: () => void;
  onNewConversation: () => void;
  onOpenSereneMind: () => void;
}

export const MobileConversationSheet = ({
  isOpen,
  onClose,
  onNewConversation,
  onOpenSereneMind,
}: MobileConversationSheetProps) => {
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
            className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm"
          />

          {/* Bottom Sheet */}
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className="fixed bottom-0 left-0 right-0 z-50 bg-card border-t border-border rounded-t-3xl max-h-[80vh] overflow-hidden"
          >
            {/* Handle */}
            <div className="flex justify-center pt-3 pb-2">
              <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
            </div>

            {/* Header */}
            <div className="px-6 py-4 border-b border-border/50">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full overflow-hidden ring-2 ring-ojas/30">
                    <img
                      src={gurusPhoto}
                      alt="Sri Preethaji & Sri Krishnaji"
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div>
                    <h2 className="font-semibold text-tejas">AskMukthiGuru</h2>
                    <p className="text-xs text-muted-foreground">Your Spiritual Companion</p>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="p-2 rounded-full hover:bg-muted/50 transition-colors"
                >
                  <X className="w-5 h-5 text-muted-foreground" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="p-6 space-y-4 overflow-y-auto">
              {/* New Conversation */}
              <button
                onClick={() => {
                  onNewConversation();
                  onClose();
                }}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-gradient-to-r from-ojas/10 to-prana/10 border border-ojas/20 hover:border-ojas/40 transition-colors group"
              >
                <div className="w-10 h-10 rounded-full bg-ojas/20 flex items-center justify-center group-hover:bg-ojas/30 transition-colors">
                  <Plus className="w-5 h-5 text-ojas" />
                </div>
                <div className="text-left">
                  <p className="font-medium text-tejas">New Conversation</p>
                  <p className="text-xs text-muted-foreground">Start fresh with the Gurus</p>
                </div>
              </button>

              {/* Serene Mind Quick Access */}
              <button
                onClick={() => {
                  onOpenSereneMind();
                  onClose();
                }}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-prana/10 border border-prana/20 hover:border-prana/40 transition-colors group"
              >
                <div className="w-10 h-10 rounded-full bg-prana/20 flex items-center justify-center group-hover:bg-prana/30 transition-colors">
                  <Flame className="w-5 h-5 text-ojas" />
                </div>
                <div className="text-left">
                  <p className="font-medium text-tejas">Serene Mind Meditation</p>
                  <p className="text-xs text-muted-foreground">3-minute guided breathwork</p>
                </div>
              </button>

              {/* Recent Conversations Placeholder */}
              <div className="pt-4">
                <p className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
                  Recent Conversations
                </p>
                <div className="space-y-2">
                  {/* Placeholder for future conversation history */}
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/30">
                    <MessageCircle className="w-4 h-4 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">Current conversation</p>
                  </div>
                </div>
              </div>

              {/* Navigation */}
              <div className="pt-4 border-t border-border/50">
                <Link
                  to="/"
                  onClick={onClose}
                  className="flex items-center gap-3 p-3 rounded-lg hover:bg-muted/30 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4 text-muted-foreground" />
                  <p className="text-sm text-tejas">Back to Home</p>
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
