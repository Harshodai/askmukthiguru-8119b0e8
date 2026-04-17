import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import { Home, MessageCircle, User, Flame, Sparkles, Settings } from 'lucide-react';

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onNavigate: (path: string) => void;
}

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
          <CommandItem onSelect={() => onNavigate('/profile')}>
            <User className="w-4 h-4 mr-2" /> My Profile
          </CommandItem>
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Practices">
          <CommandItem onSelect={() => onNavigate('/chat')}>
            <Flame className="w-4 h-4 mr-2" /> Open Serene Mind
          </CommandItem>
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
