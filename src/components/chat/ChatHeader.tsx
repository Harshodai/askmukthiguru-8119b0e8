import { Link } from 'react-router-dom';
import { PanelLeft, PanelLeftClose, Home, Sparkles, Download, Library } from 'lucide-react';
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
}

export const ChatHeader = ({ onOpenMobileMenu, sidebarCollapsed, onToggleSidebar, onExport, onOpenSources, sourcesCount = 0 }: ChatHeaderProps) => {
  return (
    <header className="relative z-20 sticky top-0 backdrop-blur-md bg-background/85 border-b border-border/40" data-testid="chat-header-simplified">
      <div className="flex items-center justify-between px-3 sm:px-5 h-[52px]">
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
          {onToggleSidebar && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onToggleSidebar}
              className="hidden sm:flex h-8 w-8"
              aria-label={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
              aria-expanded={!sidebarCollapsed}
              aria-controls="sidebar-panel"
              title={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
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
            title="Home"
            aria-label="AskMukthiGuru home"
          >
            <Home className="w-4 h-4 text-muted-foreground" />
          </Link>

          {onOpenMobileMenu && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onOpenMobileMenu}
              className="sm:hidden h-8 w-8"
              aria-label="Open conversations"
            >
              <PanelLeft className="w-4 h-4" />
            </Button>
          )}

          <span className="flex items-center gap-1.5 font-serif font-semibold text-foreground text-sm ml-1 select-none" data-testid="chat-header-wordmark">
            <Sparkles className="w-3.5 h-3.5 text-ojas" />
            AskMukthiGuru
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {onOpenSources && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onOpenSources}
              className="h-8 w-8 text-muted-foreground hover:text-foreground relative"
              aria-label={`Open sources panel (${sourcesCount} ${sourcesCount === 1 ? 'source' : 'sources'})`}
              title="View all sources cited in this conversation"
            >
              <Library className="w-4 h-4" />
              {sourcesCount > 0 && (
                <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-ojas/15 text-ojas text-[9px] font-semibold tabular-nums">
                  {sourcesCount}
                </span>
              )}
            </Button>
          )}
          {onExport && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onExport}
              className="h-8 w-8 hidden sm:flex text-muted-foreground"
              aria-label="Export conversation as Markdown"
              title="Export conversation as Markdown"
            >
              <Download className="w-4 h-4" />
            </Button>
          )}
          <UserMenu />
        </div>
      </div>
    </header>
  );
};
