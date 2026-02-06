import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Heart, AlertCircle, X } from 'lucide-react';

const DISCLAIMER_KEY = 'askmukthiguru_disclaimer_accepted';

export const SafetyDisclaimer = () => {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const accepted = localStorage.getItem(DISCLAIMER_KEY);
    if (!accepted) {
      setIsVisible(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem(DISCLAIMER_KEY, 'true');
    setIsVisible(false);
  };

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-background/95 backdrop-blur-xl" />

          {/* Content */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="relative z-10 w-full max-w-md"
          >
            <div className="glass-card p-6 md:p-8">
              {/* Close button (subtle) */}
              <button
                onClick={handleAccept}
                className="absolute top-4 right-4 p-2 rounded-full hover:bg-muted/50 transition-colors opacity-50 hover:opacity-100"
              >
                <X className="w-4 h-4 text-muted-foreground" />
              </button>

              {/* Icon */}
              <div className="flex justify-center mb-6">
                <div className="w-16 h-16 rounded-full bg-gradient-to-br from-ojas/20 to-prana/20 flex items-center justify-center">
                  <Heart className="w-8 h-8 text-ojas" />
                </div>
              </div>

              {/* Title */}
              <h2 className="text-2xl font-bold text-center text-tejas mb-4">
                Welcome, Dear Seeker
              </h2>

              {/* Message */}
              <p className="text-muted-foreground text-center leading-relaxed mb-6">
                AskMukthiGuru is an AI spiritual companion inspired by the teachings of 
                Sri Preethaji & Sri Krishnaji. It offers wisdom and guidance on your 
                journey toward inner peace.
              </p>

              {/* Warning Box */}
              <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0 mt-0.5" />
                  <div className="text-sm">
                    <p className="font-medium text-destructive mb-1">Important Notice</p>
                    <p className="text-muted-foreground">
                      This is <strong>not</strong> a replacement for professional mental health 
                      support, medical advice, or therapy. If you're experiencing a crisis, 
                      please reach out to a qualified professional or crisis helpline.
                    </p>
                  </div>
                </div>
              </div>

              {/* Crisis Resources (India focused for AIKosh) */}
              <div className="text-xs text-muted-foreground/70 text-center mb-6">
                <p className="mb-1">Crisis Support (India):</p>
                <p>iCall: 9152987821 | Vandrevala Foundation: 1860-2662-345</p>
              </div>

              {/* Accept Button */}
              <button
                onClick={handleAccept}
                className="w-full py-3 bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-medium rounded-full transition-all duration-300 hover:scale-[1.02]"
              >
                I Understand — Begin My Journey
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
