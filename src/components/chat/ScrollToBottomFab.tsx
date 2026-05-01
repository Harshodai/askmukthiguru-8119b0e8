import { motion, AnimatePresence } from 'framer-motion';
import { ChevronsDown } from 'lucide-react';

interface ScrollToBottomFabProps {
  visible: boolean;
  unreadCount: number;
  onClick: () => void;
}

/**
 * Floating "Jump to latest" button. Shows when user scrolls up
 * more than 400px from the bottom of the messages area.
 */
export const ScrollToBottomFab = ({ visible, unreadCount, onClick }: ScrollToBottomFabProps) => (
  <AnimatePresence>
    {visible && (
      <motion.button
        initial={{ opacity: 0, y: 20, scale: 0.85 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.85 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        onClick={onClick}
        className="absolute bottom-4 right-4 z-30 flex items-center gap-1.5 px-3.5 py-2 rounded-full bg-ojas text-primary-foreground shadow-lg shadow-ojas/30 hover:bg-ojas-light transition-colors focus:outline-none focus:ring-2 focus:ring-ojas/60"
        aria-label={`Jump to latest message${unreadCount > 0 ? ` (${unreadCount} new)` : ''}`}
      >
        <ChevronsDown className="w-4 h-4" />
        <span className="text-xs font-medium whitespace-nowrap">
          {unreadCount > 0 ? `${unreadCount} new` : 'Latest'}
        </span>
      </motion.button>
    )}
  </AnimatePresence>
);
