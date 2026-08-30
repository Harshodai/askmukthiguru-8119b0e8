import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { LogOut, User, Settings, Download, Flame, MessageCircle, Sun, Moon, Monitor, MapPin, ShieldCheck, Compass } from 'lucide-react';
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
import { clearLocalChatData } from '@/lib/chatStorage';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';

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
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
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
          className="rounded-full ring-1 ring-border hover:ring-ojas/40 transition-all focus:outline-none focus:ring-2 focus:ring-ojas/60 min-w-[44px] min-h-[44px] flex items-center justify-center tap-clean"
          aria-label={t('common.openUserMenu')}
        >
          <Avatar className="w-9 h-9">
            {(profile.avatarDataUrl || profile.avatarUrl) ? (
              <AvatarImage src={profile.avatarDataUrl ?? profile.avatarUrl ?? ''} alt={profile.displayName} />
            ) : null}
            <AvatarFallback className="bg-ojas text-primary-foreground text-sm font-semibold">
              {getInitials(profile.displayName)}
            </AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-64 rounded-2xl border-hairline bg-card/95 backdrop-blur-xl shadow-xl p-1.5">
        <DropdownMenuLabel className="flex flex-col px-3 py-2.5">
          <span className="text-sm font-medium text-foreground truncate">{profile.displayName}</span>
          <span className="text-[11px] text-muted-foreground">
            {t('common.localProfile')} · {profile.preferredLanguage.toUpperCase()}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/profile')} className="min-h-[40px] rounded-lg">
          <User className="w-4 h-4 mr-2 text-ojas" /> {t('nav.profile')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=stats')} className="min-h-[40px] rounded-lg">
          <Flame className="w-4 h-4 mr-2 text-ojas" /> {t('common.insightsStats')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/chat')} className="min-h-[40px] rounded-lg">
          <MessageCircle className="w-4 h-4 mr-2 text-prana" /> {t('common.continueChat')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/practices')} className="min-h-[40px] rounded-lg">
          <Compass className="w-4 h-4 mr-2 text-ojas" /> {t('nav.practices')}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/profile?tab=settings')} className="min-h-[40px] rounded-lg">
          <Settings className="w-4 h-4 mr-2" /> {t('common.settings')}
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=settings#security')} className="min-h-[40px] rounded-lg">
          <ShieldCheck className="w-4 h-4 mr-2" /> Security & privacy
        </DropdownMenuItem>
        {onRestartTour && (
          <DropdownMenuItem onClick={onRestartTour} className="min-h-[40px] rounded-lg text-ojas/90 focus:text-ojas">
            <MapPin className="w-4 h-4 mr-2" /> Take a Tour
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="min-h-[40px] rounded-lg">
            <ThemeIcon className="w-4 h-4 mr-2" />
            {t('common.theme')}
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="rounded-xl">
            <DropdownMenuItem onClick={() => setTheme('light')} className="min-h-[40px] rounded-lg">
              <Sun className="w-4 h-4 mr-2" /> {t('common.light')}
              {theme === 'light' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('dark')} className="min-h-[40px] rounded-lg">
              <Moon className="w-4 h-4 mr-2" /> {t('common.dark')}
              {theme === 'dark' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTheme('system')} className="min-h-[40px] rounded-lg">
              <Monitor className="w-4 h-4 mr-2" /> {t('common.system')}
              {theme === 'system' && <span className="ml-auto text-ojas">•</span>}
            </DropdownMenuItem>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleExport} className="min-h-[40px] rounded-lg">
          <Download className="w-4 h-4 mr-2" /> {t('common.exportData')}
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={async () => {
            await clearLocalChatData();
            resetProfile();
            await supabase.auth.signOut();
            navigate('/auth');
            toast({ title: t('common.signedOut'), description: t('common.signedOutDesc') });
          }}
          className="min-h-[40px] rounded-lg text-destructive focus:text-destructive"
        >
          <LogOut className="w-4 h-4 mr-2" /> {t('common.signOut')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
