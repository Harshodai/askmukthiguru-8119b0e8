import { ReactNode, useEffect, useState } from 'react';
import {
  Home,
  MessageCircle,
  User,
  Flame,
  Sparkles,
  Search,
  Compass,
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
import { FloatingParticles } from '@/components/landing/FloatingParticles';
import { Button } from '@/components/ui/button';
import { useProfile } from '@/hooks/useProfile';
import { useFavorites } from '@/hooks/useFavorites';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { getInitials } from '@/lib/profileStorage';

interface AppShellProps {
  children: ReactNode;
  title?: string;
}

const navItems = [
  { to: '/', label: 'Home', icon: Home, end: true },
  { to: '/chat', label: 'Chat', icon: MessageCircle },
  { to: '/practices', label: 'Practices', icon: Compass },
  { to: '/profile', label: 'Profile', icon: User },
];

const SidebarBrand = () => {
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
            AskMukthiGuru
          </p>
          <p className="text-[11px] text-muted-foreground truncate">
            Welcome, {profile.displayName}
          </p>
        </div>
      )}
    </div>
  );
};

const AppSidebar = ({ onOpenSearch }: { onOpenSearch: () => void }) => {
  const location = useLocation();
  const { state } = useSidebar();
  const collapsed = state === 'collapsed';
  const { profile } = useProfile();
  const { favorites } = useFavorites();
  const favCount = favorites.length;

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarBrand />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigate</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive =
                  item.end
                    ? location.pathname === item.to
                    : location.pathname.startsWith(item.to);
                const showBadge = item.to === '/practices' && favCount > 0;
                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild isActive={isActive} tooltip={item.label}>
                      <NavLink
                        to={item.to}
                        end={item.end}
                        className="flex items-center gap-2"
                        activeClassName="text-ojas font-medium"
                      >
                        <item.icon className="w-4 h-4" />
                        <span>{item.label}</span>
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
          <SidebarGroupLabel>Quick</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton onClick={onOpenSearch} tooltip="Command palette (⌘K)">
                  <Search className="w-4 h-4" />
                  <span>Search</span>
                  {!collapsed && (
                    <kbd className="ml-auto text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      ⌘K
                    </kbd>
                  )}
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild tooltip="Serene Mind">
                  <NavLink to="/chat" className="flex items-center gap-2">
                    <Flame className="w-4 h-4 text-ojas" />
                    <span>Serene Mind</span>
                  </NavLink>
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
                View profile
              </p>
            </div>
          )}
        </NavLink>
      </SidebarFooter>
    </Sidebar>
  );
};

export const AppShell = ({ children, title }: AppShellProps) => {
  const navigate = useNavigate();
  const [paletteOpen, setPaletteOpen] = useState(false);

  // ⌘K / Ctrl+K shortcut
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

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full bg-background relative">
        <div className="fixed inset-0 bg-spiritual-gradient pointer-events-none" />
        <FloatingParticles />

        <AppSidebar onOpenSearch={() => setPaletteOpen(true)} />

        <div className="flex-1 flex flex-col min-w-0 relative z-10">
          <header className="h-14 flex items-center gap-3 border-b border-border/60 backdrop-blur-md bg-card/60 px-3 sm:px-4 sticky top-0 z-30">
            <SidebarTrigger />
            <div className="flex-1 min-w-0">
              {title && (
                <h1 className="text-sm sm:text-base font-semibold text-foreground truncate">
                  {title}
                </h1>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPaletteOpen(true)}
              className="hidden md:inline-flex gap-2 text-muted-foreground"
            >
              <Search className="w-4 h-4" />
              <span className="text-xs">Search</span>
              <kbd className="text-[10px] bg-muted px-1.5 py-0.5 rounded">
                ⌘K
              </kbd>
            </Button>
            <UserMenu />
          </header>

          <main className="flex-1 overflow-y-auto">{children}</main>
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
