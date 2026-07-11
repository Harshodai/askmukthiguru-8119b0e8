import { motion } from 'framer-motion';
import { Flame } from 'lucide-react';
import { useTranslation } from 'react-i18next';

/**
 * Full-viewport branded loading spinner.
 * Used as the global Suspense fallback to replace bare "Loading..." text.
 * Respects prefers-reduced-motion.
 */
export const BrandedSpinner = () => (
  <div className="h-dvh w-full flex flex-col items-center justify-center bg-background gap-4">
    <motion.div
      className="relative flex items-center justify-center"
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Outer glow ring */}
      <motion.div
        className="absolute w-16 h-16 rounded-full bg-ojas/20"
        animate={{ scale: [1, 1.3, 1], opacity: [0.5, 0.2, 0.5] }}
        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* Inner icon */}
      <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/30 flex items-center justify-center shadow-lg">
        <motion.div
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Flame className="w-6 h-6 text-ojas" />
        </motion.div>
      </div>
    </motion.div>

    <motion.p
      className="text-sm font-medium text-muted-foreground tracking-wide"
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 0.7, y: 0 }}
      transition={{ duration: 0.4, delay: 0.15 }}
    >
      AskMukthiGuru
    </motion.p>
  </div>
);
