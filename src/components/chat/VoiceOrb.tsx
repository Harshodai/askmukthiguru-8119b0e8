import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Sparkles, Volume2, Pause } from 'lucide-react';
import type { VoiceConversationState } from '@/hooks/useVoiceConversation';

interface VoiceOrbProps {
  state: VoiceConversationState;
  audioLevel?: number; // 0 to 1
  size?: number;
  onClick?: () => void;
  className?: string;
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  state,
  audioLevel = 0,
  size = 180,
  onClick,
  className = '',
}) => {
  // Scale based on audio level when listening
  const dynamicScale = state === 'listening' ? 1 + audioLevel * 0.45 : 1;

  return (
    <div
      className={`relative flex items-center justify-center cursor-pointer select-none ${className}`}
      style={{ width: size, height: size }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Voice mode orb: ${state}`}
      data-testid="voice-orb-container"
    >
      {/* Outer Ethereal Glow Aura */}
      <motion.div
        className="absolute rounded-full filter blur-2xl pointer-events-none"
        style={{
          width: size * 1.3,
          height: size * 1.3,
          background:
            state === 'listening'
              ? 'radial-gradient(circle, rgba(245, 158, 11, 0.4) 0%, rgba(217, 119, 6, 0.1) 70%, transparent 100%)'
              : state === 'speaking'
              ? 'radial-gradient(circle, rgba(234, 88, 12, 0.45) 0%, rgba(245, 158, 11, 0.15) 70%, transparent 100%)'
              : state === 'thinking'
              ? 'radial-gradient(circle, rgba(168, 85, 247, 0.35) 0%, rgba(245, 158, 11, 0.1) 70%, transparent 100%)'
              : 'radial-gradient(circle, rgba(245, 158, 11, 0.2) 0%, transparent 70%)',
        }}
        animate={{
          scale: state === 'listening' ? [1, 1.15 + audioLevel * 0.3, 1] : [1, 1.08, 1],
          opacity: state === 'idle' ? 0.3 : 0.8,
        }}
        transition={{
          duration: state === 'thinking' ? 1.8 : 2.4,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* Ripple Waves when Listening or Speaking */}
      <AnimatePresence>
        {(state === 'listening' || state === 'speaking') && (
          <>
            {[0, 1, 2].map((idx) => (
              <motion.div
                key={idx}
                className="absolute rounded-full border border-saffron-gold/30 pointer-events-none"
                style={{ width: size, height: size }}
                initial={{ scale: 0.9, opacity: 0.8 }}
                animate={{
                  scale: [0.9, 1.45 + (state === 'listening' ? audioLevel * 0.5 : 0.2)],
                  opacity: [0.8, 0],
                }}
                transition={{
                  duration: 2.2,
                  repeat: Infinity,
                  delay: idx * 0.7,
                  ease: 'easeOut',
                }}
              />
            ))}
          </>
        )}
      </AnimatePresence>

      {/* Rotating Sacred Geometry Ring when Thinking */}
      {state === 'thinking' && (
        <motion.div
          className="absolute rounded-full border border-dashed border-amber-400/50 pointer-events-none"
          style={{ width: size * 1.15, height: size * 1.15 }}
          animate={{ rotate: 360 }}
          transition={{ duration: 12, repeat: Infinity, ease: 'linear' }}
        />
      )}

      {/* Main Core Orb */}
      <motion.div
        className="relative z-10 flex items-center justify-center rounded-full shadow-2xl transition-transform"
        style={{
          width: size,
          height: size,
          background:
            state === 'listening'
              ? 'radial-gradient(circle at 35% 35%, #FDE68A 0%, #F59E0B 50%, #B45309 100%)'
              : state === 'speaking'
              ? 'radial-gradient(circle at 35% 35%, #FED7AA 0%, #EA580C 55%, #9A3412 100%)'
              : state === 'thinking'
              ? 'radial-gradient(circle at 35% 35%, #DDD6FE 0%, #8B5CF6 55%, #6D28D9 100%)'
              : 'radial-gradient(circle at 35% 35%, #FDE68A 0%, #D97706 60%, #92400E 100%)',
          boxShadow:
            state === 'listening'
              ? '0 0 35px rgba(245, 158, 11, 0.6), inset 0 2px 10px rgba(255, 255, 255, 0.4)'
              : state === 'speaking'
              ? '0 0 35px rgba(234, 88, 12, 0.6), inset 0 2px 10px rgba(255, 255, 255, 0.4)'
              : state === 'thinking'
              ? '0 0 35px rgba(139, 92, 246, 0.5), inset 0 2px 10px rgba(255, 255, 255, 0.4)'
              : '0 0 20px rgba(217, 119, 6, 0.3), inset 0 2px 6px rgba(255, 255, 255, 0.3)',
        }}
        animate={{
          scale: dynamicScale,
        }}
        transition={{
          type: 'spring',
          stiffness: 300,
          damping: 20,
        }}
      >
        {/* State Icon Indicator */}
        <div className="text-white drop-shadow-md">
          {state === 'listening' ? (
            <motion.div
              animate={{ scale: [1, 1.15 + audioLevel * 0.3, 1] }}
              transition={{ duration: 0.6, repeat: Infinity }}
            >
              <Mic className="w-10 h-10" />
            </motion.div>
          ) : state === 'thinking' ? (
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
            >
              <Sparkles className="w-10 h-10 text-purple-100" />
            </motion.div>
          ) : state === 'speaking' ? (
            <motion.div
              animate={{ scale: [1, 1.12, 1] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            >
              <Volume2 className="w-10 h-10" />
            </motion.div>
          ) : (
            <Pause className="w-10 h-10 opacity-70" />
          )}
        </div>
      </motion.div>
    </div>
  );
};
