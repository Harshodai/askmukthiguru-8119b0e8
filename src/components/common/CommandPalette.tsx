import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from '@/components/ui/command';
import {
  Home,
  MessageCircle,
  User,
  Flame,
  Sparkles,
  Settings,
  Compass,
  Heart,
  Moon,
  Star,
  Search,
  BookOpen,
  Brain,
  HardDrive,
} from 'lucide-react';
import { practices } from '@/lib/practicesContent';
import { useFavorites } from '@/hooks/useFavorites';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { Conversation, loadConversations } from '@/lib/chatStorage';

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
  const { t } = useTranslation();
  const { favorites, isFavorited } = useFavorites();
  const { open: openSereneMind } = useSereneMind();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loadingConversations, setLoadingConversations] = useState(false);
  const favCount = favorites.length;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoadingConversations(true);
    loadConversations()
      .then((items) => {
        if (!cancelled) setConversations(items.slice(0, 12));
      })
      .catch(() => {
        if (!cancelled) setConversations([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingConversations(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const conversationItems = useMemo(
    () => conversations.filter((c) => c.preview && c.preview.trim().length > 0),
    [conversations],
  );

  const handleSereneMind = () => {
    onOpenChange(false);
    openSereneMind();
  };

  const navigateAndClose = (path: string) => {
    onOpenChange(false);
    onNavigate(path);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <div className="border-b border-border/40 bg-ojas/[0.03] px-4 py-2 text-[11px] text-muted-foreground flex items-center gap-2">
        <Search className="w-3.5 h-3.5 text-ojas shrink-0" />
        <span>{t('commandPalette.subtitle', 'Search your workspace, conversations, practices, and settings.')}</span>
      </div>
      <CommandInput placeholder={t('commandPalette.searchPlaceholder', 'Search AskMukthiGuru…')} />
      <CommandList>
        <CommandEmpty>{t('commandPalette.empty', 'Nothing matches that search.')}</CommandEmpty>

        {conversationItems.length > 0 && (
          <>
            <CommandGroup heading={t('commandPalette.recentConversations', 'Recent conversations')}>
              {conversationItems.map((conversation) => (
                <CommandItem
                  key={conversation.id}
                  value={`conversation ${conversation.preview}`}
                  onSelect={() => navigateAndClose(`/chat?conversation=${encodeURIComponent(conversation.id)}`)}
                >
                  <MessageCircle className="w-4 h-4 mr-2 text-prana" />
                  <span className="truncate">{conversation.preview}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground shrink-0">
                    {conversation.messageCount} {t('commandPalette.messages', 'messages')}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        )}

        <CommandGroup heading={t('commandPalette.quickActions', 'Quick actions')}>
          <CommandItem onSelect={handleSereneMind}>
            <Flame className="w-4 h-4 mr-2 text-ojas" />
            <span>{t('commandPalette.startSereneMind', 'Start Serene Mind meditation')}</span>
            <kbd className="ml-auto text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              {t('commandPalette.anywhere', 'Anywhere')}
            </kbd>
          </CommandItem>
          {!loadingConversations && (
            <CommandItem onSelect={() => navigateAndClose('/chat')}>
              <PlusIcon />
              <span>{t('commandPalette.startNewConversation', 'Start a new conversation')}</span>
            </CommandItem>
          )}
        </CommandGroup>

        <CommandSeparator />
        <CommandGroup heading={t('commandPalette.navigate', 'Navigate')}>
          <CommandItem onSelect={() => navigateAndClose('/')}>
            <Home className="w-4 h-4 mr-2" /> {t('nav.home', 'Home')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/chat')}>
            <MessageCircle className="w-4 h-4 mr-2" /> {t('commandPalette.chatWithGurus', 'Chat with the Gurus')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/practices')}>
            <Compass className="w-4 h-4 mr-2" />
            <span>{t('commandPalette.browsePractices', 'Browse practices')}</span>
            {favCount > 0 && (
              <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-ojas font-semibold">
                <Star className="w-3 h-3 fill-ojas" /> {favCount}
              </span>
            )}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/notebooks')}>
            <BookOpen className="w-4 h-4 mr-2" /> {t('commandPalette.studyNotebooks', 'Study notebooks')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/knowledge-graph')}>
            <Brain className="w-4 h-4 mr-2" /> {t('commandPalette.wisdomMap', 'Wisdom Map')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/second-brain')}>
            <HardDrive className="w-4 h-4 mr-2" /> {t('commandPalette.myReflections', 'My Reflections')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/profile')}>
            <User className="w-4 h-4 mr-2" /> {t('nav.profile', 'My Profile')}
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />
        <CommandGroup heading={t('nav.practices', 'Practices')}>
          {practices.map((p) => {
            const Icon = practiceIcon[p.slug] ?? Sparkles;
            const fav = isFavorited(p.slug);
            return (
              <CommandItem key={p.slug} value={`practice ${p.title}`} onSelect={() => navigateAndClose(`/practices/${p.slug}`)}>
                <Icon className="w-4 h-4 mr-2" />
                <span>{p.title}</span>
                {fav && <Star className="w-3 h-3 ml-auto fill-ojas text-ojas" />}
              </CommandItem>
            );
          })}
          <CommandItem onSelect={() => navigateAndClose('/profile?tab=stats')}>
            <Sparkles className="w-4 h-4 mr-2" /> {t('commandPalette.viewMeditationStats', 'View meditation stats')}
          </CommandItem>
        </CommandGroup>

        <CommandSeparator />
        <CommandGroup heading={t('common.settings', 'Settings')}>
          <CommandItem onSelect={() => navigateAndClose('/profile?tab=settings')}>
            <Settings className="w-4 h-4 mr-2" /> {t('commandPalette.preferencesAndSettings', 'Preferences & settings')}
          </CommandItem>
          <CommandItem onSelect={() => navigateAndClose('/profile?tab=settings')}>
            <User className="w-4 h-4 mr-2" /> {t('commandPalette.accountAndData', 'Account & data')}
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
};

function PlusIcon() {
  return (
    <span className="mr-2 inline-flex h-4 w-4 items-center justify-center rounded-full bg-ojas/15 text-ojas text-[12px] font-semibold leading-none">
      +
    </span>
  );
}
