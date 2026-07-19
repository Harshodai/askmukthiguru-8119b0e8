import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { PanelLeft, PanelLeftClose, Home, Download, Library, EyeOff } from 'lucide-react';
import { UserMenu } from '@/components/common/UserMenu';
import { Button } from '@/components/ui/button';

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
}

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
}: ChatHeaderProps) => {
  const { t } = useTranslation();

  return (
    <header className={`relative z-20 sticky top-0 backdrop-blur-md border-b border-border/30 h-[56px] sm:h-[64px] safe-top ${isIncognito ? 'bg-amber-950/15' : 'bg-background/85 bg-gradient-to-r from-ojas/5 to-transparent'}`} data-testid="chat-header-simplified">
      <div className="flex items-center justify-between px-3 sm:px-5 h-[52px]">
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
          {onToggleSidebar && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onToggleSidebar}
              className="hidden sm:flex h-8 w-8"
              aria-label={sidebarCollapsed ? t('chat.openSidebar') : t('chat.closeSidebar')}
              aria-expanded={!sidebarCollapsed}
              aria-controls="sidebar-panel"
              title={sidebarCollapsed ? t('chat.openSidebar') : t('chat.closeSidebar')}
            >
              {sidebarCollapsed ? (
                <PanelLeft className="w-4 h-4 text-muted-foreground" />
              ) : (
                <PanelLeftClose className="w-4 h-4 text-muted-foreground" />
              )}
            </Button>
          )}

          <Link
            to="/"
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-muted transition-colors"
            title={t('nav.home')}
            aria-label={t('chat.homeAria')}
          >
            <Home className="w-4 h-4 text-muted-foreground" />
          </Link>

          {onOpenMobileMenu && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onOpenMobileMenu}
              className="sm:hidden h-8 w-8"
              aria-label={t('chat.openConversations')}
            >
              <PanelLeft className="w-4 h-4" />
            </Button>
          )}

          {isIncognito ? (
            <div className="flex items-center gap-2 ml-1">
              <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border border-amber-600/40 bg-amber-950/20 text-amber-600 text-[11px] font-medium">
                <EyeOff className="w-3 h-3" />
                {t('chat.incognito')}
              </div>
              {onCloseIncognito && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onCloseIncognito}
                  className="h-7 text-[11px] text-muted-foreground hover:text-foreground px-2"
                >
                  {t('chat.closeIncognito')}
                </Button>
              )}
            </div>
          ) : (
            <span
              className={`flex items-center gap-1.5 font-serif font-semibold text-foreground text-sm ml-1 select-none ${sidebarCollapsed ? '' : 'md:hidden'}`}
              data-testid="chat-header-wordmark"
            >
              <span className="text-sm leading-none" aria-hidden="true">🙏</span>
              {t('nav.appName')}
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          {isIncognito && (
            <span className="text-[10px] text-amber-600/70 hidden sm:block mr-1">{t('chat.incognitoDescription')}</span>
          )}
          {hasMessages && onOpenSources && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onOpenSources}
              className="h-8 w-8 text-muted-foreground hover:text-foreground relative"
              aria-label={t('chat.openSources', { count: sourcesCount })}
              title={t('chat.viewSources')}
            >
              <Library className="w-4 h-4" />
              {sourcesCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-ojas/15 text-ojas text-[10px] font-semibold tabular-nums">
                  {sourcesCount}
                </span>
              )}
            </Button>
          )}
          {hasMessages && onExport && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onExport}
              className="h-8 w-8 hidden sm:flex text-muted-foreground"
              aria-label={t('chat.exportMarkdown')}
              title={t('chat.exportMarkdown')}
            >
              <Download className="w-4 h-4" />
            </Button>
          )}
          <div className={sidebarCollapsed ? '' : 'md:hidden'}>
            <UserMenu />
          </div>
        </div>
      </div>
    </header>
  );
};