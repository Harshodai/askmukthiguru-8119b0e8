import { ArrowRight, Flame, MessageCircle, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { formatRelativeTime } from '@/lib/chatStorage';
import type { MeditationStats } from '@/lib/meditationStorage';
import type { Conversation } from '@/lib/chatStorage';
import type { PersonalInsight } from '@/lib/personalInsights';
import type { NormalizedSession } from '@/lib/meditationMetrics';
import { ProfileStatTiles } from '@/components/profile/ProfileStatTiles';

interface JourneyOverviewProps {
  displayName: string;
  email: string;
  familiarityLevel: string;
  languageLabel: string;
  toneLabel: string;
  avatarDataUrl?: string | null;
  avatarUrl?: string | null;
  stats: MeditationStats;
  sessions?: NormalizedSession[];
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

export const JourneyOverview = ({
  stats,
  sessions = [],
  conversations,
  personalInsights,
  dailyWisdom,
  onNavigate,
  onContinueChat,
  onPractice,
}: JourneyOverviewProps) => {
  const { t } = useTranslation();
  const hasPracticed = stats.totalSessions > 0;
  const recentConversations = conversations.slice(0, 3);
  const insights = personalInsights.slice(0, 2);
  const hasActivity = recentConversations.length > 0 || insights.length > 0;

  return (
    <div className="space-y-6">
      {/* ── Practice Overview: Stat tiles & 7-day sparkline ── */}
      <ProfileStatTiles stats={stats} sessions={sessions} />

      {/* ── Ekam Sanctuary Emblem & Teaching ── */}
      <div className="relative overflow-hidden rounded-2xl border border-ojas/25 bg-gradient-to-r from-amber-950/20 via-background to-amber-950/20 p-4 sm:p-5 shadow-xs flex flex-col sm:flex-row items-center gap-4">
        <div className="relative w-24 h-24 sm:w-28 sm:h-28 rounded-xl overflow-hidden shrink-0 border border-ojas/30 shadow-md">
          <img
            src="/images/ekam-golden-orb-lotus.png"
            alt="Ekam Golden Orb of Awakening"
            className="w-full h-full object-cover object-center"
            loading="lazy"
          />
        </div>
        <div className="flex-1 min-w-0 text-center sm:text-left space-y-1">
          <p className="text-[10px] uppercase tracking-[0.14em] font-semibold text-ojas">
            Ekam · World Centre for Enlightenment
          </p>
          <h3 className="text-sm sm:text-base font-semibold text-foreground">
            The Golden Orb of Pure Awareness
          </h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            In the sacred presence of the Golden Orb, inner division dissolves and the seeker awakens into the Beautiful State.
          </p>
        </div>
      </div>

      {/* Next step: exactly one card, one action. */}
      <Card className="rounded-none border-0 border-t border-hairline bg-transparent shadow-none">
        <CardHeader className="px-0 pt-6 pb-3">
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
        <CardContent className="space-y-3 px-0">
          <Button
            variant="outline"
            type="button"
            onClick={onPractice}
            className="group flex w-full h-auto min-h-[72px] items-center gap-4 rounded-lg border border-hairline bg-background/50 p-4 text-left whitespace-normal transition-colors hover:border-ojas/30 hover:bg-ojas/5"
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
          </Button>
          <Button variant="link"
            type="button"
            onClick={() => onNavigate('profile')}
            className="text-xs text-muted-foreground underline-offset-4 hover:text-ojas hover:underline"
          >
            {t('profile.journey.howPersonalizationWorks', 'How personalization works')}
          </Button>
        </CardContent>
      </Card>

      {/* Recent activity: conversations + reflections in one list. */}
      <Card className="rounded-none border-0 border-t border-hairline bg-transparent shadow-none">
        <CardHeader className="px-0 pt-6 pb-3">
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
        <CardContent className="px-0">
          {hasActivity ? (
            <div className="space-y-2.5">
              {recentConversations.map((conversation) => (
                <Button
                  variant="ghost"
                  type="button"
                  key={conversation.id}
                  onClick={() => onContinueChat(conversation.id)}
                  className="flex w-full h-auto min-h-[64px] items-center gap-3 rounded-lg px-0 py-3 text-left hover:bg-ojas/5 transition-colors"
                >
                  <MessageCircle className="w-4 h-4 shrink-0 text-ojas/70" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm text-foreground truncate">{conversation.preview || t('profile.journey.untitledConversation', 'Untitled conversation')}</p>
                    <p className="text-xs text-muted-foreground mt-1">{conversation.updatedAt ? formatRelativeTime(conversation.updatedAt) : ''}</p>
                  </div>
                </Button>
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
        <Card className="overflow-hidden rounded-none border-0 border-t border-hairline bg-transparent shadow-none">
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
