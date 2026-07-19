import { useCallback } from 'react';
import { cn } from '@/lib/utils';

export interface TeachingCardProps {
  /** Teaching title (e.g. "The Art of Dying"). */
  title: string;
  /** Short excerpt / abstract shown beneath the title. */
  excerpt: string;
  /** Teacher or source attribution (e.g. "Preethaji"). */
  teacher: string;
  /** Category tag (e.g. "Meditation", "Wisdom"). */
  category: string;
  /** Fired when the seeker clicks "Read more". */
  onReadMore: () => void;
  /** Extra className for the outer card. */
  className?: string;
}

/**
 * TeachingCard — a warm-sand content card for surfacing teachings, excerpts,
 * and wisdom entries. Features a gradient top bar (warm sand → gold) and a
 * hover-lift shadow. Uses `serene.*` palette via inline hex fallbacks so the
 * component is self-sufficient even if the Tailwind `serene` namespace is
 * absent.
 *
 * @see TeachingCardProps
 */
export function TeachingCard({
  title,
  excerpt,
  teacher,
  category,
  onReadMore,
  className,
}: TeachingCardProps) {
  const handleClick = useCallback(() => {
    onReadMore();
  }, [onReadMore]);

  return (
    <div
      className={cn(
        'group bg-sacred-sand dark:bg-[#2C2420] rounded-xl shadow-md hover:shadow-lg transition-shadow duration-300 overflow-hidden border border-[#E8E0D8]/60',
        className,
      )}
    >
      {/* Gradient top bar — warm sand → gold */}
      <div
        className="h-2 bg-gradient-to-r from-[#D4A574] to-[#C9A96E]"
        aria-hidden
      />
      <div className="p-6">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-xs font-medium text-[#D4A574] bg-[#D4A574]/10 px-3 py-1 rounded-full">
            {category}
          </span>
          <span className="text-xs text-[#9B8E84] truncate">{teacher}</span>
        </div>
        <h3 className="text-[20px] font-semibold leading-snug text-[#2C2420] dark:text-[#F0EBE3] mb-2 group-hover:text-[#D4A574] transition-colors">
          {title}
        </h3>
        <p className="text-sm text-[#6B5E54] dark:text-[#B8A99A] mb-4 line-clamp-3 leading-relaxed">
          {excerpt}
        </p>
        <button
          type="button"
          onClick={handleClick}
          className="text-sm font-medium text-[#D4A574] hover:text-[#B8935F] transition-colors flex items-center gap-1"
        >
          Read more
          <span
            className="transform group-hover:translate-x-1 transition-transform"
            aria-hidden
          >
            →
          </span>
        </button>
      </div>
    </div>
  );
}

export default TeachingCard;