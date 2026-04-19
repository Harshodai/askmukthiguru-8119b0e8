import { useState, useEffect } from 'react';
import { Plus, PanelLeft, Wifi, WifiOff } from 'lucide-react';
import { checkConnection } from '@/lib/aiService';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { UserMenu } from '@/components/common/UserMenu';
import { Button } from '@/components/ui/button';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
  onToggleSidebar?: () => void;
}

export const ChatHeader = ({ onClearChat, onOpenMobileMenu, onToggleSidebar }: ChatHeaderProps) => {
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
    <header className="relative z-20 sticky top-0 backdrop-blur-md bg-background/70 border-b border-border/60">
      <div className="flex items-center justify-between px-3 sm:px-5 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {onOpenMobileMenu && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onOpenMobileMenu}
              className="sm:hidden h-9 w-9"
              aria-label="Open conversations"
            >
              <PanelLeft className="w-4 h-4" />
            </Button>
          )}

          {onToggleSidebar && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onToggleSidebar}
              className="hidden sm:flex h-9 w-9"
              aria-label="Toggle sidebar"
              title="Toggle sidebar"
            >
              <PanelLeft className="w-4 h-4" />
            </Button>
          )}

          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-9 h-9 rounded-full overflow-hidden ring-1 ring-ojas/30 shadow-sm shrink-0">
              <img
                src={gurusPhoto}
                alt="Sri Preethaji & Sri Krishnaji"
                className="w-full h-full object-cover"
              />
            </div>
            <div className="min-w-0">
              <h1 className="font-medium text-foreground text-sm truncate leading-tight">
                Sri Preethaji & Sri Krishnaji
              </h1>
              <div className="flex items-center gap-1.5">
                {connectionStatus.connected ? (
                  <Wifi className="w-3 h-3 text-prana" />
                ) : (
                  <WifiOff className="w-3 h-3 text-muted-foreground" />
                )}
                <p className="text-[11px] text-muted-foreground leading-none">
                  {connectionStatus.mode}
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onClearChat}
            className="gap-1.5 h-9"
            title="Start new conversation"
          >
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline text-xs">New chat</span>
          </Button>
          <UserMenu />
        </div>
      </div>
    </header>
  );
};
