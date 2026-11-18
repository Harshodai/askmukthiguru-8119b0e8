import React from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface EkamLinkButtonProps {
  className?: string;
  variant?: 'icon' | 'pill' | 'text';
  'data-testid'?: string;
  children?: React.ReactNode;
}

export const EkamLotusIcon = ({ className = 'w-4 h-4' }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    {/* Central upward petal of enlightenment */}
    <path d="M12 2.5c-.8 2.2-2.2 5.2-2.2 8.5 0 2.8 1 4.5 2.2 5 1.2-.5 2.2-2.2 2.2-5 0-3.3-1.4-6.3-2.2-8.5z" />
    {/* Left rising petal */}
    <path d="M8.2 11.2c-1.8-2-3.8-3-5.2-2.7.2 3.6 2.3 6.6 5.5 7.5-.4-1.6-.5-3.3-.3-4.8z" opacity="0.85" />
    {/* Right rising petal */}
    <path d="M15.8 11.2c1.8-2 3.8-3 5.2-2.7-.2 3.6-2.3 6.6-5.5 7.5.4-1.6.5-3.3.3-4.8z" opacity="0.85" />
    {/* Left outer cradle */}
    <path d="M5.8 17.2c-1.5-.4-2.8-1.2-3.8-2.2 1.2 3.2 4.2 5.4 7.8 5.8-1.7-.8-3.1-2-4-3.6z" opacity="0.7" />
    {/* Right outer cradle */}
    <path d="M18.2 17.2c1.5-.4 2.8-1.2 3.8-2.2-1.2 3.2-4.2 5.4-7.8 5.8 1.7-.8 3.1-2 4-3.6z" opacity="0.7" />
    {/* Sacred lotus base of oneness */}
    <path d="M12 17.5c-1.8 0-3.5.5-4.8 1.4 1.4 1.3 3.1 2.1 4.8 2.1s3.4-.8 4.8-2.1c-1.3-.9-3-1.4-4.8-1.4z" opacity="0.9" />
  </svg>
);

export const EkamLinkButton: React.FC<EkamLinkButtonProps> = ({
  className,
  variant = 'icon',
  'data-testid': testId = 'ekam-link-button',
  children,
}) => {
  const { t } = useTranslation();
  const label = t('common.visitEkam', 'Visit Ekam World Centre');

  const baseClasses =
    'min-h-[44px] min-w-[44px] inline-flex items-center justify-center transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2';

  if (variant === 'pill') {
    return (
      <a
        href="https://www.ekam.org"
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          baseClasses,
          'gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-medium',
          'text-ojas-ink dark:text-ojas bg-ojas/10 border border-ojas/25',
          'hover:bg-ojas/20 hover:border-ojas/40 active:scale-95 shadow-xs',
          className,
        )}
        aria-label={label}
        title={label}
        data-testid={testId}
      >
        <EkamLotusIcon className="w-4 h-4 fill-current shrink-0 text-ojas" />
        {children || (
          <>
            <span className="font-semibold tracking-wide">Ekam</span>
            <span className="hidden sm:inline text-muted-foreground/80 font-normal">· World Centre</span>
          </>
        )}
        <ExternalLink className="w-3 h-3 text-ojas/70 shrink-0" aria-hidden="true" />
      </a>
    );
  }

  if (variant === 'text') {
    return (
      <a
        href="https://www.ekam.org"
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          'min-h-[44px] inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium',
          'text-foreground hover:text-ojas transition-colors duration-200 ease-out active:scale-95',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas focus-visible:ring-offset-2',
          className,
        )}
        aria-label={label}
        title={label}
        data-testid={testId}
      >
        <EkamLotusIcon className="w-4 h-4 fill-current shrink-0 text-ojas" />
        <span>{children || t('common.ekamWorldCentre', 'Ekam · World Centre for Enlightenment')}</span>
        <ExternalLink className="w-3 h-3 text-muted-foreground/70 shrink-0" aria-hidden="true" />
      </a>
    );
  }

  return (
    <a
      href="https://www.ekam.org"
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        baseClasses,
        'rounded-xl text-ojas hover:text-ojas-light hover:bg-ojas/10 border border-transparent hover:border-ojas/20 active:scale-95',
        className,
      )}
      aria-label={label}
      title={label}
      data-testid={testId}
    >
      <EkamLotusIcon className="w-5 h-5 fill-current" />
    </a>
  );
};

export default EkamLinkButton;
