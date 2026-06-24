import { motion, AnimatePresence } from 'framer-motion';
import { ReactNode } from 'react';

export interface FloatingActionButtonProps {
  visible: boolean;
  onClick: () => void;
  icon?: ReactNode;
  label: string;
  className?: string;
  ariaLabel?: string;
}

export const FloatingActionButton = ({
  visible,
  onClick,
  icon,
  label,
  className = 'absolute bottom-24 right-6 z-30 flex items-center gap-1.5 px-4 py-2 rounded-full bg-card/95 backdrop-blur-md border border-border/60 text-foreground shadow-lg hover:shadow-xl hover:border-ojas/30 transition-all focus:outline-none focus:ring-2 focus:ring-ojas/40',
  ariaLabel,
}: FloatingActionButtonProps) => (
  <AnimatePresence>
    {visible && (
      <motion.button
        initial={{ opacity: 0, y: 16, scale: 0.9 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.9 }}
        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
        onClick={onClick}
        className={className}
        aria-label={ariaLabel ?? label}
      >
        {icon && <span className="shrink-0">{icon}</span>}
        <span className="text-xs font-medium whitespace-nowrap">{label}</span>
      </motion.button>
    )}
  </AnimatePresence>
);
