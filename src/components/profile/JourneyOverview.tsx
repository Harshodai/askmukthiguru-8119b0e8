import { ArrowRight, Brain, Clock, Flame, LockKeyhole, MessageCircle, Pencil, Sparkles, UserRound } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getInitials } from '@/lib/profileStorage';
import type { MeditationStats } from '@/lib/meditationStorage';
import type { Conversation } from '@/lib/chatStorage';
import type { PersonalInsight } from '@/lib/personalInsights';

interface JourneyOverviewProps {
  displayName: string;
  email: string;
  familiarityLevel: string;
  languageLabel: string;
  toneLabel: string;
  avatarDataUrl?: string | null;
  avatarUrl?: string | null;
  stats: MeditationStats;
  conversations: Conversation[];
  personalInsights: PersonalInsight[];
  metrics?: {
    totalConversations?: number;
    totalMessages?: number;
    courseCompletionPercent?: number;
  } | null;
  dailyWisdom?: {
    caption?: string | null;
    image_url?: string | null;
  } | null;
  onNavigate: (tab: 'profile' | 'stats' | 'conversations' | 'memory' | 'settings') => void;
  onContinueChat: (conversationId?: string) => void;
  onPractice: () => void;
  onKnowledgeGraph: () => void;
}

const Metric = ({ label, value, icon: Icon }: { label: string; value: string | number; icon: typeof Flame }) => {
  const { t } = useTranslation();
  const keyMap: Record<string, string> = {
    "Practice sessions": "practiceSessions",
    "Minutes practiced": "minutesPracticed",
    "Current streak": "currentStreak",
    "Conversations": "conversations",
  };
  return (
    <div className="rounded-2xl border border-hairline bg-background/50 px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="w-3.5 h-3.5 text-ojas" aria-hidden="true" />
        <span>{t(`profile.journey.${keyMap[label] ?? label}`, { defaultValue: label })}</span>
      </div>
      <p className="mt-1.5 text-xl font-semibold tabular-nums text-foreground">{value}</p>
    </div>
  );
};

export const JourneyOverview = ({
  displayName,
  email,
  familiarityLevel,
  languageLabel,
  toneLabel,
  avatarDataUrl,
  avatarUrl,
  stats,
  conversations,
  personalInsights,
  metrics,
  dailyWisdom,
  onNavigate,
  onContinueChat,
  onPractice,
  onKnowledgeGraph,
}: JourneyOverviewProps) => {
  const { t } = useTranslation();
  const recentConversations = conversations.slice(0, 3);
  const insights = personalInsights.slice(0, 2);

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border border-ojas/20 bg-gradient-to-br from-card via-card to-ojas/5 p-5 sm:p-6 shadow-sm">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4 min-w-0">
            <Avatar className="w-16 h-16 sm:w-20 sm:h-20 shrink-0 ring-2 ring-ojas/15">
              {(avatarDataUrl || avatarUrl) ? (
                <AvatarImage src={avatarDataUrl ?? avatarUrl ?? ''} alt="" />
              ) : null}
              <AvatarFallback className="bg-ojas/10 text-ojas text-xl font-semibold">
                {getInitials(displayName)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{familiarityLevel}</p>
              <h1 className="mt-1 text-2xl sm:text-3xl font-semibold tracking-tight text-foreground truncate">
                {displayName || t('profile.journey.seeker', 'Seeker')}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground truncate">{email}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 shrink-0">
            <Button onClick={() => onContinueChat()} className="min-h-[44px] rounded-xl gap-1.5 bg-ojas hover:bg-ojas-light text-primary-foreground">
              <MessageCircle className="w-4 h-4" />
              {t('profile.journey.continueChat', 'Continue chatting')}
            </Button>
            <Button onClick={() => onNavigate('profile')} variant="outline" className="min-h-[44px] rounded-xl gap-1.5 border-hairline">
              <Pencil className="w-4 h-4" />
              {t('profile.journey.editProfile', 'Edit profile')}
            </Button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          <Metric label="Practice sessions" value={stats.totalSessions} icon={Sparkles} />
          <Metric label="Minutes practiced" value={stats.totalMinutes} icon={Clock} />
          <Metric label="Current streak" value={stats.streakDays} icon={Flame} />
          <Metric label="Conversations" value={metrics?.totalConversations ?? conversations.length} icon={MessageCircle} />
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card className="rounded-3xl border-hairline bg-card shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-ojas" />
              {t('profile.journey.keepMoving', 'Keep your journey moving')}
            </CardTitle>
            <CardDescription>{t('profile.journey.keepMovingDesc', 'Choose the next small step instead of navigating through settings.')}</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              onClick={onPractice}
              className="group rounded-2xl border border-hairline bg-background/50 p-4 text-left transition-colors hover:border-ojas/30 hover:bg-ojas/5"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="w-9 h-9 rounded-xl bg-ojas/10 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-ojas" />
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-ojas transition-colors" />
              </div>
              <p className="mt-3 font-medium text-foreground">{t('profile.journey.choosePractice', 'Choose a practice')}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t('profile.journey.choosePracticeDesc', 'Return to a guided meditation or discover a new one.')}</p>
            </button>

            <button
              type="button"
              onClick={() => onNavigate('stats')}
              className="group rounded-2xl border border-hairline bg-background/50 p-4 text-left transition-colors hover:border-ojas/30 hover:bg-ojas/5"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="w-9 h-9 rounded-xl bg-ojas/10 flex items-center justify-center">
                  <Flame className="w-4 h-4 text-ojas" />
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-ojas transition-colors" />
              </div>
              <p className="mt-3 font-medium text-foreground">{t('profile.journey.seePractice', 'See your practice')}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t('profile.journey.seePracticeDesc', 'Open detailed activity, streaks, and practice history.')}</p>
            </button>
          </CardContent>
        </Card>

        <Card className="rounded-3xl border-hairline bg-card shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <MessageCircle className="w-4 h-4 text-ojas" />
                  {t('profile.journey.recentConversations', 'Recent conversations')}
                </CardTitle>
                <CardDescription>{t('profile.journey.pickUp', 'Pick up where you left off.')}</CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('conversations')} className="text-xs gap-1">
                {t('profile.journey.viewAll', 'View all')} <ArrowRight className="w-3 h-3" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {recentConversations.length > 0 ? (
              <div className="space-y-2.5">
                {recentConversations.map((conversation) => (
                  <button
                    type="button"
                    key={conversation.id}
                    onClick={() => onContinueChat(conversation.id)}
                    className="w-full rounded-2xl border border-hairline bg-background/40 px-4 py-3 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors"
                  >
                    <p className="font-medium text-sm text-foreground truncate">{conversation.preview || t('profile.journey.untitledConversation', 'Untitled conversation')}</p>
                    <p className="text-xs text-muted-foreground mt-1">{conversation.updatedAt ? conversation.updatedAt.toLocaleString() : ''}</p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-hairline px-4 py-6 text-center">
                <MessageCircle className="w-7 h-7 mx-auto text-muted-foreground/60" />
                <p className="mt-2 text-sm text-muted-foreground">{t('profile.journey.conversationsWillAppear', 'Your conversations will appear here.')}</p>
                <Button variant="outline" size="sm" className="mt-3 rounded-xl" onClick={() => onContinueChat()}>{t('profile.journey.startFirstConversation', 'Start your first conversation')}</Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {insights.length > 0 && (
        <Card className="rounded-3xl border-hairline bg-card shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-ojas" />
                  {t('profile.journey.reflections', 'Recent reflections')}
                </CardTitle>
                <CardDescription>{t('profile.journey.signalsRecorded', 'Signals derived from what you have actually recorded.')}</CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => onNavigate('stats')} className="text-xs gap-1">
                {t('profile.journey.insights', 'Insights')} <ArrowRight className="w-3 h-3" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2.5">
            {insights.map((insight) => (
              <div key={insight.kind} className="rounded-2xl border border-hairline bg-muted/25 px-4 py-3">
                <p className="text-sm leading-relaxed text-foreground/90">{insight.text}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="rounded-3xl border-hairline bg-card shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">{t('profile.journey.personalized', 'How your guidance is personalized')}</CardTitle>
          <CardDescription>{t('profile.journey.personalizedDesc', 'Regular chats can use these preferences plus eligible saved memories. Temporary chats bypass personal memory.')}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2.5">
          <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-background/40 px-4 py-3">
            <Pencil className="mt-0.5 h-4 w-4 shrink-0 text-ojas" />
            <div>
              <p className="text-sm font-medium text-foreground">{t('profile.journey.preferences', 'Profile preferences')}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <span className="rounded-full border border-hairline bg-card px-2 py-0.5 text-[11px] text-muted-foreground">{languageLabel}</span>
                <span className="rounded-full border border-hairline bg-card px-2 py-0.5 text-[11px] text-muted-foreground">{toneLabel} tone</span>
                <span className="rounded-full border border-hairline bg-card px-2 py-0.5 text-[11px] text-muted-foreground">{familiarityLevel} guidance</span>
              </div>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-background/40 px-4 py-3">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas" />
            <div>
              <p className="text-sm font-medium text-foreground">{t('profile.journey.savedContext', 'Saved personal context')}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{t('profile.journey.savedContextDesc', 'Eligible memories, reflections, and persona context can be recalled when relevant.')}</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-hairline bg-background/40 px-4 py-3">
            <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0 text-ojas" />
            <div>
              <p className="text-sm font-medium text-foreground">{t('profile.journey.temporaryChat', 'Temporary chat')}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{t('profile.journey.temporaryChatDesc', 'No personal-memory recall and no saved chat history for that session.')}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="rounded-3xl border-hairline bg-card shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">{t('profile.journey.yourSpaces', 'Your spaces')}</CardTitle>
          <CardDescription>{t('profile.journey.yourSpacesDesc', 'Everything else stays one layer away, so the journey stays simple.')}</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <button type="button" onClick={() => onNavigate('memory')} className="rounded-2xl border border-hairline p-4 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors">
            <UserRound className="w-4 h-4 text-ojas" />
            <p className="mt-3 text-sm font-medium">{t('profile.journey.memoryNotes', 'Memory & notes')}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t('profile.journey.memoryNotesDesc', 'Reflections, saved memories, and personal notes.')}</p>
          </button>
          <button type="button" onClick={() => onNavigate('settings')} className="rounded-2xl border border-hairline p-4 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors">
            <LockKeyhole className="w-4 h-4 text-ojas" />
            <p className="mt-3 text-sm font-medium">{t('profile.journey.privacySecurity', 'Privacy & security')}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t('profile.journey.privacySecurityDesc', 'Security, theme, voice, reminders, and account controls.')}</p>
          </button>
          <button type="button" onClick={() => onNavigate('profile')} className="rounded-2xl border border-hairline p-4 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors">
            <Pencil className="w-4 h-4 text-ojas" />
            <p className="mt-3 text-sm font-medium">{t('profile.journey.personalizeGuidance', 'Personalize guidance')}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t('profile.journey.personalizeGuidanceDesc', 'Your name, tone, language, familiarity, and preferences.')}</p>
          </button>
          <button type="button" onClick={onKnowledgeGraph} className="rounded-2xl border border-hairline p-4 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors">
            <Brain className="w-4 h-4 text-ojas" />
            <p className="mt-3 text-sm font-medium">{t('profile.journey.wisdomMap', 'Your wisdom map')}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t('profile.journey.wisdomMapDesc', 'Explore the graph built from your saved reflections, notes, and linked teachings.')}</p>
          </button>
        </CardContent>
      </Card>

      {dailyWisdom?.caption && (
        <Card className="overflow-hidden rounded-3xl border-hairline bg-card shadow-sm">
          <div className="flex flex-col sm:flex-row">
            {dailyWisdom.image_url ? (
              <div className="relative w-full sm:w-1/3 aspect-[16/10] sm:aspect-auto sm:min-h-[150px] overflow-hidden bg-muted/20">
                <img src={dailyWisdom.image_url} alt="" className="w-full h-full object-cover" loading="lazy" />
                <div className="absolute inset-0 bg-gradient-to-t sm:bg-gradient-to-r from-card/80 via-transparent to-transparent pointer-events-none" />
              </div>
            ) : null}
            <div className="flex-1 p-5 flex flex-col justify-center">
              <div className="flex items-center gap-1.5 mb-2">
                <Sparkles className="w-3.5 h-3.5 text-ojas" />
                <span className="text-[10px] font-semibold text-ojas uppercase tracking-[0.14em]">{t('profile.journey.wisdomOfDay', 'Wisdom of the Day')}</span>
              </div>
              <p className="text-base text-foreground/90 font-serif leading-relaxed italic">&ldquo;{dailyWisdom.caption}&rdquo;</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};

export default JourneyOverview;
