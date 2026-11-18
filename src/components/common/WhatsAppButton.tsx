import React from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export interface WhatsAppButtonProps {
  className?: string;
  variant?: 'icon' | 'pill';
  'data-testid'?: string;
  phone?: string;
  text?: string;
}

export const WhatsAppIcon = ({ className = 'w-5 h-5' }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L0 24l6.335-1.662c1.746.953 3.71 1.455 5.711 1.456h.005c6.554 0 11.89-5.336 11.893-11.893a11.821 11.821 0 00-3.48-8.414z" />
  </svg>
);

export const WhatsAppButton: React.FC<WhatsAppButtonProps> = ({
  className,
  variant = 'icon',
  'data-testid': testId = 'whatsapp-action-button',
  phone,
  text = 'Namaste Mukthi Guru',
}) => {
  const { t } = useTranslation();
  const label = t('chat.chatOnWhatsApp', 'Chat on WhatsApp');

  const rawNumber = (phone || import.meta.env.VITE_WHATSAPP_NUMBER || '+918008888888').trim();
  const cleanNumber = rawNumber.replace(/[^0-9]/g, '');
  const encodedText = text ? encodeURIComponent(text) : '';
  const whatsappUrl = cleanNumber
    ? `https://wa.me/${cleanNumber}${encodedText ? `?text=${encodedText}` : ''}`
    : `https://wa.me/${encodedText ? `?text=${encodedText}` : ''}`;

  const baseClasses =
    'min-h-[44px] min-w-[44px] inline-flex items-center justify-center transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2';

  if (variant === 'pill') {
    return (
      <a
        href={whatsappUrl}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          baseClasses,
          'gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/20 active:scale-95 shadow-xs',
          className,
        )}
        aria-label={label}
        title={label}
        data-testid={testId}
      >
        <WhatsAppIcon className="w-4 h-4 fill-current shrink-0" />
        <span>{label}</span>
      </a>
    );
  }

  return (
    <a
      href={whatsappUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        baseClasses,
        'rounded-xl text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300 hover:bg-emerald-500/10 active:scale-95',
        className,
      )}
      aria-label={label}
      title={label}
      data-testid={testId}
    >
      <WhatsAppIcon className="w-5 h-5 fill-current" />
    </a>
  );
};

export default WhatsAppButton;
