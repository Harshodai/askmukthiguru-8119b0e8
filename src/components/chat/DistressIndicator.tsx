import { useCallback } from 'react';
import { cn } from '@/lib/utils';

/**
 * Distress severity levels detected by the backend safety layer.
 * - `none`   — no distress signal; component renders nothing.
 * - `low`    — mild unease; gentle check-in.
 * - `moderate` — visible distress; offer a calming practice.
 * - `high`   — acute distress; offer a breathing exercise + helpline path.
 */
export type DistressLevel = 'none' | 'low' | 'moderate' | 'high';

export interface DistressIndicatorProps {
  /** Detected distress level. `none` renders nothing. */
  level: DistressLevel;
  /** Fired when the seeker accepts the offered help (e.g. opens Serene Mind). */
  onOfferHelp: () => void;
  /** Optional override of the offer CTA label. */
  ctaLabel?: string;
  /** Extra className for the outer container. */
  className?: string;
}

interface LevelConfig {
  /** Soft background tint (warm sand / terracotta family). */
  containerClass: string;
  /** Pulsing dot color. */
  dotClass: string;
  /** Empathetic copy shown to the seeker. */
  text: string;
}

const LEVEL_CONFIG: Record<Exclude<DistressLevel, 'none'>, LevelConfig> = {
  low: {
    containerClass: 'bg-[#D4A574]/10 border-[#D4A574]/30',
    dotClass: 'bg-[#D4A574]',
    text: 'I sense some unease. Would you like to talk?',
  },
  moderate: {
    containerClass: 'bg-[#D4A574]/15 border-[#D4A574]/40',
    dotClass: 'bg-[#C9A96E]',
    text: 'You seem distressed. Can I help with a calming practice?',
  },
  high: {
    containerClass: 'bg-[#C47065]/12 border-[#C47065]/40',
    dotClass: 'bg-[#C47065]',
    text: "I'm here for you. Would you like to try a breathing exercise?",
  },
};

/**
 * DistressIndicator — a warm, non-alarming banner that surfaces when the
 * backend safety classifier detects emotional distress in the seeker's
 * message. Offers a gentle help CTA that the host wires to Serene Mind /
 * breathing exercise / helpline.
 *
 * Uses the `serene.*` color tokens via inline hex fallbacks so the component
 * is self-sufficient even if the Tailwind `serene` namespace is absent.
 *
 * @see DistressIndicatorProps
 */
export function DistressIndicator({
  level,
  onOfferHelp,
  ctaLabel = 'Yes',
  className,
}: DistressIndicatorProps) {
  const handleOfferHelp = useCallback(() => {
    onOfferHelp();
  }, [onOfferHelp]);

  if (level === 'none') return null;

  const config = LEVEL_CONFIG[level];

  const isHigh = level === 'high';

  return (
    <div
      role="alert"
      aria-live={isHigh ? 'assertive' : 'polite'}
      aria-atomic={isHigh}
      className={cn(
        'animate-slide-up rounded-xl p-4 mb-4 flex items-center gap-4 border',
        config.containerClass,
        className,
      )}
    >
      <div
        className={cn(
          'w-3 h-3 rounded-full animate-pulse-soft flex-shrink-0',
          config.dotClass,
        )}
        aria-hidden
      />
      <p className="text-sm text-[#2C2420] dark:text-[#F0EBE3] flex-1 leading-relaxed">
        {config.text}
      </p>
      <button
        type="button"
        onClick={handleOfferHelp}
        className="px-4 py-2 bg-white dark:bg-[#2C2420] rounded-full text-sm font-medium text-[#2C2420] dark:text-[#F0EBE3] shadow-sm hover:shadow-md transition-shadow flex-shrink-0"
      >
        {ctaLabel}
      </button>
    </div>
  );
}

export default DistressIndicator;