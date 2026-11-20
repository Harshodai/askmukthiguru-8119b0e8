import React, { useMemo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { Mic, Sprout, Volume2, Pause } from 'lucide-react';
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
  type RadialBar = { id: number; angle: number; harmonic: number };

  // Dynamic scale interpolation based on live acoustic input
  const clampedLevel = Math.min(Math.max(audioLevel, 0), 1);
  const dynamicScale = state === 'listening' ? 1 + clampedLevel * 0.28 : state === 'speaking' ? 1.05 : 1;

  // 16 radial audio spectrum bars radiating outward
  const radialBars = useMemo(() => {
    const bars: RadialBar[] = [];
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
          Layer 5: Sacred Ekam Golden Orb & Interaction Anchor
         ========================================================================= */}
      <motion.div
        className="relative z-10 flex items-center justify-center rounded-full overflow-hidden transition-shadow ring-2 ring-amber-400/60 dark:ring-amber-300/70"
        style={{
          width: size,
          height: size,
          boxShadow:
            state === 'listening'
              ? '0 12px 40px rgba(245, 158, 11, 0.65), 0 0 35px rgba(245, 158, 11, 0.55), inset 0 0 20px rgba(254, 243, 199, 0.3)'
              : state === 'speaking'
              ? '0 12px 40px rgba(217, 119, 6, 0.65), 0 0 35px rgba(245, 158, 11, 0.5), inset 0 0 20px rgba(254, 243, 199, 0.3)'
              : state === 'thinking'
              ? '0 12px 40px rgba(245, 158, 11, 0.5), 0 0 25px rgba(245, 158, 11, 0.4), inset 0 0 20px rgba(254, 243, 199, 0.25)'
              : '0 8px 24px rgba(217, 119, 6, 0.45), 0 0 20px rgba(245, 158, 11, 0.35)',
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
        {/* Authentic Sacred Ekam Golden Orb Photo */}
        <img
          src="/images/ekam-golden-orb-lotus-square.png"
          alt="Sacred Ekam Golden Orb"
          className="absolute inset-0 w-full h-full object-cover select-none pointer-events-none transform scale-105"
          onError={(e) => {
            (e.currentTarget as HTMLElement).style.display = 'none';
          }}
        />

        {/* Ambient lighting gradient overlay for seamless dark integration */}
        <div
          className="absolute inset-0 rounded-full pointer-events-none mix-blend-overlay opacity-30"
          style={{
            background:
              state === 'listening'
                ? 'radial-gradient(circle, rgba(245, 158, 11, 0.8) 0%, transparent 80%)'
                : state === 'speaking'
                ? 'radial-gradient(circle, rgba(234, 88, 12, 0.8) 0%, transparent 80%)'
                : state === 'thinking'
                ? 'radial-gradient(circle, rgba(139, 92, 246, 0.7) 0%, transparent 80%)'
                : 'radial-gradient(circle, rgba(245, 158, 11, 0.4) 0%, transparent 80%)',
          }}
        />

        {/* Specular gloss highlight */}
        <div
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{
            background:
              'radial-gradient(ellipse at 32% 26%, rgba(255, 255, 255, 0.45) 0%, rgba(255, 255, 255, 0.1) 35%, transparent 65%)',
          }}
        />

        {/* Floating frosted glass state indicator badge */}
        <div className="absolute bottom-3.5 z-20 flex items-center gap-1.5 px-3 py-1 rounded-full bg-black/55 backdrop-blur-md border border-amber-400/40 text-amber-200 text-xs font-medium shadow-lg select-none">
          {state === 'listening' ? (
            <motion.div
              className="flex items-center gap-1.5"
              animate={shouldReduceMotion ? {} : { scale: [1, 1.08 + clampedLevel * 0.2, 1] }}
              transition={{ duration: 0.8, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Mic className="w-3.5 h-3.5 text-amber-300 fill-amber-300/30" />
              <span>Listening</span>
            </motion.div>
          ) : state === 'thinking' ? (
            <motion.div
              className="flex items-center gap-1.5"
              animate={shouldReduceMotion ? {} : { rotate: [0, 5, -5, 0] }}
              transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Sprout className="w-3.5 h-3.5 text-amber-300 animate-spin" />
              <span>Reflecting</span>
            </motion.div>
          ) : state === 'speaking' ? (
            <motion.div
              className="flex items-center gap-1.5"
              animate={shouldReduceMotion ? {} : { scale: [1, 1.06, 1] }}
              transition={{ duration: 1.1, repeat: Infinity, ease: 'easeInOut' }}
            >
              <Volume2 className="w-3.5 h-3.5 text-amber-300" />
              <span>Speaking</span>
            </motion.div>
          ) : (
            <div className="flex items-center gap-1.5 text-amber-200/80">
              <Pause className="w-3.5 h-3.5 opacity-75" />
              <span>Paused</span>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
};
