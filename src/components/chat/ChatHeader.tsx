import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PanelLeft, PanelLeftClose, Home, Brain, LogIn } from 'lucide-react';
import { checkConnection } from '@/lib/aiService';
import { UserMenu } from '@/components/common/UserMenu';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { memoryApi, type GuruMemory } from '@/lib/memoryApi';

import { useAuthStatus } from '@/hooks/useAuthStatus';
import gurusPhoto from '@/assets/gurus-photo.jpg';

interface ChatHeaderProps {
  onClearChat: () => void;
  onOpenMobileMenu?: () => void;
  sidebarCollapsed?: boolean;
  onToggleSidebar?: () => void;
}

export const ChatHeader = ({ onOpenMobileMenu, sidebarCollapsed, onToggleSidebar }: ChatHeaderProps) => {
  const [connectionStatus, setConnectionStatus] = useState<{ connected: boolean; mode: string }>({
    connected: true,
    mode: 'Offline Mode',
  });
  const [memories, setMemories] = useState<GuruMemory[] | null>(null);
  const { status: authStatus, email } = useAuthStatus();
  const authed = authStatus === 'signed_in';
  const navigate = useNavigate();

  useEffect(() => {
    const checkStatus = async () => {
      const status = await checkConnection();
      setConnectionStatus(status);
    };
    checkStatus();
    const interval = setInterval(checkStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!authed) { setMemories(null); return; }
    (async () => {
      try {
        const list = await memoryApi.list(1, 8);
        if (!cancelled) setMemories(list.memories);
      } catch {
        if (!cancelled) setMemories([]);
      }
    })();
    return () => { cancelled = true; };
  }, [authed]);

  const memoryCount = memories?.length ?? 0;

  return (
    <header className="relative z-20 sticky top-0 backdrop-blur-md bg-background/85 border-b border-border/40">
      <div className="flex items-center justify-between px-3 sm:px-5 h-16">
        <div className="flex items-center gap-2.5 min-w-0">
          {onToggleSidebar && (
            <Button
              size="icon"
              variant="ghost"
              onClick={onToggleSidebar}
              className="hidden sm:flex h-9 w-9"
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

          <div className="w-11 h-11 rounded-full overflow-hidden border-2 border-ojas/30 flex-shrink-0 shadow-sm">
            <img
              src={gurusPhoto}
              alt="Sri Preethaji & Sri Krishnaji"
              className="w-full h-full object-cover"
            />
          </div>

          <div className="flex flex-col min-w-0 leading-tight">
            <h1 className="font-serif font-semibold text-foreground text-[15px] sm:text-base truncate">
              Sri Preethaji &amp; Sri Krishnaji
            </h1>
            <p className="text-[11px] text-muted-foreground/80 hidden sm:block">
              Your Beautiful State companion
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {authed && (
            <Popover>
              <PopoverTrigger asChild>
                <button
                  className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-ojas/25 bg-ojas/5 hover:bg-ojas/10 transition-colors px-2.5 py-1 text-[11px] text-foreground/80"
                  aria-label="Memory"
                  title="What I remember about you"
                >
                  <Brain className="w-3 h-3 text-ojas" />
                  <span className="font-serif">Memory</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="tabular-nums">{memoryCount}</span>
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 p-3">
                <p className="text-xs font-semibold text-foreground mb-2">What I remember</p>
                {memories === null && <p className="text-xs text-muted-foreground">Loading…</p>}
                {memories && memories.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    Nothing yet. Your reflections and key moments will appear here as we converse.
                  </p>
                )}
                {memories && memories.length > 0 && (
                  <ul className="space-y-1.5 max-h-64 overflow-y-auto">
                    {memories.map((m) => (
                      <li key={m.id} className="text-xs text-foreground/85 border-l-2 border-ojas/30 pl-2 py-0.5">
                        {m.claim}
                      </li>
                    ))}
                  </ul>
                )}
                <Link
                  to="/profile?tab=memory"
                  className="block mt-3 text-[11px] text-ojas hover:underline"
                >
                  Manage memory →
                </Link>
              </PopoverContent>
            </Popover>
          )}
          {/* Auth status pill */}
          {authStatus !== 'loading' && (
            authStatus === 'session_expired' ? (
              <button
                type="button"
                onClick={() => navigate('/auth?redirect=/chat')}
                className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 transition-colors px-2.5 py-1 text-[11px] text-amber-600 dark:text-amber-400"
                title="Your session expired — sign in again"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                <span className="hidden sm:inline">Session expired</span>
                <LogIn className="w-3 h-3" />
                <span className="sm:hidden">Sign in</span>
                <span className="hidden sm:inline">· Sign in again</span>
              </button>
            ) : authStatus === 'signed_in' ? (
              <span
                className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-1 text-[11px] text-foreground/70"
                title={email ?? 'Signed in'}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Signed in
              </span>
            ) : (
              <Link
                to="/auth?redirect=/chat"
                className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/40 hover:bg-muted transition-colors px-2.5 py-1 text-[11px] text-foreground/70"
                title="Sign in to save conversations"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
                Sign in
              </Link>
            )
          )}
          <UserMenu />
        </div>
      </div>
    </header>
  );
};
