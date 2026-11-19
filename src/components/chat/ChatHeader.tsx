import { useChatCapabilities } from '@/hooks/useChatCapabilities';
import '@/styles/mobile-chat-ux.css';
import '@/styles/product-ux.css';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { PanelLeft, PanelLeftClose, Home, Download, Library, EyeOff, Sparkles, AudioLines } from 'lucide-react';
import { UserMenu } from '@/components/common/UserMenu';
import { ResponsePreferencesMenu } from './ResponsePreferencesMenu';
import type { ResponsePreferences } from '@/lib/chat/types';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
  onExport?: () => void;
  onOpenSources?: () => void;
  sourcesCount?: number;
  hasMessages?: boolean;
  isIncognito?: boolean;
  onCloseIncognito?: () => void;
  isPersonalized?: boolean;
  isHandsFreeVoice?: boolean;
  responsePreferences?: ResponsePreferences;
  onResponsePreferencesChange?: (value: ResponsePreferences) => void;
  onResetResponsePreferences?: () => void;
  onOpenMemorySettings?: () => void;
  /** null = consent not loaded yet: show no memory badge rather than "Paused". */
  memoryActive?: boolean | null;
  onOpenVoiceMode?: () => void;
}

const WhatsAppIcon = ({ className = "w-4 h-4" }: { className?: string }) => (
  <svg
    viewBox="0 0 24 24"
    fill="currentColor"
    className={className}
    aria-hidden="true"
  >
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L0 24l6.335-1.662c1.746.953 3.71 1.455 5.711 1.456h.005c6.554 0 11.89-5.336 11.893-11.893a11.821 11.821 0 00-3.48-8.414z" />
  </svg>
);

export const ChatHeader = ({
  onOpenMobileMenu,
  sidebarCollapsed,
  onToggleSidebar,
  onExport,
  onOpenSources,
  sourcesCount = 0,
  hasMessages = false,
  isIncognito = false,
  onCloseIncognito,
  isPersonalized = false,
  isHandsFreeVoice = false,
  responsePreferences,
  onResponsePreferencesChange,
  onResetResponsePreferences,
  onOpenMemorySettings,
  memoryActive = false,
  onOpenVoiceMode,
}: ChatHeaderProps) => {
  const { t } = useTranslation();
  const { capabilities } = useChatCapabilities();
  const rawWhatsApp = (import.meta.env.VITE_WHATSAPP_NUMBER || '').trim();
  const whatsappNumber = rawWhatsApp.replace(/[^0-9]/g, '');
  const whatsappUrl = whatsappNumber
    ? `https://wa.me/${whatsappNumber}?text=Namaste%20Mukthi%20Guru`
    : 'https://wa.me/?text=Namaste%20Mukthi%20Guru';

  return <header className={`relative z-20 sticky top-0 backdrop-blur-md border-b border-border/30 h-[56px] sm:h-[64px] safe-top ${isIncognito ? 'bg-amber-950/15' : 'bg-background/85 bg-gradient-to-r from-ojas/5 to-transparent'}`} data-testid="chat-header-simplified">
    <div className="flex items-center justify-between px-2.5 sm:px-5 h-full">
      <div className="flex items-center gap-1 sm:gap-2 min-w-0">
        {onOpenMobileMenu && <Button size="icon" variant="ghost" onClick={onOpenMobileMenu} data-tour="mobile-menu" className="sm:hidden min-h-[44px] min-w-[44px] h-10 w-10 rounded-xl" aria-label={t('chat.openConversations')}><PanelLeft className="w-4 h-4" /></Button>}
        {onToggleSidebar && <Button size="icon" variant="ghost" onClick={onToggleSidebar} className="hidden sm:flex min-h-[44px] min-w-[44px] sm:h-8 sm:w-8" aria-label={sidebarCollapsed ? t('chat.openSidebar') : t('chat.closeSidebar')} aria-expanded={!sidebarCollapsed} aria-controls="sidebar-panel" title={sidebarCollapsed ? t('chat.openSidebar') : t('chat.closeSidebar')}>{sidebarCollapsed ? <PanelLeft className="w-4 h-4 text-muted-foreground" /> : <PanelLeftClose className="w-4 h-4 text-muted-foreground" />}</Button>}
        <Link to="/" className="hidden sm:flex min-h-[44px] min-w-[44px] items-center justify-center rounded-lg hover:bg-muted transition-colors" title={t('nav.home')} aria-label={t('chat.homeAria')}><Home className="w-4 h-4 text-muted-foreground" /></Link>
        {isIncognito ? (
          <div className="flex items-center gap-2 ml-1 min-w-0">
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-amber-600/40 bg-amber-950/20 text-amber-800 dark:text-amber-400 text-[11px] font-medium whitespace-nowrap"
              title={t('chat.temporaryChatTitle')}
              data-testid="temporary-chat-badge"
            >
              <EyeOff className="w-3 h-3" />
              <span>{t("chat.temporaryChat", "Temporary chat")}</span>
            </div>
            {onCloseIncognito && (
              <Button variant="ghost" size="sm" onClick={onCloseIncognito} className="min-h-[44px] sm:h-7 text-[11px] text-muted-foreground hover:text-foreground px-2">
                {t('chat.closeIncognito')}
              </Button>
            )}
          </div>
        ) : (
          <span className="flex items-center gap-2 font-serif font-semibold text-foreground text-sm ml-1 select-none" data-testid="chat-header-wordmark">
            <span className="flex items-center gap-1.5 truncate">
              <span className="text-sm leading-none" aria-hidden="true">🙏</span>
              <span className="truncate">{t('nav.appName')}</span>
            </span>
            {isPersonalized && memoryActive !== null && (
              onOpenMemorySettings ? (
                <button
                  type="button"
                  onClick={onOpenMemorySettings}
                  className={`hidden sm:inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium whitespace-nowrap transition-colors cursor-pointer hover:border-ojas/40 ${
                    memoryActive
                      ? 'border-ojas/30 bg-ojas/10 text-ojas-ink dark:text-ojas hover:bg-ojas/15'
                      : 'border-border/60 bg-muted/40 text-muted-foreground hover:bg-muted/60'
                  }`}
                  title={t('chat.memorySettings.badgeTitle', 'Spiritual Memory Settings')}
                  aria-label={t('chat.memorySettings.badgeTitle', 'Spiritual Memory Settings')}
                  data-testid="personalization-badge"
                >
                  <Sparkles className={`w-3 h-3 ${memoryActive ? 'text-ojas' : 'text-muted-foreground'}`} />
                  <span>{memoryActive ? t('chat.memoryActive', 'Memory Active') : t('chat.memoryPaused', 'Memory Paused')}</span>
                </button>
              ) : (
                <span
                  className="hidden sm:inline-flex items-center gap-1 rounded-full border border-ojas/20 bg-ojas/5 px-2 py-0.5 text-[10px] font-medium text-ojas-ink dark:text-ojas whitespace-nowrap"
                  title={t('chat.personalizedTitle')}
                  data-testid="personalization-badge"
                >
                  <Sparkles className="w-3 h-3" />
                  {t('chat.personalized')}
                </span>
              )
            )}
            {isHandsFreeVoice && (
              <span
                className="hidden sm:inline-flex items-center gap-1 rounded-full border border-ojas/20 bg-ojas/5 px-2 py-0.5 text-[10px] font-medium text-ojas-ink dark:text-ojas whitespace-nowrap"
                data-testid="voice-conversation-badge"
              >
                <AudioLines className="w-3 h-3" />
                {t('chat.voiceMode')}
              </span>
            )}
          </span>
        )}
      </div>
      <div className="flex items-center gap-0.5 sm:gap-1.5">
        {responsePreferences && onResponsePreferencesChange && onResetResponsePreferences && <div className="hidden sm:block"><ResponsePreferencesMenu value={responsePreferences} onChange={onResponsePreferencesChange} onReset={onResetResponsePreferences} /></div>}
        {isIncognito && <span className="text-[10px] text-amber-600/70 hidden sm:block mr-1">{t('chat.incognitoScope', 'Not saved to history, personal memory, or your personal wisdom map.')}</span>}
        {hasMessages && onOpenSources && (
          <Button
            size="icon"
            variant="ghost"
            onClick={onOpenSources}
            className={cn(
              "min-h-[44px] min-w-[44px] h-10 w-10 sm:h-8 sm:w-8 relative flex items-center justify-center rounded-xl transition-all",
              sourcesCount > 0
                ? "text-ojas hover:text-ojas hover:bg-ojas/10 border border-ojas/20"
                : "text-muted-foreground hover:text-foreground"
            )}
            aria-label={t('chat.openSources', { count: sourcesCount })}
            title={t('chat.viewSources', 'View cited sources and teachings')}
            data-testid="header-sources-button"
          >
            <Library className="w-4 h-4" />
            {sourcesCount > 0 && (
              <span className="absolute -top-1 -right-1 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-ojas text-primary-foreground text-[10px] font-bold tabular-nums shadow-xs">
                {sourcesCount}
              </span>
            )}
          </Button>
        )}
        {hasMessages && onExport && <Button size="icon" variant="ghost" onClick={onExport} className="min-h-[44px] min-w-[44px] sm:h-8 sm:w-8 hidden sm:flex text-muted-foreground items-center justify-center" aria-label={t('chat.exportMarkdown')} title={t('chat.exportMarkdown')}><Download className="w-4 h-4" /></Button>}
        <a
          href={whatsappUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="min-h-[44px] min-w-[44px] h-10 w-10 sm:h-8 sm:w-8 text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300 transition-colors flex items-center justify-center rounded-xl hover:bg-emerald-500/10"
          aria-label={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
          title={t('chat.chatOnWhatsApp', 'Chat on WhatsApp')}
          data-testid="whatsapp-action-button"
        >
          <WhatsAppIcon className="w-5 h-5 fill-current" />
        </a>
        <div className={cn('flex items-center flex-shrink-0', sidebarCollapsed ? '' : 'sm:hidden')}>
          <UserMenu />
        </div>
      </div>
    </div>
  </header>;
};
