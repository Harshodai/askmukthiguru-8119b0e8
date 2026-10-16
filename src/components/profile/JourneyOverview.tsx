import { ArrowRight, Clock, Flame, MessageCircle, Pencil, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getInitials } from '@/lib/profileStorage';
import { formatRelativeTime } from '@/lib/chatStorage';
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
  onNavigate: (tab: 'profile' | 'memory' | 'settings') => void;
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
}: JourneyOverviewProps) => {
  const { t } = useTranslation();
  const conversationCount = metrics?.totalConversations ?? conversations.length;
  const hasStats =
    stats.totalSessions > 0 ||
    stats.totalMinutes > 0 ||
    stats.streakDays > 0 ||
    conversationCount > 0;
  const hasPracticed = stats.totalSessions > 0;
  const recentConversations = conversations.slice(0, 3);
  const insights = personalInsights.slice(0, 2);
  const hasActivity = recentConversations.length > 0 || insights.length > 0;

  return (
    <div className="space-y-5">
      {/* Hero: flat Sacred Minimal — single identity header for the page. */}
      <section aria-labelledby="journey-name" className="rounded-2xl border border-hairline bg-card p-5 sm:p-6 shadow-sm">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4 min-w-0">
            <Avatar className="w-16 h-16 sm:w-20 sm:h-20 shrink-0 ring-1 ring-ojas/20">
              {(avatarDataUrl || avatarUrl) ? (
                <AvatarImage src={avatarDataUrl ?? avatarUrl ?? ''} alt="" />
              ) : null}
              <AvatarFallback className="bg-ojas/10 text-ojas text-xl font-semibold">
                {getInitials(displayName)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{familiarityLevel}</p>
              <h1 id="journey-name" className="mt-1 text-2xl sm:text-3xl font-semibold tracking-tight text-foreground truncate">
                {displayName || t('profile.journey.seeker', 'Seeker')}
              </h1>
              <p className="mt-1 text-sm text-muted-foreground truncate">{email || t('profile.journey.signedInSeeker', 'Signed-in seeker')}</p>
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

        {hasStats && (
          <div className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-2.5">
            <Metric label="Practice sessions" value={stats.totalSessions} icon={Sparkles} />
            <Metric label="Minutes practiced" value={stats.totalMinutes} icon={Clock} />
            <Metric label="Current streak" value={stats.streakDays} icon={Flame} />
            <Metric label="Conversations" value={conversationCount} icon={MessageCircle} />
          </div>
        )}
      </section>

      {/* Next step: exactly one card, one action. */}
      <Card className="rounded-2xl border-hairline bg-card shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-ojas" aria-hidden="true" />
            {t('profile.journey.nextStep', 'Your next step')}
          </CardTitle>
          <CardDescription>
            {hasPracticed
              ? t('profile.journey.nextStepContinueDesc', 'Keep the rhythm going with a short practice.')
              : t('profile.journey.nextStepStartDesc', 'Begin with one small guided practice.')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <button
            type="button"
            onClick={onPractice}
            className="group flex w-full items-center gap-4 rounded-2xl border border-hairline bg-background/50 p-4 text-left transition-colors hover:border-ojas/30 hover:bg-ojas/5"
          >
            <div className="w-10 h-10 rounded-xl bg-ojas/10 flex items-center justify-center shrink-0">
              {hasPracticed
                ? <Flame className="w-4 h-4 text-ojas" aria-hidden="true" />
                : <Sparkles className="w-4 h-4 text-ojas" aria-hidden="true" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-foreground">
                {hasPracticed
                  ? t('profile.journey.continuePractice', 'Continue your practice')
                  : t('profile.journey.choosePractice', 'Choose a practice')}
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {hasPracticed
                  ? t('profile.journey.seePracticeDesc', 'Return to your meditation and practice history.')
                  : t('profile.journey.choosePracticeDesc', 'Return to a guided meditation or discover a new one.')}
              </p>
            </div>
            <ArrowRight className="w-4 h-4 shrink-0 text-muted-foreground group-hover:text-ojas transition-colors" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => onNavigate('profile')}
            className="text-xs text-muted-foreground underline-offset-4 hover:text-ojas hover:underline"
          >
            {t('profile.journey.howPersonalizationWorks', 'How personalization works')}
          </button>
        </CardContent>
      </Card>

      {/* Recent activity: conversations + reflections in one list. */}
      <Card className="rounded-2xl border-hairline bg-card shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <MessageCircle className="w-4 h-4 text-ojas" aria-hidden="true" />
                {t('profile.journey.recentActivity', 'Recent activity')}
              </CardTitle>
              <CardDescription>{t('profile.journey.pickUp', 'Pick up where you left off.')}</CardDescription>
            </div>
            {recentConversations.length > 0 && (
              <Button variant="ghost" size="sm" onClick={() => onContinueChat()} className="text-xs gap-1 shrink-0">
                {t('profile.journey.openChat', 'Open chat')} <ArrowRight className="w-3 h-3" aria-hidden="true" />
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {hasActivity ? (
            <div className="space-y-2.5">
              {recentConversations.map((conversation) => (
                <button
                  type="button"
                  key={conversation.id}
                  onClick={() => onContinueChat(conversation.id)}
                  className="flex w-full items-center gap-3 rounded-2xl border border-hairline bg-background/40 px-4 py-3 text-left hover:border-ojas/30 hover:bg-ojas/5 transition-colors"
                >
                  <MessageCircle className="w-4 h-4 shrink-0 text-ojas/70" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-foreground truncate">{conversation.preview || t('profile.journey.untitledConversation', 'Untitled conversation')}</p>
                    <p className="text-xs text-muted-foreground mt-1">{conversation.updatedAt ? formatRelativeTime(conversation.updatedAt) : ''}</p>
                  </div>
                </button>
              ))}
              {insights.map((insight) => (
                <div key={insight.kind} className="flex items-start gap-3 rounded-2xl border border-hairline bg-muted/25 px-4 py-3">
                  <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas/70" aria-hidden="true" />
                  <p className="text-sm leading-relaxed text-foreground/90">{insight.text}</p>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-hairline px-4 py-6 text-center">
              <MessageCircle className="w-7 h-7 mx-auto text-muted-foreground/60" aria-hidden="true" />
              <p className="mt-2 text-sm text-muted-foreground">{t('profile.journey.conversationsWillAppear', 'Your conversations will appear here.')}</p>
              <Button variant="outline" size="sm" className="mt-3 rounded-xl" onClick={() => onContinueChat()}>{t('profile.journey.startFirstConversation', 'Start your first conversation')}</Button>
            </div>
          )}
        </CardContent>
      </Card>

      {dailyWisdom?.caption && (
        <Card className="overflow-hidden rounded-2xl border-hairline bg-card shadow-sm">
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
