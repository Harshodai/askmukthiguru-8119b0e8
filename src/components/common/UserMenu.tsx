import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  LogOut,
  User,
  Settings,
  Download,
  Flame,
  MessageCircle,
  Sun,
  Moon,
  Monitor,
  MapPin,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useProfile } from '@/hooks/useProfile';
import { useTheme } from '@/hooks/useTheme';
import { exportAllData, getInitials, resetProfile } from '@/lib/profileStorage';
import { useToast } from '@/hooks/use-toast';

interface UserMenuProps {
  onRestartTour?: () => void;
}

export const UserMenu = ({ onRestartTour }: UserMenuProps = {}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { profile } = useProfile();
  const { theme, setTheme } = useTheme();
  const { toast } = useToast();

  const handleExport = () => {
    const data = exportAllData();
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `askmukthiguru-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast({ title: t('common.dataExported'), description: t('common.dataExportedDesc') });
  };

  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          data-tour="profile"
          className="rounded-full ring-1 ring-border hover:ring-ojas/40 transition-all focus:outline-none focus:ring-2 focus:ring-ojas/60"
          aria-label={t('common.openUserMenu')}
        >
          <Avatar className="w-9 h-9">
            {profile.avatarDataUrl ? (
              <AvatarImage src={profile.avatarDataUrl} alt={profile.displayName} />
            ) : null}
            <AvatarFallback className="bg-ojas text-primary-foreground text-sm font-semibold">
              {getInitials(profile.displayName)}
            </AvatarFallback>

          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col">
          <span className="text-sm font-medium text-foreground">
            {profile.displayName}
          </span>
          <span className="text-[11px] text-muted-foreground">
            {t('common.localProfile')} · {profile.preferredLanguage.toUpperCase()}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/profile')}>
          <User className="w-4 h-4 mr-2" /> {t('nav.profile')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=settings')}>
          <Settings className="w-4 h-4 mr-2" /> {t('common.settings')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/chat')}>
          <MessageCircle className="w-4 h-4 mr-2" /> {t('common.continueChat')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=stats')}>
          <Flame className="w-4 h-4 mr-2" /> {t('common.insightsStats')}
        </DropdownMenuItem>
        {(
          <DropdownMenuItem
            onClick={() => {
              if (onRestartTour) {
                onRestartTour();
              } else {
                window.dispatchEvent(new CustomEvent('tour:restart'));
              }
            }}
            className="text-ojas/80 focus:text-ojas"
          >
            <MapPin className="w-4 h-4 mr-2" /> Take a Tour
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            <ThemeIcon className="w-4 h-4 mr-2" />
            {t('common.theme')}
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent>
            <DropdownMenuItem onClick={() => setTheme('light')}>
              <Sun className="w-4 h-4 mr-2" /> {t('common.light')}
              {theme === 'light' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('dark')}>
              <Moon className="w-4 h-4 mr-2" /> {t('common.dark')}
              {theme === 'dark' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('system')}>
              <Monitor className="w-4 h-4 mr-2" /> {t('common.system')}
              {theme === 'system' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleExport}>
          <Download className="w-4 h-4 mr-2" /> {t('common.exportData')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={async () => {
            const { supabase } = await import('@/integrations/supabase/client');
            await supabase.auth.signOut();
            resetProfile();
            navigate('/auth');
            toast({ title: t('common.signedOut'), description: t('common.signedOutDesc') });
          }}
          className="text-destructive focus:text-destructive"
        >
          <LogOut className="w-4 h-4 mr-2" /> {t('common.signOut')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
