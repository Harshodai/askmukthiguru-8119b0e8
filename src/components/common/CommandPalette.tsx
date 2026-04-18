import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { Home, MessageCircle, User, Flame, Sparkles, Settings, Compass, Heart, Moon } from 'lucide-react';
import { practices } from '@/lib/practicesContent';

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (path: string) => void;
}

const practiceIcon: Record<string, typeof Flame> = {
  'soul-sync': Sparkles,
  'serene-mind': Flame,
  'beautiful-state': Heart,
  'daily-reflection': Moon,
};

export const CommandPalette = ({
  open,
  onOpenChange,
  onNavigate,
}: CommandPaletteProps) => {
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Where do you want to go?" />
      <CommandList>
        <CommandEmpty>Nothing matches that search.</CommandEmpty>
        <CommandGroup heading="Navigate">
          <CommandItem onSelect={() => onNavigate('/')}>
            <Home className="w-4 h-4 mr-2" /> Home
          </CommandItem>
          <CommandItem onSelect={() => onNavigate('/chat')}>
            <MessageCircle className="w-4 h-4 mr-2" /> Chat with the Gurus
          </CommandItem>
          <CommandItem onSelect={() => onNavigate('/practices')}>
            <Compass className="w-4 h-4 mr-2" /> Browse practices
          </CommandItem>
          <CommandItem onSelect={() => onNavigate('/profile')}>
            <User className="w-4 h-4 mr-2" /> My Profile
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Practices">
          {practices.map((p) => {
            const Icon = practiceIcon[p.slug] ?? Sparkles;
            return (
              <CommandItem key={p.slug} onSelect={() => onNavigate(`/practices/${p.slug}`)}>
                <Icon className="w-4 h-4 mr-2" /> {p.title}
              </CommandItem>
            );
          })}
          <CommandItem onSelect={() => onNavigate('/profile?tab=stats')}>
            <Sparkles className="w-4 h-4 mr-2" /> View meditation stats
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Settings">
          <CommandItem onSelect={() => onNavigate('/profile?tab=preferences')}>
            <Settings className="w-4 h-4 mr-2" /> Preferences
          </CommandItem>
          <CommandItem onSelect={() => onNavigate('/profile?tab=account')}>
            <User className="w-4 h-4 mr-2" /> Account & data
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
};
