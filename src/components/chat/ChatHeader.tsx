import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Plus, PanelLeft, Wifi, WifiOff, Home, Flame, Heart } from 'lucide-react';
import { checkConnection } from '@/lib/aiService';
import { derivePrePracticeInsights } from '@/lib/profileStorage';
import gurusPhoto from '@/assets/gurus-photo.jpg';
import { UserMenu } from '@/components/common/UserMenu';
import { useProfile } from '@/hooks/useProfile';
import { Button } from '@/components/ui/button';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
  onToggleSidebar?: () => void;
}

const formatRelativeTime = (iso: string | null): string => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
};

const favouriteLabel = (fav: 'soul_sync' | 'serene_mind' | null): string => {
  if (fav === 'soul_sync') return 'Soul Sync';
  if (fav === 'serene_mind') return 'Serene Mind';
  return '';
};

export const ChatHeader = ({ onClearChat, onOpenMobileMenu, onToggleSidebar }: ChatHeaderProps) => {
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; mode: string }>({
    connected: true,
    mode: 'Offline Mode',
  });
  const { profile } = useProfile();

  const insights = useMemo(
    () => derivePrePracticeInsights(profile.prePracticeLog),
    [profile.prePracticeLog],
  );

  useEffect(() => {
    const checkStatus = async () => {
      const status = await checkConnection();
      setConnectionStatus(status);
    };

    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const hasInsights = insights.totalAsked > 0;

  return (
    <header className="relative z-20 sticky top-0 backdrop-blur-md bg-background/70 border-b border-border/60">
      <div className="flex items-center justify-between px-3 sm:px-5 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          {/* Home button */}
          <Link
            to="/"
            className="h-9 w-9 flex items-center justify-center rounded-lg hover:bg-muted transition-colors"
            title="Home"
          >
            <Home className="w-4 h-4 text-muted-foreground" />
          </Link>

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
              <div className="flex items-center gap-2">
                <h1 className="font-medium text-foreground text-sm truncate leading-tight">
                  Sri Preethaji & Sri Krishnaji
                </h1>
                {/* Mobile-only streak badge */}
                {hasInsights && insights.streakPrepared > 0 && (
                  <span className="sm:hidden inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-ojas/15 text-[10px] font-semibold text-ojas border border-ojas/25">
                    <Flame className="w-2.5 h-2.5" />
                    {insights.streakPrepared}
                  </span>
                )}
              </div>
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

      {/* Desktop insight strip */}
      {hasInsights && (
        <div className="hidden sm:flex items-center justify-center gap-3 px-5 pb-2 -mt-0.5">
          <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
            {insights.streakPrepared > 0 && (
              <span className="inline-flex items-center gap-1">
                <Flame className="w-3 h-3 text-ojas" />
                <span className="font-medium text-foreground">{insights.streakPrepared}</span>
                <span>day streak</span>
              </span>
            )}
            {insights.favourite && (
              <span className="inline-flex items-center gap-1">
                <Heart className="w-3 h-3 text-ojas" />
                <span>{favouriteLabel(insights.favourite)}</span>
              </span>
            )}
            {profile.prePracticeLog?.lastAnsweredAt && (
              <span className="inline-flex items-center gap-1">
                <span>Last:</span>
                <span className="font-medium text-foreground">
                  {formatRelativeTime(profile.prePracticeLog.lastAnsweredAt)}
                </span>
              </span>
            )}
          </div>
        </div>
      )}
    </header>
  );
};
