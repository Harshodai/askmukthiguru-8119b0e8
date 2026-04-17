import { useNavigate } from 'react-router-dom';
import { LogOut, User, Settings, Download, Flame, MessageCircle } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useProfile } from '@/hooks/useProfile';
import { exportAllData, getInitials, resetProfile } from '@/lib/profileStorage';
import { useToast } from '@/hooks/use-toast';

export const UserMenu = () => {
  const navigate = useNavigate();
  const { profile } = useProfile();
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
    toast({ title: 'Data exported', description: 'Your data was downloaded.' });
  };

  const handleSignOut = () => {
    // Local profile only — "sign out" resets to a fresh seeker.
    resetProfile();
    toast({
      title: 'Profile reset',
      description: 'A fresh local profile has been created.',
    });
    navigate('/');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="rounded-full ring-1 ring-border hover:ring-ojas/40 transition-all focus:outline-none focus:ring-2 focus:ring-ojas/60"
          aria-label="Open user menu"
        >
          <Avatar className="w-9 h-9">
            {profile.avatarDataUrl ? (
              <AvatarImage src={profile.avatarDataUrl} alt={profile.displayName} />
            ) : null}
            <AvatarFallback className="bg-ojas/20 text-ojas text-sm font-semibold">
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
            Local profile · {profile.preferredLanguage.toUpperCase()}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => navigate('/profile')}>
          <User className="w-4 h-4 mr-2" /> Profile
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=preferences')}>
          <Settings className="w-4 h-4 mr-2" /> Preferences
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/chat')}>
          <MessageCircle className="w-4 h-4 mr-2" /> Continue chat
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => navigate('/profile?tab=stats')}>
          <Flame className="w-4 h-4 mr-2" /> Meditation stats
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleExport}>
          <Download className="w-4 h-4 mr-2" /> Export my data
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleSignOut} className="text-destructive focus:text-destructive">
          <LogOut className="w-4 h-4 mr-2" /> Reset profile
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
