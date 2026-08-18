import React from 'react';
import { Sparkles, Bot, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { OriginType, AIProvenanceManifest } from '@/types/provenance';

export interface EuAiBadgeProps {
  originType?: OriginType;
  onClick?: () => void;
  className?: string;
  size?: 'sm' | 'md';
  showLabel?: boolean;
  manifest?: AIProvenanceManifest;
}

export const EuAiBadge: React.FC<EuAiBadgeProps> = ({
  originType = 'ai_generated',
  onClick,
  className,
  size = 'sm',
  showLabel = true,
}) => {
  const isClickable = Boolean(onClick);

  const getLabel = () => {
    switch (originType) {
      case 'ai_assisted':
        return 'AI Assisted';
      case 'human_generated':
        return 'Human Authored';
      case 'ai_generated':
      default:
        return 'AI Generated';
    }
  };

  const getIcon = () => {
    switch (originType) {
      case 'ai_assisted':
        return <Bot className={cn(size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5', 'text-ojas shrink-0')} aria-hidden="true" />;
      case 'human_generated':
        return <ShieldCheck className={cn(size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5', 'text-ojas shrink-0')} aria-hidden="true" />;
      case 'ai_generated':
      default:
        return <Sparkles className={cn(size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5', 'text-ojas shrink-0')} aria-hidden="true" />;
    }
  };

  const ariaLabel = `${getLabel()} content - EU AI Act Article 50 Disclosure`;

  const badgeContent = (
    <>
      {getIcon()}
      {showLabel && (
        <span className="font-medium tracking-tight whitespace-nowrap">
          {getLabel()}
        </span>
      )}
      <span className="sr-only"> - Click to view EU AI Act Article 50 provenance manifest</span>
    </>
  );

  const baseClasses = cn(
    'inline-flex items-center gap-1.5 rounded-full font-sans transition-all duration-200 select-none',
    'border border-ojas/25 bg-ojas/5 dark:bg-ojas/10 text-ojas dark:text-ojas-light',
    'hover:border-ojas/50 hover:bg-ojas/10 dark:hover:bg-ojas/20 hover:shadow-[0_0_12px_rgba(217,119,6,0.25)]',
    size === 'sm' ? 'px-2 py-0.5 text-[11px] leading-4' : 'px-2.5 py-1 text-xs leading-5',
    isClickable && 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas/60 focus-visible:ring-offset-1',
    className
  );

  if (isClickable) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={baseClasses}
        aria-label={ariaLabel}
        data-testid="eu-ai-badge"
        title="EU AI Act Article 50 Disclosure · Click for machine-readable provenance"
      >
        {badgeContent}
      </button>
    );
  }

  return (
    <span
      className={baseClasses}
      aria-label={ariaLabel}
      data-testid="eu-ai-badge"
      role="status"
      title="EU AI Act Article 50 Disclosure"
    >
      {badgeContent}
    </span>
  );
};
