import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { forwardRef, useState, useCallback, memo, useRef, useEffect, Suspense, useMemo, Children, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ExternalLink, Share2, Shield, Copy, Check, RotateCcw, Pencil, BookOpen, Play, AlertTriangle, LogIn, RefreshCw, Bookmark, StickyNote, Languages, Volume2, VolumeX, MoreHorizontal, ChevronDown } from 'lucide-react';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { useNotes } from '@/hooks/useNotes';
import { useTextToSpeech } from '@/hooks/useTextToSpeech';
import { useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Message } from '@/lib/chatStorage';
import type { TeachingPreview, GroundingState, TeachingAttribution } from '@/lib/chat/types';
import { resolveAttributionLabel, isPersonalizedCitation } from '@/lib/chat/types';
import { isAutoTranscript } from '@/lib/transcriptStatus';
import { selectGuruTeachingCitation } from '@/lib/firstPersonCitationMapper';
import { evidenceSupport } from '@/lib/chat/evidenceSupport';
import { FEATURE_FLAGS } from '@/lib/featureFlags';
import { cn } from '@/lib/utils';
import { useProfile } from '@/hooks/useProfile';
import { translateText } from '@/lib/aiService';
import { lazyWithRetry } from '@/lib/lazyWithRetry';
import { InlineActions, EngagementCard } from './InlineActions';
import { FacultyReviewGate } from './FacultyReviewGate';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { createPortal } from 'react-dom';
import { memoryApi } from '@/lib/memoryApi';
import { useToast } from '@/hooks/use-toast';
import { CitationPanel, type Citation } from './CitationPanel';
import { LiveLogisticsCards } from './LiveLogisticsCards';
import { EuAiBadge } from '@/components/compliance/EuAiBadge';
import { ProvenanceDrawer } from '@/components/compliance/ProvenanceDrawer';
import { CitationBadge, DiscourseVideoModal, type DiscourseCitation } from './CitationCard';
import { LinkSearchModal } from './LinkSearchModal';
import { SacredPracticeWidget } from './SacredPracticeWidget';
import { DiscourseAudioStrip } from './DiscourseAudioStrip';
import { DeepenAndTuneBar } from './DeepenAndTuneBar';
import { buildPersonalizeRef, type PersonalizeTeachingRef } from '@/lib/chat/personalize';
import { completeStep } from '@/lib/dailyJourney';
import { AbstainHelpCard } from './AbstainHelpCard';

interface ChatMessageProps {
  message: Message;
  queryText?: string;
  index?: number;
  isStreaming?: boolean;
  isLastGuru?: boolean;
  onRegenerate?: () => void;
  onStartNewChat?: () => void;
  onEditUserMessage?: (message: Message) => void;
  onSubmitEdit?: (messageId: string, newContent: string) => void;
  onAction?: (query: string) => void;
  /** Fired when the reader clicks an inline `[N]` citation marker in the answer. */
  onCitationClick?: (messageId: string, citationIndex: number) => void;
  /** Set only when the seeker may personalize (flag on, signed in, not incognito). */
  onPersonalizeTeaching?: (ref: PersonalizeTeachingRef) => void;
}

/**
 * Preprocess assistant content so that literal `[N]` (or `[1, 2]`) citation
 * markers become clickable markdown links (`href="#cite-N"`) that our custom
 * `a` renderer converts into accessible buttons.
 * Only markers whose N maps to a real citation URL are transformed.
 */
const injectCitationLinks = (content: string, citationsLen: number): string => {
  if (!content || citationsLen === 0) return content;
  // Match [1], [ 2 ], [1,2], [1, 2, 3] — expand comma lists into adjacent markers.
  return content.replace(/\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]/g, (match, group: string) => {
    const nums = group.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => Number.isFinite(n) && n >= 1 && n <= citationsLen);
    if (nums.length === 0) return match;
    return nums.map((n) => `[[${n}]](#cite-${n})`).join('');
  });
};

/**
 * Allowlist for markdown-rendered URLs. react-markdown v10 forwards raw hrefs
 * unless urlTransform is set; model-generated content must never open
 * javascript:/data: links, so every scheme outside the allowlist is dropped.
 */
export const safeUrlTransform = (url: string): string =>  /^(https?:|mailto:|#)/i.test(url) ? url : '';

/** Extract a valid 11-character YouTube video ID from a source URL. */
const getYouTubeId = (url: string): string | null => {
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    let candidate: string | null = null;
    if (hostname === 'youtu.be') {
      candidate = parsed.pathname.split('/').filter(Boolean)[0] ?? null;
    } else if (hostname === 'youtube.com') {
      if (parsed.pathname === '/watch') candidate = parsed.searchParams.get('v');
      if (parsed.pathname.startsWith('/embed/')) candidate = parsed.pathname.split('/')[2] ?? null;
      if (parsed.pathname.startsWith('/shorts/')) candidate = parsed.pathname.split('/')[2] ?? null;
    }
    return candidate && /^[A-Za-z0-9_-]{11}$/.test(candidate) ? candidate : null;
  } catch {
    return null;
  }
};

/** Check if a URL is a usable HTTP(S) source. */
const isUsableSourceUrl = (url: string): boolean => {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
    if (!parsed.hostname) return false;
    const hostname = parsed.hostname.toLowerCase().replace(/^www\./, '');
    if (hostname === 'youtube.com' || hostname === 'youtu.be') {
      return getYouTubeId(url) !== null;
    }
    return true;
  } catch {
    return false;
  }
};

/**
 * True when a guru answer is a crisis/helpline response. Such answers must never
 * carry the "Did this help? 👍/👎" engagement card or the "explain simply" inline
 * actions — a thumbs-down widget under a suicide helpline is unsafe. The backend
 * crisis path (services/crisis_helplines.format_helplines_block) always emits the
 * 🆘 intro; we also match a bare helpline heading defensively.
 */
const isCrisisAnswer = (content: string): boolean =>
  /🆘/.test(content) || /immediate crisis|crisis, please reach out|helpline/i.test(content);

/**
 * Detects whether a guru response is a first-person abstain
 * ("I don't have a verified verbatim teaching that directly answers this...").
 */
export const isFirstPersonAbstainMessage = (message: Message): boolean => {
  if (message.isFirstPersonAbstain === true) return true;
  if (message.routeDecision === 'first_person_abstain') return true;
  const method = message.verification?.method;
  if (
    method === 'first_person_no_match_abstain' ||
    method === 'first_person_store_unavailable'
  ) {
    return true;
  }
  const content = message.content || '';
  if (
    content.includes('rather say so than improvise one') ||
    content.includes("I don't have a verified verbatim teaching that directly answers this") ||
    content.includes("I don't have a recording that answers this part yet") ||
    content.includes('No verified verbatim teaching')
  ) {
    return true;
  }
  return false;
};

interface TeachingGroundingCardProps {
  citations: Citation[];
  teachingPreview?: TeachingPreview[];
  groundingState?: GroundingState;
  citationsVerified?: boolean | null;
  verification?: Record<string, unknown> | null;
  guidanceAttribution?: TeachingAttribution | null;
}

const TeachingGroundingCard = ({
  citations,
  teachingPreview = [],
  groundingState,
  citationsVerified,
  verification,
  guidanceAttribution,
}: TeachingGroundingCardProps) => {
  const { t } = useTranslation();
  const items = teachingPreview.length > 0
    ? teachingPreview.slice(0, 3)
    : citations
        .filter((citation) => Boolean(citation.title || citation.quote || citation.textSnippet))
        .slice(0, 3)
        .map((citation) => ({
          title: citation.title || citation.source || t('chat.references'),
          teacher: resolveAttributionLabel(citation) ?? null,
          url: citation.url || null,
          excerpt: citation.quote || citation.textSnippet || null,
        }));

  const isAbstained = groundingState === 'abstained';
  const isUnverifiedAttribution = guidanceAttribution?.source_backed === false || citationsVerified === false;
  // Source-only partial evidence (verification.partial) or any failed answer
  // verification must never read as "Verified": citations_verified describes the
  // excerpts' provenance, not whether the answer text passed verification.
  const isPartialEvidence = verification?.partial === true || verification?.passed === false;
  // First-person weak match: a real recorded clip served under "Related, not a direct
  // answer" (verification.direct === false) must never wear the "Verified" badge.
  const isRelatedOnly = verification?.direct === false;
  const isExplicitlyVerified =
    citationsVerified === true && !isUnverifiedAttribution && !isPartialEvidence && !isRelatedOnly;
  const isSupporting =
    !isExplicitlyVerified && !isUnverifiedAttribution && !isPartialEvidence && !isRelatedOnly;

  // Title-less citations (live partial-evidence shape) produce no card items. They
  // are still sources, so never claim "no direct discourse citations" beside them.
  if (items.length === 0 && citations.length > 0) {
    if (!isPartialEvidence) return null;
    return (
      <aside
        data-testid="teaching-grounding"
        aria-label={t('chat.teachingContext.title')}
        className="mb-3.5 w-full rounded-xl border border-amber-500/20 bg-amber-500/[0.03] px-3.5 py-3 text-start backdrop-blur-sm"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-[15px] leading-5 font-medium text-foreground">
          <span>{t('chat.teachingContext.title')}</span>
          <span className="inline-flex items-center rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
            {t('chat.teachingContext.partialBadge', 'Closest passages (not verified)')}
          </span>
        </div>
      </aside>
    );
  }

  if (items.length === 0 && !isAbstained) return null;

  if (items.length === 0 && isAbstained) {
    return (
      <aside
        data-testid="teaching-grounding"
        aria-label={t('chat.teachingContext.title')}
        className="mb-3.5 w-full rounded-xl border border-muted-foreground/15 bg-muted/20 px-3.5 py-3 text-start backdrop-blur-sm"
      >
        <div className="flex items-center gap-2 text-[15px] leading-5 font-medium text-foreground">
          <Sparkles className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span>{t('chat.teachingContext.title')}</span>
          <span className="ms-auto rounded-full bg-muted/60 px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
            {t('chat.teachingContext.noDirectDiscourse', 'No direct discourse match')}
          </span>
        </div>
        <p className="mt-1.5 text-[15px] leading-[1.75] text-muted-foreground">
          {t('chat.teachingContext.abstainedDescription', 'This contemplation is offered from foundational spiritual principles without direct discourse citations.')}
        </p>
      </aside>
    );
  }

  const badgeLabel = isExplicitlyVerified
    ? t('chat.teachingContext.verifiedBadge', 'Verified Sacred Teaching')
    : isPartialEvidence
    ? t('chat.teachingContext.partialBadge', 'Closest passages (not verified)')
    : isRelatedOnly
    ? t('chat.teachingContext.relatedBadge', 'Related teaching — not a direct answer')
    : isSupporting
    ? t('chat.teachingContext.supportingBadge', 'Supporting Context')
    : t('chat.teachingContext.unverifiedBadge', 'General Spiritual Context');

  return (
    <aside
      data-testid="teaching-grounding"
      aria-label={t('chat.teachingContext.title')}
      className={cn(
        'mb-3.5 w-full rounded-xl border px-3.5 py-3 text-start backdrop-blur-sm',
        isExplicitlyVerified
          ? 'border-ojas/20 bg-ojas/[0.04]'
          : isSupporting
          ? 'border-border/60 bg-card/60'
          : 'border-amber-500/20 bg-amber-500/[0.03]'
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-[15px] leading-5 font-medium text-foreground">
        <div className="flex items-center gap-2">
          {isExplicitlyVerified ? (
            <BookOpen className="h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
          ) : isSupporting ? (
            <Sparkles className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          ) : (
            <Sparkles className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
          )}
          <span>{t('chat.teachingContext.title')}</span>
          <span className="text-[15px] font-normal text-muted-foreground/70">
            {t('chat.teachingContext.sourceCount', { count: items.length })}
          </span>
        </div>
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium',
            isExplicitlyVerified
              ? 'bg-ojas/10 text-ojas border border-ojas/20'
              : isSupporting
              ? 'bg-muted/80 text-muted-foreground border border-border/40'
              : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20'
          )}
        >
          {badgeLabel}
        </span>
      </div>

      {isUnverifiedAttribution && (
        <p className="mt-1.5 text-xs text-muted-foreground/90 italic">
          {t('chat.teachingContext.unverifiedNote', 'Discourse attribution is unverified; offered as general spiritual guidance.')}
        </p>
      )}

      <div className="mt-2.5 space-y-2.5">
        {items.map((item, index) => {
          const safeUrl = item.url && isUsableSourceUrl(item.url) ? safeUrlTransform(item.url) : null;
          return (
            <div key={item.url || item.title + '-' + index} className="min-w-0">
              <div className="text-[15px] leading-5 font-medium text-foreground">
                {safeUrl ? (
                  <a
                    href={safeUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-ojas hover:underline underline-offset-2"
                    aria-label={t('chat.openSourceAria', {
                      number: index + 1,
                      domain: (() => {
                        try {
                          return new URL(safeUrl).hostname.replace(/^www\./, '');
                        } catch {
                          return safeUrl;
                        }
                      })(),
                    })}
                  >
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
              </div>
              {item.teacher && (
                <div className="mt-0.5 text-[14px] leading-tight text-muted-foreground font-medium">{item.teacher}</div>
              )}
              {item.excerpt && (
                <blockquote className="mt-1 border-s-2 border-ojas/30 ps-3 text-[15px] leading-[1.75] text-muted-foreground line-clamp-3">
                  {item.excerpt}
                </blockquote>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
};

/** m:ss clock for served-clip labels. 0 is a real start, rendered as 0:00. */
const formatClipClock = (sec: number): string => {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
};

export interface GuruTeachingCardProps {
  /** The served quote-bearing citation. `quote`/`textSnippet` render byte-for-byte. */
  citation: Citation;
  /** True only when the serving path verified this exact teaching — never set
   *  for partial evidence, failed verification, or unverified attribution. */
  verified: boolean;
  /** Served under "Related, not a direct answer" — never badged Verified. */
  related?: boolean;
  /** 1-based position, forwarded to the playback modal. */
  index?: number;
  /** Opens the timestamped playback modal. Absent: play degrades to a source link. */
  onPlay?: (citation: DiscourseCitation) => void;
}

/**
 * Artifact-style card for a served guru teaching (Claude-artifact treatment):
 * a labelled, visually distinct panel holding the verbatim quote, the
 * resolved attribution line, and the playback/source links — so the teacher's
 * own words never blur into generated glue. The quote is a plain text node:
 * no markdown, no HTML parsing, no rewording, no dangerouslySetInnerHTML.
 * Attribution always flows through resolveAttributionLabel (bare unverified
 * teacher names downgrade to "shared in <channel>" / "unverified clip").
 * Empty state (no quotable excerpt) renders null — never an empty card.
 */
export const GuruTeachingCard = ({
  citation,
  verified,
  related = false,
  index = 1,
  onPlay,
}: GuruTeachingCardProps) => {
  const { t } = useTranslation();
  const quote = citation.quote?.trim()
    ? citation.quote
    : citation.textSnippet?.trim()
      ? citation.textSnippet
      : null;
  if (!quote) return null;

  const personalized = isPersonalizedCitation(citation);
  const attribution = resolveAttributionLabel({
    speaker: citation.speaker,
    speakerVerified: citation.speakerVerified,
    channel_name: citation.channel_name,
    source: citation.source,
  });
  const showVerified = verified && !related && !personalized;
  const startSeconds = citation.playbackStartSeconds ?? citation.timestampSeconds;
  const clockLabel = formatClipClock(startSeconds ?? 0);
  // Playback window only when the payload pins an explicit clip start (a
  // normalized fallback to the answer timestamp is not a clip range).
  const playbackLabel = citation.playbackStartSeconds != null
    ? `(from ${formatClipClock(citation.playbackStartSeconds)})`
    : null;
  const playbackUrl = citation.playbackUrl ?? citation.url;
  const domain = getDomain(citation.url);
  const playName = `Play clip: ${attribution ?? domain} at ${clockLabel}`;

  const openPlayback = () => {
    if (!onPlay) return;
    onPlay({
      index,
      url: playbackUrl,
      title: citation.title ?? citation.source ?? undefined,
      speaker: citation.speaker ?? undefined,
      speakerVerified: citation.speakerVerified,
      startTimestamp: citation.timestampSeconds,
      playbackStartSeconds: citation.playbackStartSeconds,
      playbackEndSeconds: citation.playbackEndSeconds,
      quote,
      transcriptStatus: citation.transcriptStatus,
    });
  };

  const badgeLabel = personalized
    ? t('chat.guruTeaching.personalizedBadge', 'Personalized reflection')
    : showVerified
      ? t('chat.guruTeaching.verifiedBadge', 'Verified')
      : related
        ? t('chat.guruTeaching.relatedBadge', 'Related — not a direct answer')
        : t('chat.guruTeaching.unverifiedBadge', 'Unverified attribution');

  return (
    <aside
      data-testid="guru-teaching-card"
      aria-label={t('chat.guruTeaching.ariaLabel', "Guru teaching in the teacher's own words")}
      className="w-full rounded-2xl border border-ojas/30 bg-gradient-to-br from-ojas/[0.08] via-card to-card px-4 py-3.5 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <BookOpen className="h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ojas">
          {personalized
            ? t('chat.guruTeaching.personalizedLabel', 'Personalized reflection')
            : t('chat.guruTeaching.label', 'Guru teaching · verbatim')}
        </span>
        <span
          className={cn(
            'ms-auto inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
            showVerified
              ? 'border-ojas/20 bg-ojas/10 text-ojas'
              : 'border-amber-500/20 bg-amber-500/10 text-amber-600 dark:text-amber-400'
          )}
        >
          {badgeLabel}
        </span>
      </div>
      <blockquote
        data-testid="guru-teaching-quote"
        className="mt-2 border-s-2 border-ojas/40 ps-3 font-serif text-[15px] leading-[1.75] text-foreground"
      >
        {quote}
      </blockquote>
      {personalized && (
        <p className="mt-1.5 text-xs italic text-muted-foreground">
          {t(
            'chat.guruTeaching.personalizedNote',
            'In our own words — not a direct quote from the teachers.'
          )}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs text-muted-foreground">
        {attribution && (
          <span className="font-medium text-ojas">{attribution}</span>
        )}
        <span className="tabular-nums">{clockLabel}</span>
        {playbackLabel && <span className="tabular-nums">{playbackLabel}</span>}
        {isAutoTranscript(citation.transcriptStatus) && (
          <span className="rounded-full bg-muted/70 px-2 py-0.5 text-[10px] font-medium">
            {t('chat.guruTeaching.autoTranscript', 'auto-transcript')}
          </span>
        )}
        {onPlay ? (
          <button
            type="button"
            onClick={openPlayback}
            aria-label={playName}
            className="ms-auto inline-flex items-center gap-1.5 rounded-full bg-ojas px-3 py-1.5 font-semibold text-primary-foreground shadow-sm transition-transform hover:scale-[1.02]"
          >
            <Play className="h-3 w-3 fill-current" aria-hidden="true" />
            {t('chat.guruTeaching.playClip', 'Play clip')}
          </button>
        ) : (
          <a
            href={safeUrlTransform(playbackUrl)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={playName}
            className="ms-auto inline-flex items-center gap-1.5 rounded-full bg-ojas px-3 py-1.5 font-semibold text-primary-foreground shadow-sm transition-transform hover:scale-[1.02]"
          >
            <Play className="h-3 w-3 fill-current" aria-hidden="true" />
            {t('chat.guruTeaching.playClip', 'Play clip')}
          </a>
        )}
        <a
          href={safeUrlTransform(citation.url)}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={t('chat.guruTeaching.openSourceAria', 'Open source teaching')}
          title={domain}
          className="inline-flex h-7 w-7 items-center justify-center rounded-lg border border-border/40 bg-background/40 text-muted-foreground transition-colors hover:bg-background/80 hover:text-foreground"
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      </div>
    </aside>
  );
};

const GuidancePlanCard = ({ plan }: { plan: NonNullable<Message["guidancePlan"]> }) => {
  const { t } = useTranslation();
  return (
  <aside
    data-testid="guidance-plan"
    aria-label={t('chat.guidance.ariaLabel')}
    className="w-full rounded-xl border border-ojas/20 bg-gradient-to-br from-ojas/10 to-card px-3.5 py-3 shadow-sm"
  >
    <div className="flex items-start gap-2">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {plan.action_step && (
          <>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">{t('chat.guidance.tryNow')}</p>
            <p className="mt-1 text-sm font-medium leading-5 text-foreground">{plan.action_step.title}</p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{plan.action_step.instruction}</p>
            {plan.action_step.safety_note && (
              <p className="mt-2 text-xs leading-4 text-muted-foreground">{plan.action_step.safety_note}</p>
            )}
          </>
        )}
        {plan.reflection_prompt && (
          <div className={plan.action_step ? "mt-3 border-t border-ojas/15 pt-2.5" : ""}>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">{t('chat.guidance.goDeeper')}</p>
            <p className="mt-1 text-sm leading-5 text-foreground/85">{plan.reflection_prompt}</p>
          </div>
        )}
      </div>
    </div>
  </aside>
  );
};

const SereneMindOfferCard = ({ offer }: { offer: NonNullable<Message["sereneMindOffer"]> }) => {
  const { t } = useTranslation();
  const { open } = useSereneMind();
  const customMeditation = offer.custom_meditation;
  const durationSeconds = offer.duration_seconds ?? 225;
  const durationLabel = durationSeconds >= 60
    ? `${Math.round(durationSeconds / 60)} min`
    : `${durationSeconds} sec`;

  return (
    <aside
      data-testid="serene-mind-offer"
      aria-label={t('chat.sereneMindOfferAria')}
      role="status"
      aria-live="polite"
      className="mt-3 w-full rounded-xl border border-ojas/25 bg-gradient-to-br from-ojas/10 to-card px-3.5 py-3 shadow-sm"
    >
      <div className="flex items-start gap-2">
        <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-ojas" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ojas">{t('chat.optionalPractice')}</p>
          <p className="mt-1 text-sm font-medium leading-5 text-foreground">
            {offer.offer_reason || t('chat.sereneMindOfferDefaultReason')}
          </p>
          <p className="mt-1 text-xs leading-4 text-muted-foreground">
            {durationLabel} · {t('chat.sereneMindOfferFooter')}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => open('audio', false, customMeditation?.steps, customMeditation?.source_teaching)}
              className="inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-ojas to-ojas-light px-3 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition-transform hover:scale-[1.02]"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {t('chat.startSereneMind')}
            </button>
            <span className="self-center text-[11px] text-muted-foreground">{t('chat.continueChatting')}</span>
          </div>
        </div>
      </div>
    </aside>
  );
};

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};


/** Check if a URL is a valid YouTube source. */
const isYouTubeUrl = (url: string): boolean => getYouTubeId(url) !== null;

/** Lazy YouTube embed: thumbnail → click → iframe */
interface YTPlayerReadyEvent {
  target: {
    addEventListener: (event: string, listener: (e: { data: number }) => void) => void;
  };
}

declare global {
  interface Window {
    YT?: {
      Player: new (
        elementId: string,
        options: {
          videoId: string;
          playerVars?: Record<string, number | string>;
          events?: { onReady?: (event: YTPlayerReadyEvent) => void; onError?: (event: { data: number }) => void };
        }
      ) => { destroy: () => void };
      PlayerState?: { ENDED: number; PLAYING: number };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** Get a display name for a citation: the real title when known, else a
 *  domain-derived label (e.g., 'Video Source A') synthesized from the URL. */
const getSourceDisplayName = (citation: Citation, index: number, t: TFunction): string => {
  if (citation.title) return citation.title;
  const url = citation.url;
  try {
    const urlObj = new URL(url);
    const hostname = urlObj.hostname.replace(/^www\./, '');
    if (hostname.includes('youtube') || hostname.includes('youtu.be')) {
      return t('chat.videoSource', { letter: String.fromCharCode(65 + index) });
    }
    if (hostname.includes('academy') || hostname.includes('ekam')) {
      return t('chat.academyReference');
    }
    if (hostname.includes('preethaji') || hostname.includes('krishnaji')) {
      return t('chat.teachingReference');
    }
    return hostname;
  } catch {
    return t('chat.sourceLabel', { number: index + 1 });
  }
};

/**
 * Summarizes the cited teachers or channel sources for the compact source pill.
 * Follows invariant L-FP-HYBRID-SCAFFOLD-1: never invent teacher names for unverified clips.
 */
export const getTeacherSummary = (citations: Citation[]): string => {
  const teachers = new Set<string>();
  for (const c of citations) {
    const label = resolveAttributionLabel({
      speaker: c.speaker,
      speakerVerified: c.speakerVerified,
      channel_name: c.channel_name,
      source: c.source,
    });
    if (label && label !== 'unverified clip') {
      teachers.add(label);
    } else if (c.channel_name && !/unknown/i.test(c.channel_name)) {
      teachers.add(c.channel_name);
    }
  }
  if (teachers.size === 0) {
    return 'Wisdom Teachings';
  }
  const list = Array.from(teachers);
  if (list.length <= 2) {
    return list.join(', ');
  }
  return `${list.slice(0, 2).join(', ')} +${list.length - 2}`;
};


/**
 * Wisdom Card generator is a big, rarely-opened modal — it ships in its own
 * chunk and loads only when the share button is clicked, keeping it off the
 * chat hot path (P1-AI-16). lazyWithRetry reloads once if a deploy invalidated
 * the chunk URL mid-session. The module exports a named component, so adapt
 * it to the `{ default }` shape lazyWithRetry expects. Shared by ChatInterface
 * (Quick Wisdom Card) so the generator stays in exactly one lazy chunk.
 */
export const LazyWisdomCardGenerator = lazyWithRetry<
  React.ComponentType<{ isOpen: boolean; onClose: () => void; content: string }>
>(async () => {
  const mod = await import('./WisdomCardGenerator');
  return { default: mod.WisdomCardGenerator };
});

export const PERSONALIZED_LABEL =
  '_This is a personalized reflection on the teaching above, in our own words — not a direct quote from the teachers._';

interface UserMessageContentProps {
  content: string;
  showMoreLabel?: string;
  showLessLabel?: string;
}

const UserMessageContent: React.FC<UserMessageContentProps> = ({
  content,
  showMoreLabel = 'Read more',
  showLessLabel = 'Show less',
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isLong = content.length > 420 || (content.match(/\n/g) || []).length > 5;
  const wordCount = useMemo(() => {
    const trimmed = content.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }, [content]);

  if (!isLong) {
    return (
      <span className="font-medium whitespace-pre-wrap leading-relaxed break-words">
        {content}
      </span>
    );
  }

  return (
    <div className="flex flex-col w-full">
      <div
        className={cn(
          'relative transition-all duration-300 font-medium whitespace-pre-wrap leading-relaxed break-words',
          !isExpanded && 'max-h-[140px] overflow-hidden'
        )}
      >
        <span>{content}</span>
        {!isExpanded && (
          <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-chat-user via-chat-user/80 to-transparent" />
        )}
      </div>
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-ojas hover:text-ojas-light transition-colors self-start select-none py-0.5 rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ojas"
        aria-expanded={isExpanded}
      >
        <span>{isExpanded ? showLessLabel : `${showMoreLabel} (${wordCount} words)`}</span>
        <ChevronDown
          className={cn('w-3.5 h-3.5 transition-transform duration-200', isExpanded && 'rotate-180')}
        />
      </button>
    </div>
  );
};

const ChatMessageInner = forwardRef<HTMLDivElement, ChatMessageProps>(
  ({ message, queryText, index = 0, isStreaming = false, isLastGuru = false, onRegenerate, onStartNewChat, onEditUserMessage, onSubmitEdit, onAction, onCitationClick, onPersonalizeTeaching }, ref) => {
    const { t } = useTranslation();
  const isContextExhaustedError = message.error?.kind === 'context_exhausted';
  const errorTitle = isContextExhaustedError ? t('chat.contextLimit.title') : message.error?.title;
  const errorDescription = isContextExhaustedError ? t('chat.contextLimit.description') : message.error?.description;
    const isGuru = message.role === 'guru';
    const navigate = useNavigate();
    const { profile } = useProfile();
    const { open: openSereneMind } = useSereneMind();
    // Extract any https:// URL from the guru's response as a fallback citation.
    // Covers: YouTube links, source references like "Source: https://...", inline citations.
    // No title is available for these — the panel falls back to the domain.
    const inlineCitations: Citation[] = isGuru
      ? Array.from(new Set(
        (message.content.match(/https?:\/\/[^\s)"'<>]+/g) ?? [])
          .filter(isUsableSourceUrl)
      )).map((url) => ({ url }))
      : [];
    const citations: Citation[] = (message.citations && message.citations.length > 0)
      ? message.citations.filter((c) => isUsableSourceUrl(c.url))
      : inlineCitations;
    // First served clip with a real YouTube id and start second; null hides the button.
    const personalizeRef = onPersonalizeTeaching && isGuru && !isStreaming
      ? citations.map((c) => buildPersonalizeRef(c)).find((r) => r !== null) ?? null
      : null;
    // Backend flag authoritative: when citations exist, only the backend's
    // personalize marker decides. Content-sniff is a fallback solely for
    // citation-less legacy bubbles whose flags were never persisted.
    const isAlreadyPersonalized =
      citations.length > 0
        ? citations.some(isPersonalizedCitation)
        : Boolean(message.content?.includes(PERSONALIZED_LABEL));
    const groundingState = message.groundingState ?? 'abstained';

    // Attribution integrity: a quoted teacher statement with no linked source
    // must be labelled unverified rather than rendered as doctrine (QA P1).
    // Exempt safety_redirect (distress/crisis preemption): those are hardcoded
    // compassionate templates, not RAG-retrieved doctrine, so they're never
    // citable — but they still legitimately quote a teacher for comfort, and
    // replacing them silently drops the crisis helpline text they carry.
    const hasUnverifiedAttribution = useMemo(() => {
      if (!isGuru || citations.length > 0 || groundingState === 'safety_redirect') return false;
      return /(?:Sri\s+(?:Preethaji|Krishnaji)|Preethaji|Krishnaji)[^.\n]{0,60}["“'”’]/.test(message.content);
    }, [isGuru, citations.length, groundingState, message.content]);

    const displayContent = useMemo(() => {
      if (!isGuru || citations.length > 0 || !hasUnverifiedAttribution) return message.content;
      return t('chat.unverifiedTeaching');
    }, [isGuru, citations.length, groundingState, hasUnverifiedAttribution, message.content, t]);

    const [showWisdomCard, setShowWisdomCard] = useState(false);
    const [copied, setCopied] = useState(false);
    const [saved, setSaved] = useState(false);
    const [savingMemory, setSavingMemory] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(message.content);
    const [noteSaved, setNoteSaved] = useState(false);
    const [sourcesOpen, setSourcesOpen] = useState(false);
    const [provenanceOpen, setProvenanceOpen] = useState(false);
    const [activeVideoCitation, setActiveVideoCitation] = useState<DiscourseCitation | null>(null);
    const [activeSearchCitation, setActiveSearchCitation] = useState<DiscourseCitation | null>(null);
    const editTextareaRef = useRef<HTMLTextAreaElement>(null);

    const primaryDiscourseCitation = useMemo<DiscourseCitation | null>(() => {
      if (citations && citations.length > 0) {
        const ytCitation = citations.find((c) => isUsableSourceUrl(c.url) && isYouTubeUrl(c.url));
        if (ytCitation) {
          const idx = citations.indexOf(ytCitation) + 1;
          return {
            index: idx > 0 ? idx : 1,
            url: ytCitation.url,
            title: ytCitation.title || ytCitation.source || undefined,
            speaker: resolveAttributionLabel(ytCitation) || ytCitation.speaker || undefined,
            speakerVerified: ytCitation.speakerVerified,
            startTimestamp: ytCitation.timestampSeconds,
            playbackStartSeconds: ytCitation.playbackStartSeconds,
            playbackEndSeconds: ytCitation.playbackEndSeconds,
            quote: ytCitation.quote || ytCitation.textSnippet,
          };
        }
      }
      return null;
    }, [citations]);

    // Served-teaching artifact: the first quote-bearing citation becomes the
    // distinct guru-teaching card. Suppressed while streaming, on errors, and
    // on crisis answers (same guards as the audio strip below).
    const guruTeachingCitation = useMemo(() => {
      if (!isGuru || isStreaming || message.error) return null;
      if (isCrisisAnswer(message.content)) return null;
      return selectGuruTeachingCitation(citations);
    }, [isGuru, isStreaming, message.error, message.content, citations]);

    // Verified only on the strict path: backend citationsVerified plus no
    // partial/failed/related flag and no source-unbacked attribution. The card
    // itself downgrades the badge for related/personalized turns.
    const isGuruTeachingVerified = guruTeachingCitation !== null
      && message.citationsVerified === true
      && message.verification?.passed !== false
      && message.verification?.partial !== true
      && message.guidancePlan?.attribution?.source_backed !== false;

    const { teachingBody, inquiryBody } = useMemo(() => {
      if (!isGuru || !displayContent) {
        return { teachingBody: displayContent, inquiryBody: null };
      }
      // Check for the '---' divider that separates Guru teaching from Atma Vichara inquiry
      const dividerMatch = displayContent.match(/(?:^|\n)\s*---\s*(?:\n|$)/);
      if (dividerMatch && dividerMatch.index !== undefined) {
        const teaching = displayContent.slice(0, dividerMatch.index).trim();
        const inquiry = displayContent.slice(dividerMatch.index + dividerMatch[0].length).trim();
        return { teachingBody: teaching, inquiryBody: inquiry || null };
      }
      // Also check for explicit inquiry heading if no '---'
      const inquiryHeaderMatch = displayContent.match(/(?:^|\n)\s*(?:\*+Atma Vichara[^*]*\*+|###?\s*Atma Vichara[^\n]*)\s*(?:\n|$)/i);
      if (inquiryHeaderMatch && inquiryHeaderMatch.index !== undefined) {
        const teaching = displayContent.slice(0, inquiryHeaderMatch.index).trim();
        const inquiry = displayContent.slice(inquiryHeaderMatch.index).trim();
        return { teachingBody: teaching, inquiryBody: inquiry || null };
      }
      return { teachingBody: displayContent, inquiryBody: null };
    }, [isGuru, displayContent]);

    const markdownComponents = useMemo(() => ({
      p: ({ children }: { children?: ReactNode }) => {
        const text = Children.toArray(children)
          .map((child) => (typeof child === 'string' ? child : ''))
          .join('');
        if (text.startsWith('[') && text.endsWith(']')) {
          return (
            <p className="mb-4 text-xs italic text-muted-foreground/80 border-b border-border/30 pb-2">
              {children}
            </p>
          );
        }
        if (text.includes("I don't have a recording that answers this part yet.")) {
          return (
            <p className="mb-4 text-sm italic text-muted-foreground/90 bg-muted/30 px-3 py-2 rounded-lg border border-border/30">
              {children}
            </p>
          );
        }
        if (text.trim() === 'Related, not a direct answer') {
          return (
            <p className="my-3 text-xs font-medium text-amber-600/90 dark:text-amber-400/90 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500/70" />
              {children}
            </p>
          );
        }
        return <p className="mb-4 last:mb-0">{children}</p>;
      },
      h1: ({ children }: { children?: React.ReactNode }) => (
        <h1 className="text-[1.35em] font-semibold text-foreground leading-snug mt-7 mb-3 first:mt-0">{children}</h1>
      ),
      h2: ({ children }: { children?: React.ReactNode }) => (
        <h2 className="text-[1.15em] font-semibold text-foreground leading-snug mt-6 mb-2.5 first:mt-0">{children}</h2>
      ),
      h3: ({ children }: { children?: React.ReactNode }) => (
        <h3 className="text-[1.02em] font-semibold text-foreground leading-snug mt-5 mb-2 first:mt-0">{children}</h3>
      ),
      h4: ({ children }: { children?: React.ReactNode }) => (
        <h4 className="text-[0.95em] font-semibold text-muted-foreground uppercase tracking-wide mt-5 mb-1.5 first:mt-0">{children}</h4>
      ),
      ul: ({ children }: { children?: React.ReactNode }) => (
        <ul className="my-4 space-y-2 pl-5 list-disc marker:text-ojas/70">{children}</ul>
      ),
      ol: ({ children }: { children?: React.ReactNode }) => (
        <ol className="my-4 space-y-2 pl-5 list-decimal marker:text-ojas marker:font-semibold marker:tabular-nums">{children}</ol>
      ),
      li: ({ children }: { children?: React.ReactNode }) => (
        <li className="leading-[1.7] pl-1">{children}</li>
      ),
      blockquote: ({ children }: { children?: React.ReactNode }) => (
        <blockquote className="border-l-[3px] border-ojas/50 pl-4 pr-3 py-2 my-4 bg-ojas/5 rounded-r-lg italic text-foreground/80">
          {children}
        </blockquote>
      ),
      pre: ({ children }: { children?: React.ReactNode }) => (
        <pre className="my-4 overflow-x-auto rounded-xl bg-muted/60 border border-border/40 p-4 text-[13px] leading-[1.6] font-mono">
          {children}
        </pre>
      ),
      code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
        const isBlock = Boolean(className);
        if (isBlock) {
          return <code className={`font-mono ${className ?? ''}`}>{children}</code>;
        }
        return (
          <code className="bg-ojas/10 text-ojas px-1.5 py-0.5 rounded text-[0.875em] font-mono border border-ojas/15">
            {children}
          </code>
        );
      },
      table: ({ children }: { children?: React.ReactNode }) => (
        <div className="my-4 overflow-x-auto rounded-xl border border-border/40">
          <table className="w-full text-[0.93em] border-collapse">{children}</table>
        </div>
      ),
      thead: ({ children }: { children?: React.ReactNode }) => <thead className="bg-muted/50">{children}</thead>,
      th: ({ children }: { children?: React.ReactNode }) => (
        <th className="text-left font-semibold px-3 py-2 border-b border-border/40 whitespace-nowrap">{children}</th>
      ),
      td: ({ children }: { children?: React.ReactNode }) => (
        <td className="px-3 py-2 border-b border-border/25 align-top last:border-b-0">{children}</td>
      ),
      strong: ({ children }: { children?: React.ReactNode }) => (
        <strong className="font-semibold text-foreground">{children}</strong>
      ),
      em: ({ children }: { children?: React.ReactNode }) => <em className="italic text-foreground/90">{children}</em>,
      hr: () => <hr className="border-0 border-t border-border/40 my-6" />,
      // `node` is react-markdown's AST; destructured so it never reaches the DOM.
      a: ({ href, children, node, ...rest }: React.ComponentPropsWithoutRef<'a'> & { node?: unknown }) => {
        const match = typeof href === 'string' ? href.match(/^#cite-(\d+)$/) : null;
        if (match) {
          const n = parseInt(match[1], 10);
          const citationData = (message.citations ?? [])[n - 1];
          const discourseCitation: DiscourseCitation = {
            index: n,
            url: citationData?.url || '#',
            title: citationData?.title || citationData?.source || 'Sacred Discourse Teaching',
            speaker: resolveAttributionLabel(citationData ?? {}) || undefined,
            speakerVerified: citationData?.speakerVerified,
            startTimestamp: citationData?.timestampSeconds,
            quote: citationData?.textSnippet || citationData?.quote,
          };
          return (
            <CitationBadge
              citation={discourseCitation}
              onOpenVideoModal={(c) => {
                setActiveVideoCitation(c);
                onCitationClick?.(message.id, n - 1);
              }}
              onOpenSearchModal={(c) => {
                setActiveSearchCitation(c);
                onCitationClick?.(message.id, n - 1);
              }}
            />
          );
        }
        return (
          <a href={href} {...rest} target="_blank" rel="noopener noreferrer" className="text-ojas underline-offset-2 hover:underline">
            {children}
          </a>
        );
      },
    }), [message.citations, message.id, onCitationClick]);

    // Auto-resize + cursor-end when editing opens or text changes
    useEffect(() => {
      const el = editTextareaRef.current;
      if (!el || !isEditing) return;
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
    }, [editValue, isEditing]);

    // Place cursor at end only once when edit mode opens
    useEffect(() => {
      if (!isEditing) return;
      const el = editTextareaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }, [isEditing]);
    const { toast } = useToast();
    const { createNote } = useNotes();

    const handleSaveAsNote = useCallback(async () => {
      const snippet = (queryText ? `**Question:** ${queryText}\n\n**Teaching:**\n` : '') + message.content;
      const note = await createNote({
        title: queryText ? queryText.slice(0, 80) : t('chat.teaching'),
        body: snippet,
        tags: ['from-chat'],
        source_message_id: message.id,
      });
      if (note) {
        setNoteSaved(true);
        setTimeout(() => setNoteSaved(false), 2000);
        toast({ title: t('chat.savedToNotes'), description: t('chat.savedToNotesDescription'), action: <Button variant="outline" size="sm" onClick={() => navigate('/profile?tab=memory')}>{t('profile.tabs.memory', 'Memory')}</Button> });
      } else {
        toast({ title: t('chat.noteSaveFailed', 'Could not save note. Check your connection and sign-in, then retry.'), variant: 'destructive' });
      }
    }, [createNote, message.content, message.id, queryText, toast, t, navigate]);

    const handleCopy = useCallback(async () => {
      try {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      } catch { /* ignore */ }
    }, [message.content]);

    // Per-message read-aloud. speak() cancels any other message's speech, so
    // one utterance plays at a time across the conversation.
    const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported, currentSentence } = useTextToSpeech();
    const plainText = useMemo(() =>
      message.content
        .replace(/```[\s\S]*?```/g, ' ')
        .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, ' ')
        .replace(/[#*_>`]/g, '')
        .replace(/\s+/g, ' ')
        .trim(),
      [message.content]);
    const sentences = useMemo(() => {
      if (!plainText) return [];
      return plainText.split(/(?<=[.!?।\n])\s+/).map((s) => s.trim()).filter(Boolean);
    }, [plainText]);
    const handleSpeak = useCallback(() => {
      if (isSpeaking) {
        stopSpeaking();
        return;
      }
      if (plainText) speak(plainText, message.language);
    }, [isSpeaking, stopSpeaking, speak, plainText, message.language]);

    const renderHighlightedText = () => {
      if (sentences.length === 0 || !currentSentence) {
        return <span>{plainText}</span>;
      }
      return (
        <span>
          {sentences.map((sentence, i) => (
            <span
              key={i}
              className={sentence === currentSentence ? 'bg-ojas/20 rounded px-0.5 transition-colors' : ''}
            >
              {sentence}
              {i < sentences.length - 1 ? ' ' : ''}
            </span>
          ))}
        </span>
      );
    };

    const handleSaveToMemory = useCallback(async () => {
      if (saved || savingMemory) return;
      setSavingMemory(true);
      try {
        // Use the user's question + a short slice of the answer as the saved fact.
        const snippet = (queryText ? `Q: ${queryText}\nA: ` : '') + message.content.slice(0, 600);
        await memoryApi.add(snippet);
        setSaved(true);
        toast({ title: t('chat.savedToMemory'), description: t('chat.guruWillRecall') });
      } catch (e) {
        const err = e as { code?: string; message?: string };
        if (err?.code === 'unauthorized') {
          toast({ title: t('chat.signInSaveMemories'), description: t('chat.memoryUnavailable'), variant: 'destructive' });
        } else {
          toast({ title: t('chat.couldNotSave'), description: err?.message ?? t('common.retry'), variant: 'destructive' });
        }
      } finally {
        setSavingMemory(false);
      }
    }, [saved, savingMemory, queryText, message.content, toast, t]);

    return (
      <>
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: Math.min(index * 0.03, 0.15) }}
          className={`group message-bubble flex items-start gap-2 ${isGuru ? 'justify-start' : 'justify-end'}`}
          data-message-id={message.id}
        >
          {isGuru && (
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-ojas/15 to-ojas/5 border border-ojas/25 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-[0_0_12px_hsl(var(--ojas)/0.12)]">
              <Sparkles className="w-3.5 h-3.5 text-ojas animate-pulse-soft" />
            </div>
          )}
          {/* The guru answer is long-form prose — it gets the full reading column
              (the parent is already capped at max-w-3xl), the way Claude/ChatGPT
              lay out assistant turns. Capping it at 75% made every answer a
              narrow ragged strip. The user's own turn stays a right-aligned bubble. */}
          <div className={`${isEditing ? 'w-full max-w-[95%] sm:max-w-[85%]' : isGuru ? 'flex-1 min-w-0 w-full' : 'max-w-[85%] sm:max-w-[75%]'} flex flex-col gap-1 ${isGuru ? 'items-start' : 'items-end'}`}>
            {/* Message body */}
            <div
className={`relative ${isGuru ? 'w-full' : 'w-fit'} transition-all duration-200 ${isGuru
                    ? 'rounded-2xl rounded-tl-sm px-0 py-1 sm:py-1.5 text-[15px] leading-[1.75] text-foreground font-normal'
                    : isEditing
                      ? 'bg-card border border-hairline rounded-2xl p-3 sm:p-4 shadow-sm'
                      : 'bg-chat-user rounded-2xl p-3 sm:p-4 text-[15px] leading-[1.55] font-normal shadow-sm'
                }`}
            >
              <div
                className={`break-words ${isGuru ? '' : 'whitespace-pre-wrap'}`}
              >
                {isGuru ? (
                  message.error ? (
                    <div
                      role="alert"
                      aria-live="assertive"
                      className="not-prose rounded-xl border border-destructive/30 bg-destructive/5 px-3.5 py-3 text-foreground/90"
                    >
                      <div className="flex items-start gap-2.5">
                        <AlertTriangle className="w-4 h-4 mt-0.5 text-destructive shrink-0" aria-hidden />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-destructive leading-tight">{errorTitle}</p>
                          <p className="text-sm text-foreground/80 mt-1 leading-relaxed">{errorDescription}</p>
                          {message.error.detail && (
                            <details className="mt-1.5">
                              <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground/70 select-none">
                                {t('chat.technicalDetail')}
                              </summary>
                              <pre className="mt-1 text-xs text-muted-foreground whitespace-pre-wrap break-all font-mono bg-background/40 rounded px-2 py-1.5 border border-border/40">
                                {message.error.detail}
                              </pre>
                            </details>
                          )}
                          <div className="flex flex-wrap gap-2 mt-2.5">
                            {(message.error.actionLabel === 'retry' || !message.error.actionLabel) && onRegenerate && (
                              <button
                                type="button"
                                onClick={onRegenerate}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <RefreshCw className="w-3 h-3" aria-hidden />
                                {t('common.retry')}
                              </button>
                            )}
                            {message.error.actionLabel === 'sign_in' && (
                              <button
                                type="button"
                                onClick={() => navigate('/auth')}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <LogIn className="w-3 h-3" aria-hidden />
                                {t('chat.signInAgain', 'Sign in again')}
                              </button>
                            )}
                            {message.error.actionLabel === 'new_chat' && onStartNewChat && (
                              <button
                                type="button"
                                onClick={onStartNewChat}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <RefreshCw className="w-3 h-3" aria-hidden />
                                {t('chat.contextLimit.continueNewChat')}
                              </button>
                            )}
                            {message.error.actionLabel === 'reload' && (
                              <button
                                type="button"
                                onClick={() => window.location.reload()}
                                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-destructive hover:text-destructive/80 border border-destructive/30 hover:border-destructive/50 hover:bg-destructive/10 rounded-md px-2.5 py-1 transition-colors"
                              >
                                <RefreshCw className="w-3 h-3" aria-hidden />
                                {t('chat.reload', 'Reload')}
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <>
                      <TeachingGroundingCard
                        citations={citations}
                        teachingPreview={message.teachingPreview}
                        groundingState={message.groundingState}
                        citationsVerified={message.citationsVerified}
                        verification={message.verification}
                        guidanceAttribution={message.guidancePlan?.attribution}
                      />
                      {personalizeRef && !isAlreadyPersonalized && (
                        <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
                          <button
                            type="button"
                            data-testid="personalize-teaching"
                            onClick={() => onPersonalizeTeaching?.(personalizeRef)}
                            aria-describedby={`personalize-note-${message.id}`}
                            className="inline-flex items-center gap-1.5 rounded-full border border-border/60 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                            {t('chat.personalizeTeaching', 'Personalize this teaching')}
                          </button>
                          <p id={`personalize-note-${message.id}`} className="text-[11px] text-muted-foreground" data-testid="personalize-note">
                            {t('chat.personalizeNote', 'Uses only memories you chose to save.')}{' '}
                            <button
                              type="button"
                              onClick={() => navigate('/profile?tab=memory')}
                              className="underline underline-offset-2 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                            >
                              {t('chat.personalizeManage', 'Review what is saved')}
                            </button>
                          </p>
                        </div>
                      )}
                      {guruTeachingCitation && (
                        <div className="mb-3.5 w-full">
                          <GuruTeachingCard
                            citation={guruTeachingCitation}
                            verified={isGuruTeachingVerified}
                            related={message.verification?.direct === false}
                            index={citations.indexOf(guruTeachingCitation) + 1}
                            onPlay={(c) => {
                              // Playing a real served clip is the proof for the journey's teaching step.
                              completeStep('teaching');
                              setActiveVideoCitation(c);
                              onCitationClick?.(message.id, c.index - 1);
                            }}
                          />
                        </div>
                      )}
                      <div className="text-[15px] leading-[1.75] text-foreground selection:bg-ojas/20">
                      {/* While streaming with no content, render nothing — the single
                        ThinkingPills indicator in ChatInterface is the source of truth.
                        This prevents two simultaneous "thinking" indicators. */}
                      {isStreaming && !message.content ? null : (
                        <>
                          {/* 1. PRIMARY HERO: DIRECT GURU TEACHING WORDS FROM CORPUS */}
                          <div className="prose prose-stone dark:prose-invert max-w-none text-[15px] leading-[1.75] text-foreground">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              urlTransform={safeUrlTransform}
                              components={markdownComponents}
                            >
                              {injectCitationLinks(teachingBody, (message.citations ?? []).length)}
                            </ReactMarkdown>
                          </div>

                          {/* Invariant 1: platform copy that accompanies a served clip
                              (compassion framing, relationship/addiction safety
                              boundaries, the human support line) is its own block — it
                              is never concatenated into the teacher's verbatim words. */}
                          {isGuru && !isStreaming && (message.safetyNotices?.length ?? 0) > 0 && (
                            <div
                              data-testid="safety-notices"
                              className="mt-3 space-y-2 rounded-lg border border-border/50 bg-muted/30 p-3 text-[13px] leading-relaxed text-muted-foreground"
                            >
                              {message.safetyNotices?.map((notice, noticeIndex) => (
                                <p key={noticeIndex} className="whitespace-pre-wrap">
                                  {notice}
                                </p>
                              ))}
                            </div>
                          )}

                          {/* Supportive Seeker UX for first-person abstain */}
                          {/* Not under a crisis/compassion reply or an outage: suggested questions there are noise. */}
                          {isGuru && !isStreaming && !message.error && isFirstPersonAbstainMessage(message) &&
                            !isCrisisAnswer(message.content) &&
                            message.verification?.method !== 'first_person_distress_compassion' &&
                            message.verification?.method !== 'first_person_store_unavailable' && (
                            <AbstainHelpCard onAction={onAction} className="mt-3.5" />
                          )}

                          {/* Attached directly beneath Guru words: Playable source-recording strip */}
                          {isGuru && !isStreaming && !message.error && primaryDiscourseCitation && !isCrisisAnswer(message.content) && (
                            <DiscourseAudioStrip
                              citation={primaryDiscourseCitation}
                              onOpenVideoModal={(c) => {
                                setActiveVideoCitation(c);
                                onCitationClick?.(message.id, c.index - 1);
                              }}
                            />
                          )}

                          {/* 2. SECONDARY: ATMA VICHARA CONTEMPLATIVE INQUIRY */}
                          {isGuru && inquiryBody && !isStreaming && !message.error && (
                            <aside
                              data-testid="atma-vichara-inquiry"
                              aria-label="Optional reflection prompt inspired by the cited teaching"
                              className="my-3.5 rounded-2xl border border-saffron-gold/25 bg-gradient-to-br from-saffron-gold/10 via-card to-card p-3.5 shadow-sm backdrop-blur-md"
                            >
                              <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-saffron-gold mb-2">
                                <Sparkles className="h-3.5 w-3.5 text-saffron-gold" aria-hidden="true" />
                                <span>Atma Vichara · Contemplative Inquiry</span>
                              </div>
                              <p
                                data-testid="reflection-prompt-label"
                                className="mb-2 text-[11px] font-normal normal-case tracking-normal text-muted-foreground"
                              >
                                Optional reflection prompt inspired by the cited teaching. It is not the teacher's own words.
                              </p>
                              <div className="font-serif italic text-[14.5px] leading-relaxed text-foreground/90 pl-1">
                                <ReactMarkdown
                                  remarkPlugins={[remarkGfm]}
                                  urlTransform={safeUrlTransform}
                                  components={markdownComponents}
                                >
                                  {injectCitationLinks(inquiryBody, (message.citations ?? []).length)}
                                </ReactMarkdown>
                              </div>
                            </aside>
                          )}

                          {/* 3. "DEEPEN & TUNE" 4-QUADRANT INTERACTIVE CONTROL BAR */}
                          {FEATURE_FLAGS.deepenAndTuneBar && isGuru && !isStreaming && !message.error && !message.isWelcome && !isCrisisAnswer(message.content) && !isFirstPersonAbstainMessage(message) && (
                            <DeepenAndTuneBar
                              message={message}
                              queryText={queryText}
                              citation={primaryDiscourseCitation}
                              onOpenVideoModal={(c) => {
                                setActiveVideoCitation(c);
                                onCitationClick?.(message.id, c.index - 1);
                              }}
                              onOpenSearchModal={(c) => {
                                setActiveSearchCitation(c);
                                onCitationClick?.(message.id, c.index - 1);
                              }}
                            />
                          )}
                        </>
                      )}
                      </div>
                    </>
                  )
                ) : isEditing ? (
                  <div className="flex flex-col gap-2.5 w-full">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1 h-1 rounded-full bg-ojas animate-pulse" />
                      <p className="text-[11px] text-ojas/70 font-medium">
                        {t('chat.editingLabel')}
                      </p>
                    </div>
                    <textarea
                      ref={editTextareaRef}
                      value={editValue}
                      onChange={(e) => {
                        setEditValue(e.target.value);
                        // immediate height sync on change
                        const el = e.currentTarget;
                        el.style.height = 'auto';
                        el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
                      }}
                      rows={2}
                      className="w-full bg-background/80 border border-ojas/30 rounded-xl p-3 text-[14px] text-foreground placeholder:text-muted-foreground outline-none focus:border-ojas/60 focus:ring-2 focus:ring-ojas/15 resize-none leading-relaxed overflow-y-auto"
                      style={{ minHeight: '64px', maxHeight: '260px' }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          if (editValue.trim() && editValue.trim() !== message.content) {
                            onSubmitEdit?.(message.id, editValue.trim());
                          }
                          setIsEditing(false);
                        }
                        if (e.key === 'Escape') {
                          setEditValue(message.content);
                          setIsEditing(false);
                        }
                      }}
                    />
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] text-muted-foreground/60">
                        {t('chat.keybindSave')}
                      </span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => { setEditValue(message.content); setIsEditing(false); }}
                          className="px-3 py-1.5 rounded-lg text-[12px] font-medium text-muted-foreground hover:bg-muted/70 transition-colors"
                        >
                          {t('chat.cancelEdit')}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            const trimmed = editValue.trim();
                            if (trimmed && trimmed !== message.content) {
                              onSubmitEdit?.(message.id, trimmed);
                            }
                            setIsEditing(false);
                          }}
                          disabled={!editValue.trim() || editValue.trim() === message.content}
                          className="px-3 py-1.5 rounded-lg text-[12px] font-semibold bg-ojas text-primary-foreground hover:bg-ojas-light disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
                        >
                          {t('chat.saveResend')}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <UserMessageContent
                    content={message.content}
                    showMoreLabel={t('common.readMore', 'Read more')}
                    showLessLabel={t('common.showLess', 'Show less')}
                  />
                )}
                {isGuru && isSpeaking && plainText && (
                  <span className="block mt-2 text-foreground/80" aria-live="polite">
                    {renderHighlightedText()}
                  </span>
                )}
                {isStreaming && (
                  <span className="inline-flex items-center gap-1 ml-0.5 align-text-bottom">
                    {/* Serene UI: warm-sand breathing ring around the cursor.
                        Uses tailwind animate-breathe + animate-pulse-soft keyframes
                        registered in tailwind.config.ts (serene namespace). */}
                    <span
                      className="inline-block w-2 h-2 rounded-full bg-ojas/30 animate-breathe"
                      aria-hidden
                    />
                    <motion.span
                      animate={{ opacity: [1, 0] }}
                      transition={{ duration: 0.6, repeat: Infinity, repeatType: 'reverse' }}
                      className="inline-block w-[2px] h-[1em] bg-ojas"
                    />
                  </span>
                )}
              </div>

              {isGuru && message.personalizationProvenance?.used && !isStreaming && !message.error && !isCrisisAnswer(message.content) && (
                <details className="mt-2 rounded-xl border border-ojas/15 bg-ojas/[0.035] px-3 py-2 text-[11px] text-muted-foreground max-w-xl">
                  <summary className="cursor-pointer select-none text-ojas/80 font-medium">
                    ✨ {t('chat.personalization.header')}
                  </summary>
                  <div className="mt-2 space-y-1.5 leading-relaxed">
                    {message.personalizationProvenance.profile_preferences && (
                      <p>• {t('chat.personalization.profileEnabled')}</p>
                    )}
                    {message.personalizationProvenance.personal_memory && (
                      <p>• {t('chat.personalization.personalMemoryUsed')}</p>
                    )}
                    {(message.personalizationProvenance.private_graph_links ?? 0) > 0 && (
                      <p>• {t('chat.personalization.graphMatched', { count: message.personalizationProvenance.private_graph_links })}</p>
                    )}
                    <p className="text-muted-foreground/70">{t('chat.personalization.privateMemoryNotShown')}</p>
                  </div>
                </details>
              )}

              {/* Inline action buttons for the latest guru message only.
                  Suppressed on crisis/helpline answers and first-person abstain. */}
              {isGuru && isLastGuru && message.content && !isStreaming && onAction && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && !isFirstPersonAbstainMessage(message) && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, delay: 0.04 }}
                  className="w-full"
                >
                  <InlineActions messageContent={message.content} onAction={onAction} />
                </motion.div>
              )}

              {/* Engagement card: "Did this help?" — shown for the last guru answer.
                  Never shown on crisis/helpline answers — a feedback widget under a
                  helpline is unsafe (see isCrisisAnswer). */}
              {isGuru && isLastGuru && message.content && !isStreaming && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22, delay: 0.08 }}
                  className="w-full"
                >
                  <EngagementCard
                    messageId={message.id}
                    messageContent={message.content}
                    queryText={queryText}
                    qualityMetadata={{
                      message_id: message.id,
                      trace_id: message.traceId,
                      latency_ms: message.latencyMs,
                      model_used: message.modelUsed,
                      model_provider: message.modelProvider,
                      query_tier: message.queryTier,
                      faithfulness_score: message.faithfulnessScore,
                      relevancy_score: message.relevancyScore,
                      hallucination_flag: message.hallucinationFlag,
                      verification: message.verification,
                      citations_verified: message.citationsVerified,
                      citation_count: message.citations?.length ?? 0,
                      answer_length_chars: message.content.length,
                      answer_length_words: message.content.trim() ? message.content.trim().split(/\s+/).length : 0,
                      grounding_state: message.groundingState,
                      route_decision: message.queryTier,
                    }}
                  />
                </motion.div>
              )}


              {/* Faculty review labels: build-flag + signed-in gated inside the gate;
                  never under crisis/helpline answers. */}
              {isGuru && message.content && !isStreaming && !message.error && !message.isWelcome && !message.content.includes('_Stopped by you._') && (
                <FacultyReviewGate
                  crisis={isCrisisAnswer(message.content)}
                  traceId={message.traceId}
                  messageId={message.id}
                  model={message.modelUsed}
                  releaseManifest={message.releaseManifest ?? null}
                />
              )}

              {/* Practice nudge: offer to turn the last answer into a guided Serene
                  Mind session. Suppressed on crisis/helpline and abstain answers (which have their own dedicated practice trigger). */}
              {isGuru && isLastGuru && message.content && !isStreaming && !message.error && !message.content.includes('_Stopped by you._') && !isCrisisAnswer(message.content) && !isFirstPersonAbstainMessage(message) && (
                <div
                  className="mt-2 flex items-center gap-2 text-[12px]"
                  title={t('chat.practiceNudge.body')}
                >
                  <span className="text-muted-foreground">{t('chat.practiceNudge.title')}</span>
                  <button
                    onClick={() => openSereneMind('audio', true)}
                    className="flex-shrink-0 rounded-full border border-ojas/30 px-2.5 py-1 text-[11px] font-medium text-ojas hover:bg-ojas/10 transition-colors whitespace-nowrap"
                  >
                    {t('chat.practiceNudge.cta')}
                  </button>
                </div>
              )}

              {/* Hover-only timestamp */}
              <time className="opacity-0 group-hover:opacity-60 text-[11px] text-muted-foreground transition-opacity mt-1 block">
                {formatTime(message.timestamp)}
              </time>

              {/* Guru hover actions — elevated Copy, Listen, and Share Wisdom as primary visible action buttons */}
              {isGuru && message.content && !message.error && !isStreaming && !message.content.includes('_Stopped by you._') && (
                <div className="flex items-center gap-0.5 mt-2 opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 max-md:opacity-100 transition-opacity duration-200">
                  <button
                    onClick={handleCopy}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={copied ? t('common.copied') : t('chat.copyResponse')}
                    aria-label={copied ? t('common.copied') : t('chat.copyResponse')}
                  >
                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </button>
                  {ttsSupported && (
                    <button
                      onClick={handleSpeak}
                      aria-pressed={isSpeaking}
                      className={`p-1 rounded-full transition-colors ${isSpeaking
                          ? 'bg-ojas/15 text-ojas'
                          : 'hover:bg-ojas/10 text-muted-foreground hover:text-ojas'
                        }`}
                      title={isSpeaking ? t('chat.stopReading') : t('chat.readAloud')}
                      aria-label={isSpeaking ? t('chat.stopReading') : t('chat.readAloud')}
                    >
                      {isSpeaking ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                    </button>
                  )}
                  <button
                    onClick={() => setShowWisdomCard(true)}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={t('chat.shareWisdomCard')}
                    aria-label={t('chat.shareWisdomCard')}
                  >
                    <Share2 className="w-4 h-4" />
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                        title={t('common.more', 'More')}
                        aria-label={t('common.more', 'More')}
                      >
                        <MoreHorizontal className="w-4 h-4" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                      {isLastGuru && onRegenerate && (
                        <DropdownMenuItem onClick={onRegenerate}>
                          <RotateCcw className="w-4 h-4 mr-2" />
                          {t('chat.regenerate')}
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuItem onClick={handleSaveToMemory} disabled={saved || savingMemory}>
                        <Bookmark className={`w-4 h-4 mr-2 ${saved ? 'fill-current' : ''}`} />
                        {saved ? t('chat.savedToMemory') : t('chat.saveToMemory')}
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={handleSaveAsNote}>
                        <StickyNote className={`w-4 h-4 mr-2 ${noteSaved ? 'fill-current' : ''}`} />
                        {noteSaved ? t('chat.savedToNotes') : t('chat.saveAsNote')}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <LanguageTranslateButton message={message} />
                </div>
              )}

            </div>

            {/* EU AI Act Article 50 Disclosure & Provenance Badge */}
            {isGuru && !message.error && (message.content || !isStreaming) && (
              <div className="mt-2 select-none flex items-center gap-2">
                <EuAiBadge
                  originType="ai_generated"
                  onClick={() => setProvenanceOpen(true)}
                  size="sm"
                />
              </div>
            )}

            {/* User hover actions */}
            {!isGuru && message.content && !isStreaming && !isEditing && (
              <div className="flex items-center justify-end gap-0.5 opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100 max-md:opacity-100 transition-opacity duration-200 mt-1 mr-1">
                <button
                  onClick={handleCopy}
                  className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                  title={copied ? t('common.copied') : t('chat.copyQuestion')}
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                </button>
                {(onSubmitEdit || onEditUserMessage) && (
                  <button
                    onClick={() => {
                      if (onSubmitEdit) {
                        setEditValue(message.content);
                        setIsEditing(true);
                      } else if (onEditUserMessage) {
                        onEditUserMessage(message);
                      }
                    }}
                    className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
                    title={t('chat.editResend')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                )}
              </div>
            )}

            {/* Memory provenance — surfaces facts the Guru recalled from your reflections */}
            {isGuru && message.memoriesUsed && message.memoriesUsed.length > 0 && (
              <details className="w-full rounded-lg border border-ojas/15 bg-ojas/5 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-medium text-ojas/80 select-none">
                  {t('chat.recalledFromReflections', { count: message.memoriesUsed.length })}
                </summary>
                <ul className="mt-2 space-y-1 list-disc pl-4 text-muted-foreground">
                  {message.memoriesUsed.slice(0, 6).map((m, i) => (
                    <li key={i}>{m}</li>
                  ))}
                </ul>
              </details>
            )}

            {/* Follow-up suggestions as clickable chips */}
            {FEATURE_FLAGS.suggestedFollowUps && isGuru && message.followUpSuggestions && message.followUpSuggestions.length > 0 && !isStreaming && onAction && !message.content.includes('_Stopped by you._') && (
              <div className="w-full mt-1">
                <p className="text-[10px] text-muted-foreground/60 mb-2 pl-0.5">{t('chat.suggestedFollowUps')}</p>
                <div className="flex flex-wrap gap-1.5">
                  {message.followUpSuggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => onAction(suggestion)}
                      className="text-[11px] px-2.5 py-1 rounded-full border border-ojas/20 bg-ojas/5 hover:bg-ojas/10 hover:border-ojas/40 text-foreground/80 hover:text-foreground transition-all"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Sources / Citations status. When there ARE citations, this merges into
                the REFERENCES <details> summary below instead of rendering here —
                same "grounded, N sources" fact was showing twice in two stacked
                boxes. Zero-citation states (reflective guidance, safety redirect,
                unverified attribution, system error) have nothing to expand into,
                so they keep their own standalone row. Exception: plain abstains
                already say "no direct discourse" in the grounding card above —
                repeating "no grounded teaching" here stacks the same fact twice,
                so the row is skipped unless it carries a confidence score or a
                distinct state (safety/system/unverified). */}
            {FEATURE_FLAGS.responseProvenance && isGuru && !isStreaming && !message.error && !message.isWelcome && citations.length === 0 && (message.content || typeof message.confidenceScore === 'number' || hasUnverifiedAttribution) && (groundingState !== 'abstained' || typeof message.confidenceScore === 'number' || hasUnverifiedAttribution) && (
              <div
                data-testid="response-provenance"
                role="status"
                className={cn(
                  'w-full flex items-center gap-2.5 rounded-xl border px-3 py-2 text-xs text-muted-foreground',
                  groundingState === 'grounded'
                    ? 'border-ojas/15 bg-ojas/[0.045]'
                    : 'border-amber-500/40 bg-amber-500/[0.07]',
                )}
              >
                <Shield
                  className={cn('h-3.5 w-3.5 shrink-0', groundingState === 'grounded' ? 'text-ojas' : 'text-amber-500')}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1 leading-tight">
                  <p className="font-medium text-foreground/80">
                    {groundingState === 'safety_redirect'
                      ? 'Safety support'
                      : groundingState === 'system_error'
                        ? 'Verification unavailable'
                        : hasUnverifiedAttribution
                          ? 'Unverified attribution'
                          : 'Reflective guidance'}
                  </p>
                  <p>
                    {groundingState === 'safety_redirect'
                      ? 'Safety guidance is shown instead of doctrine attribution.'
                      : groundingState === 'system_error'
                        ? 'The response could not be verified. Please retry before relying on it.'
                        : hasUnverifiedAttribution
                          ? 'This answer quotes a teacher without a linked source — treat the wording as paraphrase, not a verified quotation.'
                          : 'No grounded teaching was found for this response; treat it as reflective guidance.'}
                  </p>
                </div>
              </div>
            )}
            {isGuru && !isStreaming && <LiveLogisticsCards events={message.liveLogisticsEvents} />}
            {/* Attribution-only guidance ("Guidance inspired by retrieved teachings")
                already duplicates the response-provenance grounding badge below —
                only render this card when it carries actionable content. */}
            {isGuru && !isStreaming && message.guidancePlan
              && (message.guidancePlan.action_step || message.guidancePlan.reflection_prompt)
              && !isCrisisAnswer(message.content) && (
              <GuidancePlanCard plan={message.guidancePlan} />
            )}
            {isGuru && !isStreaming && message.sereneMindOffer?.triggered && !isCrisisAnswer(message.content) && (
              <SereneMindOfferCard offer={message.sereneMindOffer} />
            )}

            {isGuru && citations.length > 0 && (
              <div className="mt-2.5 flex items-center">
                <button
                  type="button"
                  onClick={() => setSourcesOpen(true)}
                  className="inline-flex items-center gap-2 rounded-full border border-hairline bg-card/80 hover:bg-card hover:border-ojas/40 px-3 py-1 text-xs text-muted-foreground hover:text-foreground transition-all shadow-sm"
                  aria-label={t('chat.viewSources')}
                  title={t('chat.references')}
                >
                  <Sparkles className="w-3.5 h-3.5 text-ojas shrink-0" aria-hidden="true" />
                  <span className="sr-only">{t('chat.references')}</span>
                  <span className="font-medium text-foreground">
                    {t('chat.sourcesCitedCount', { count: citations.length, defaultValue: `${citations.length} Sources` })}
                  </span>
                  <span className="text-muted-foreground/60">·</span>
                  <span className="text-muted-foreground truncate max-w-[200px]">
                    {getTeacherSummary(citations)}
                  </span>
                  <BookOpen className="w-3.5 h-3.5 text-muted-foreground/70 ml-0.5 shrink-0" aria-hidden="true" />
                </button>
              </div>
            )}

            {/* ponytail: CitationPanel = richer source view (YouTube embeds + quotes) triggered from References badge */}
            {isGuru && citations.length > 0 && (
              <CitationPanel
                isOpen={sourcesOpen}
                onClose={() => setSourcesOpen(false)}
                citations={citations}
              />
            )}

            {/* EU AI Act Article 50 Provenance Drawer */}
            {isGuru && (
              <ProvenanceDrawer
                isOpen={provenanceOpen}
                onClose={() => setProvenanceOpen(false)}
                message={message}
              />
            )}

            {/* Timestamped YouTube Discourse Video Player Modal */}
            <DiscourseVideoModal
              isOpen={!!activeVideoCitation}
              onClose={() => setActiveVideoCitation(null)}
              citation={activeVideoCitation}
            />

            {/* In-Situ Link & Wisdom Inspector Modal */}
            <LinkSearchModal
              isOpen={!!activeSearchCitation}
              onClose={() => setActiveSearchCitation(null)}
              citation={activeSearchCitation}
              onPlayVideo={(c) => {
                setActiveSearchCitation(null);
                setActiveVideoCitation(c as DiscourseCitation);
              }}
            />
          </div>

        </motion.div>

        {/* Wisdom Card Modal — lazy-loaded chunk (P1-AI-16); Suspense keeps the
            open state snappy while the chunk loads. */}
        {showWisdomCard && createPortal(
          <Suspense fallback={null}>
            <LazyWisdomCardGenerator
              isOpen={showWisdomCard}
              onClose={() => setShowWisdomCard(false)}
              content={message.content}
            />
          </Suspense>,
          document.body
        )}
      </>
    );
  }
);

ChatMessageInner.displayName = 'ChatMessageInner';

// React.memo to skip re-renders when props haven't changed.
// During streaming, only the actively-streaming message changes.
// P1-AI-17: comparator previously omitted queryText / onSubmitEdit /
// onEditUserMessage — a changing query (e.g. the next message's question)
// or a fresh edit handler then kept rendering stale output and captured
// stale closures for edit/submit. All are primitives or stable identities
// from MessageList, so reference comparison is safe. (Streaming content
// flows through `message.content`, which is compared above.)
export const ChatMessage = memo(ChatMessageInner, (prev, next) => {
  return (
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.feedback === next.message.feedback &&
    prev.isStreaming === next.isStreaming &&
    prev.index === next.index &&
    prev.isLastGuru === next.isLastGuru &&
    prev.message.language === next.message.language &&
    prev.message.guidancePlan === next.message.guidancePlan &&
    prev.message.answerEvidence === next.message.answerEvidence &&
    prev.message.groundingState === next.message.groundingState &&
    prev.message.verification === next.message.verification &&
    prev.message.citationsVerified === next.message.citationsVerified &&
    // Citation-only updates (citations arriving after content) must re-render:
    // personalizeRef derives from citations, so a stale false here hides the
    // Personalize button and the citation panel. Arrays are replaced wholesale.
    prev.message.citations === next.message.citations &&
    prev.queryText === next.queryText &&
    prev.onAction === next.onAction &&
    prev.onRegenerate === next.onRegenerate &&
    prev.onStartNewChat === next.onStartNewChat &&
    prev.onSubmitEdit === next.onSubmitEdit &&
    prev.onEditUserMessage === next.onEditUserMessage &&
    prev.onCitationClick === next.onCitationClick &&
    prev.onPersonalizeTeaching === next.onPersonalizeTeaching
  );
}) as typeof ChatMessageInner;
(ChatMessage as { displayName?: string }).displayName = 'ChatMessage';

const toBcp47LanguageTag = (language: string | undefined): string => {
  const normalized = (language || 'en').trim();
  if (normalized.includes('-')) return normalized;
  return normalized === 'en' ? 'en-IN' : `${normalized}-IN`;
};


export const LanguageTranslateButton = ({ message }: { message: Message }) => {
  const { t } = useTranslation();
  const { profile } = useProfile();
  const [translated, setTranslated] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const sourceLanguage = toBcp47LanguageTag(message.language);
  const preferredTarget = toBcp47LanguageTag(profile?.preferredLanguage);
  const targetLanguage = sourceLanguage === preferredTarget ? 'en-IN' : preferredTarget;
  if (targetLanguage === sourceLanguage) return <></>;

  const handleTranslate = async () => {
    if (translated) {
      setTranslated(null);
      return;
    }
    setLoading(true);
    const result = await translateText(message.content, targetLanguage, sourceLanguage);
    setTranslated(result || t('chat.translationUnavailable'));
    setLoading(false);
  };

  return (
    <div className="relative">
      <button
        onClick={handleTranslate}
        disabled={loading}
        className="p-1 rounded-full hover:bg-ojas/10 text-muted-foreground hover:text-ojas transition-colors"
        title={translated ? t('chat.showOriginal') : t('chat.translateTo', { lang: targetLanguage.split('-')[0] })}
      >
        {loading ? (
          <span className="w-3 h-3 block rounded-full border border-ojas border-t-transparent animate-spin" />
        ) : (
          <Languages className="w-4 h-4" />
        )}
      </button>
      <AnimatePresence>
        {translated && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="absolute bottom-full right-0 mb-2 w-72 p-2 rounded-lg bg-popover border border-border shadow-lg text-xs text-popover-foreground z-50"
          >
            <p className="leading-relaxed">{translated}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
const formatTime = (date: Date): string => {
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};
