import { useTranslation } from 'react-i18next';
import { ReactNode, useEffect, useState } from 'react';
import {
  Home,
  MessageCircle,
  User,
  Flame,
  Sparkles,
  Search,
  Compass,
  Loader2,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  SidebarHeader,
  SidebarFooter,
  useSidebar,
} from '@/components/ui/sidebar';
import { NavLink } from '@/components/NavLink';
import { UserMenu } from '@/components/common/UserMenu';
import { CommandPalette } from '@/components/common/CommandPalette';
import { ChatErrorBoundary } from '@/components/common/ChatErrorBoundary';
import { FloatingParticles } from '@/components/landing/FloatingParticles';
import { Button } from '@/components/ui/button';
import { useProfile } from '@/hooks/useProfile';
import { useFavorites } from '@/hooks/useFavorites';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { getInitials } from '@/lib/profileStorage';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { checkConnection } from '@/lib/aiService';
import { useRequireAuth } from '@/hooks/useRequireAuth';

interface AppShellProps {
  children: ReactNode;
  title?: string;
}

const navItems = [
  { to: '/', labelKey: 'nav.home' as const, icon: Home, end: true },
  { to: '/chat', labelKey: 'nav.chat' as const, icon: MessageCircle },
  { to: '/practices', labelKey: 'nav.practices' as const, icon: Compass },
  { to: '/profile', labelKey: 'nav.profile' as const, icon: User },
];

const SidebarBrand = () => {
  const { t } = useTranslation();
  const { state } = useSidebar();
  const collapsed = state === 'collapsed';
  const { profile } = useProfile();
  return (
    <div className="flex items-center gap-3 px-2 py-3">
      <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-ojas to-ojas-light flex items-center justify-center shadow-md shrink-0">
        <Sparkles className="w-5 h-5 text-primary-foreground" />
      </div>
      {!collapsed && (
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-foreground truncate">
            {t('nav.appName')}
          </p>
          <p className="text-[11px] text-muted-foreground truncate">
            {t('common.welcomeSeeker')}, {profile.displayName}
          </p>
        </div>
      )}
    </div>
  );
};

const AppSidebar = ({ onOpenSearch }: { onOpenSearch: () => void }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const { state } = useSidebar();
  const collapsed = state === 'collapsed';
  const { profile } = useProfile();
  const { favorites } = useFavorites();
  const { open: openSereneMind } = useSereneMind();
  const favCount = favorites.length;

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarBrand />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>{t('layout.navigate')}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.end
                    ? location.pathname === item.to
                    : location.pathname.startsWith(item.to);
                const showBadge = item.to === '/practices' && favCount > 0;
                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild isActive={isActive} tooltip={t(item.labelKey)}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        className="flex items-center gap-2"
                        activeClassName="text-ojas font-medium"
                      >
                        <Icon className="w-4 h-4" />
                        <span>{t(item.labelKey)}</span>
                        {showBadge && !collapsed && (
                          <span className="ml-auto inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-ojas/20 text-ojas text-[10px] font-semibold">
                            {favCount}
                          </span>
                        )}
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>{t('layout.quick')}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={onOpenSearch} tooltip={t('layout.commandPalette')}>
                  <Search className="w-4 h-4" />
                  <span>{t('layout.search')}</span>
                  {!collapsed && (
                    <kbd className="ml-auto text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      ⌘K
                    </kbd>
                  )}
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={() => openSereneMind()} tooltip={t('meditation.sereneMind')}>
                  <Flame className="w-4 h-4 text-ojas" />
                  <span>{t('meditation.sereneMind')}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <NavLink
          to="/profile"
          className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/60 transition-colors"
        >
          <Avatar className="w-8 h-8 ring-1 ring-border">
            {profile.avatarDataUrl ? (
              <AvatarImage src={profile.avatarDataUrl} alt={profile.displayName} />
            ) : null}
            <AvatarFallback className="bg-ojas/20 text-ojas text-xs font-semibold">
              {getInitials(profile.displayName)}
            </AvatarFallback>
          </Avatar>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {profile.displayName}
              </p>
              <p className="text-[11px] text-muted-foreground truncate">
                {t('layout.viewProfile')}
              </p>
            </div>
          )}
        </NavLink>
      </SidebarFooter>
    </Sidebar>
  );
};

const ConnectionPill = () => {
  const { t } = useTranslation();
  const [mode, setMode] = useState<string>(t('layout.offlineMode'));
  const [connected, setConnected] = useState<boolean>(true);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      const result = await checkConnection();
      if (!cancelled) {
        setMode(result.mode);
        setConnected(result.connected);
      }
    };
    poll();
    const id = setInterval(poll, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [t]);

  const dotColor = connected
    ? mode === t('layout.connectedMode')
      ? 'bg-prana'
      : 'bg-muted-foreground'
    : 'bg-destructive';

  return (
    <div
      className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-card/60 text-[11px] text-muted-foreground"
      title={t('layout.aiService', { mode })}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor} ${!connected ? 'animate-pulse' : ''}`} />
      <span>{mode}</span>
    </div>
  );
};

const HeaderSereneButton = () => {
  const { t } = useTranslation();
  const { open } = useSereneMind();
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => open()}
      className="gap-1.5 text-ojas hover:bg-ojas/10 hover:text-ojas"
      title={t('layout.sereneMindTitle')}
    >
      <Flame className="w-4 h-4" />
      <span className="hidden sm:inline text-xs font-medium">{t('meditation.sereneMind')}</span>
    </Button>
  );
};

export const AppShell = ({ children, title }: AppShellProps) => {
  const { t } = useTranslation();
  const { loading: authLoading } = useRequireAuth();
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  if (authLoading) {
    return (
      <div className="min-h-dvh flex items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 text-ojas animate-spin" />
      </div>
    );
  }

  return (
    <SidebarProvider>
      <div className="min-h-dvh flex w-full bg-background relative">
        <div className="fixed inset-0 bg-spiritual-gradient pointer-events-none" />
        <FloatingParticles />

        <AppSidebar onOpenSearch={() => setPaletteOpen(true)} />

        <div className="flex-1 flex flex-col min-w-0 relative z-10">
          <header className="h-14 flex items-center gap-2 sm:gap-3 border-b border-border/60 backdrop-blur-md bg-card/60 px-3 sm:px-4 sticky top-0 z-30">
            <SidebarTrigger />
            <div className="flex-1 min-w-0">
              {title && (
                <div className="text-sm sm:text-base font-semibold text-foreground truncate" role="heading" aria-level={2}>
                  {title}
                </div>
              )}
            </div>
            <ConnectionPill />
            <HeaderSereneButton />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPaletteOpen(true)}
              className="hidden md:inline-flex gap-2 text-muted-foreground"
            >
              <Search className="w-4 h-4" />
              <span className="text-xs">{t('layout.search')}</span>
              <kbd className="text-[10px] bg-muted px-1.5 py-0.5 rounded">
                ⌘K
              </kbd>
            </Button>
            <UserMenu />
          </header>

          <main className="flex-1 overflow-y-auto">
            <ChatErrorBoundary>
              {children}
            </ChatErrorBoundary>
          </main>
        </div>

        <CommandPalette
          open={paletteOpen}
          onOpenChange={setPaletteOpen}
          onNavigate={(path) => {
            setPaletteOpen(false);
            navigate(path);
          }}
        />
      </div>
    </SidebarProvider>
  );
};
