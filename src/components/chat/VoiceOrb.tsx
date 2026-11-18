import React, { useMemo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Mic, Sparkles, Volume2, Pause } from 'lucide-react';
import type { VoiceConversationState } from '@/hooks/useVoiceConversation';

export interface VoiceOrbProps {
  state: VoiceConversationState;
  audioLevel?: number; // 0 to 1
  size?: number;
  onClick?: () => void;
  className?: string;
}

export const VoiceOrb: React.FC<VoiceOrbProps> = ({
  state,
  audioLevel = 0,
  size = 200,
  onClick,
  className = '',
}) => {
  const shouldReduceMotion = useReducedMotion();

  // Dynamic scale interpolation based on live acoustic input
  const clampedLevel = Math.min(Math.max(audioLevel, 0), 1);
  const dynamicScale = state === 'listening' ? 1 + clampedLevel * 0.28 : state === 'speaking' ? 1.05 : 1;

  // 16 radial audio spectrum bars radiating outward
  const radialBars = useMemo(() => {
    const bars = [];
    const count = 16;
    for (let i = 0; i < count; i++) {
      const angle = (i * 360) / count;
      // Staggered harmonic multiplier for organic liquid equalizer feel
      const harmonic = 0.4 + 0.6 * Math.abs(Math.sin((i / count) * Math.PI * 2));
      bars.push({ id: i, angle, harmonic });
    }
    return bars;
  }, []);

  return (
    <div
      className={`relative flex items-center justify-center cursor-pointer select-none touch-manipulation ${className}`}
      style={{ width: size * 1.5, height: size * 1.5 }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Voice mode orb: ${state}`}
      data-testid="voice-orb-container"
    >
      {/* =========================================================================
          Layer 1: Breathing Auric Glow & Ambient Diffusion
         ========================================================================= */}
      <motion.div
        className="absolute rounded-full filter blur-3xl pointer-events-none"
        style={{
          width: size * 1.35,
          height: size * 1.35,
          background:
            state === 'listening'
              ? 'radial-gradient(circle, rgba(245, 158, 11, 0.45) 0%, rgba(217, 119, 6, 0.15) 60%, transparent 100%)'
              : state === 'speaking'
              ? 'radial-gradient(circle, rgba(168, 85, 247, 0.45) 0%, rgba(234, 88, 12, 0.2) 65%, transparent 100%)'
              : state === 'thinking'
              ? 'radial-gradient(circle, rgba(139, 92, 246, 0.4) 0%, rgba(79, 70, 229, 0.2) 60%, transparent 100%)'
              : 'radial-gradient(circle, rgba(245, 158, 11, 0.2) 0%, transparent 70%)',
        }}
        animate={
          shouldReduceMotion
            ? { opacity: 0.6 }
            : {
                scale: state === 'listening' ? [1, 1.18 + clampedLevel * 0.25, 1] : [1, 1.08, 1],
                opacity: state === 'idle' ? 0.35 : 0.85,
              }
        }
        transition={{
          duration: state === 'thinking' ? 1.6 : 2.2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
      />

      {/* =========================================================================
          Layer 2: Golden Ratio Orbital Ring & Celestial Sacred Geometry (Ekam)
         ========================================================================= */}
      <div
        className="absolute rounded-full border border-amber-400/25 dark:border-amber-400/20 pointer-events-none"
        style={{ width: size * 1.28, height: size * 1.28 }}
      />

      {/* Counter-rotating celestial orbiting markers */}
      {!shouldReduceMotion && (
        <motion.div
          className="absolute rounded-full border border-dashed border-amber-400/40 pointer-events-none"
          style={{ width: size * 1.22, height: size * 1.22 }}
          animate={{ rotate: 360 }}
          transition={{ duration: state === 'thinking' ? 8 : 22, repeat: Infinity, ease: 'linear' }}
        >
          {/* Celestial marker bead 1 */}
          <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-gradient-to-r from-amber-300 to-amber-500 shadow-[0_0_10px_#F59E0B]" />
          {/* Celestial marker bead 2 */}
          <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-gradient-to-r from-amber-400 to-amber-200 shadow-[0_0_8px_#F59E0B]" />
        </motion.div>
      )}

      {/* =========================================================================
          Layer 3: 16-Bar Radial Harmonic Audio Spectrum Equalizer
         ========================================================================= */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        {radialBars.map((bar) => {
          // Dynamic bar height based on speech intensity and state
          let barHeight = 8;
          let barColor = 'bg-amber-400/40';

          if (state === 'listening') {
            const dynamicBurst = 8 + clampedLevel * 34 * bar.harmonic;
            barHeight = dynamicBurst;
            barColor = 'bg-gradient-to-t from-amber-500 to-amber-300';
          } else if (state === 'speaking') {
            barHeight = 10 + Math.sin(bar.angle) * 12 + 8;
            barColor = 'bg-gradient-to-t from-violet-500 to-amber-400';
          } else if (state === 'thinking') {
            barHeight = 6;
            barColor = 'bg-purple-400/30';
          }

          return (
            <div
              key={bar.id}
              className="absolute flex items-start justify-center"
              style={{
                width: 4,
                height: size * 1.12,
                transform: `rotate(${bar.angle}deg)`,
              }}
            >
              <motion.div
                className={`w-1 rounded-full ${barColor} shadow-[0_0_6px_rgba(245,158,11,0.5)]`}
                animate={
                  shouldReduceMotion
                    ? {}
                    : {
                        height: barHeight,
                        opacity: state === 'idle' ? 0.3 : 0.85,
                      }
                }
                transition={{
                  duration: 0.15,
                  ease: 'easeOut',
                }}
              />
            </div>
          );
        })}
      </div>

      {/* =========================================================================
          Layer 4: Ripple Shockwaves when Listening or Imparting Wisdom
         ========================================================================= */}
      <AnimatePresence>
        {!shouldReduceMotion && (state === 'listening' || state === 'speaking') && (
          <>
            {[0, 1, 2].map((idx) => (
              <motion.div
                key={idx}
                className="absolute rounded-full border border-amber-400/35 pointer-events-none"
                style={{ width: size, height: size }}
                initial={{ scale: 0.95, opacity: 0.85 }}
                animate={{
                  scale: [0.95, 1.48 + (state === 'listening' ? clampedLevel * 0.45 : 0.25)],
                  opacity: [0.85, 0],
                }}
                transition={{
                  duration: 2.4,
                  repeat: Infinity,
                  delay: idx * 0.75,
                  ease: 'easeOut',
                }}
              />
            ))}
          </>
        )}
      </AnimatePresence>

      {/* =========================================================================
          Layer 5: 3D Specular Glass Core & Interaction Anchor
         ========================================================================= */}
      <motion.div
        className="relative z-10 flex items-center justify-center rounded-full overflow-hidden transition-shadow"
        style={{
          width: size,
          height: size,
          background:
            state === 'listening'
              ? 'radial-gradient(circle at 35% 30%, #FEF3C7 0%, #F59E0B 45%, #B45309 85%, #78350F 100%)'
              : state === 'speaking'
              ? 'radial-gradient(circle at 35% 30%, #F5D0FE 0%, #A855F7 45%, #6B21A8 85%, #4C1D95 100%)'
              : state === 'thinking'
              ? 'radial-gradient(circle at 35% 30%, #E0E7FF 0%, #6366F1 45%, #4338CA 85%, #312E81 100%)'
              : 'radial-gradient(circle at 35% 30%, #FEF3C7 0%, #D97706 50%, #92400E 90%, #451A03 100%)',
          boxShadow:
            state === 'listening'
              ? '0 12px 40px rgba(245, 158, 11, 0.55), inset 0 3px 8px rgba(255, 255, 255, 0.6), inset 0 -4px 12px rgba(0, 0, 0, 0.35)'
              : state === 'speaking'
              ? '0 12px 40px rgba(168, 85, 247, 0.55), inset 0 3px 8px rgba(255, 255, 255, 0.6), inset 0 -4px 12px rgba(0, 0, 0, 0.35)'
              : state === 'thinking'
              ? '0 12px 40px rgba(99, 102, 241, 0.5), inset 0 3px 8px rgba(255, 255, 255, 0.6), inset 0 -4px 12px rgba(0, 0, 0, 0.35)'
              : '0 8px 24px rgba(217, 119, 6, 0.35), inset 0 2px 6px rgba(255, 255, 255, 0.4), inset 0 -3px 8px rgba(0, 0, 0, 0.3)',
        }}
        animate={
          shouldReduceMotion
            ? { scale: 1 }
            : {
                scale: dynamicScale,
              }
        }
        whileHover={{ scale: 1.04 }}
        whileTap={{ scale: 0.95 }}
        transition={{
          type: 'spring',
          stiffness: 280,
          damping: 20,
        }}
      >
        {/* Top-left specular gloss highlight */}
        <div
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at 32% 26%, rgba(255, 255, 255, 0.65) 0%, rgba(255, 255, 255, 0.15) 35%, transparent 65%)',
          }}
        />

        {/* State Icon Indicator with smooth kinetic transitions */}
        <div className="relative z-20 text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.6)]">
          {state === 'listening' ? (
            <motion.div
              animate={shouldReduceMotion ? {} : { scale: [1, 1.12 + clampedLevel * 0.25, 1] }}
              transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Mic className="w-11 h-11" />
            </motion.div>
          ) : state === 'thinking' ? (
            <motion.div
              animate={shouldReduceMotion ? {} : { rotate: 360 }}
              transition={{ duration: 5, repeat: Infinity, ease: 'linear' }}
            >
              <Sparkles className="w-11 h-11 text-indigo-100" />
            </motion.div>
          ) : state === 'speaking' ? (
            <motion.div
              animate={shouldReduceMotion ? {} : { scale: [1, 1.14, 1] }}
              transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Volume2 className="w-11 h-11 text-purple-100" />
            </motion.div>
          ) : (
            <Pause className="w-10 h-10 opacity-75" />
          )}
        </div>
      </motion.div>
    </div>
  );
};
