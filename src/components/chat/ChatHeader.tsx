import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { PanelLeft, PanelLeftClose, Wifi, WifiOff, Home } from 'lucide-react';
import { checkConnection } from '@/lib/aiService';
import { UserMenu } from '@/components/common/UserMenu';
import { Button } from '@/components/ui/button';
import gurusPhoto from '@/assets/gurus-photo.jpg';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

export const ChatHeader = ({ onClearChat, onOpenMobileMenu, sidebarCollapsed, onToggleSidebar }: ChatHeaderProps) => {
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; mode: string }>({
    connected: true,
    mode: 'Offline Mode',
  });

  useEffect(() => {
    const checkStatus = async () => {
      const status = await checkConnection();
      setConnectionStatus(status);
    };
    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="relative z-20 sticky top-0 backdrop-blur-md bg-background/80 border-b border-border/40">
      <div className="flex items-center justify-between px-3 sm:px-5 h-11">
        <div className="flex items-center gap-2 min-w-0">
          {/* Sidebar toggle — desktop */}
          {onToggleSidebar && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onToggleSidebar}
              className="hidden sm:flex h-8 w-8"
              aria-label={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
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

          {/* Guru avatar */}
          <div className="w-7 h-7 rounded-full overflow-hidden border border-ojas/30 flex-shrink-0">
            <img
              src={gurusPhoto}
              alt="Sri Preethaji & Sri Krishnaji"
              className="w-full h-full object-cover"
            />
          </div>

          <div className="flex flex-col min-w-0">
            <button className="flex items-center gap-1.5 group">
              <h1 className="font-semibold text-foreground text-base truncate leading-tight">
                Mukthi Guru
              </h1>
              <PanelLeft className="w-4 h-4 text-muted-foreground group-hover:text-foreground transition-colors rotate-270" />
            </button>
            <p className="text-[10px] text-muted-foreground/60 leading-tight hidden sm:block">
              Spiritual Guide
            </p>
          </div>
        </div>

        <UserMenu />
      </div>
    </header>
  );
};
