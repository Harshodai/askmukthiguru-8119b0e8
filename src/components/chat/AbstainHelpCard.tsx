import React from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles, HelpCircle, BookOpen, Wind, Play, ArrowRight } from 'lucide-react';
import { useSereneMind } from '@/components/common/SereneMindProvider';
import { cn } from '@/lib/utils';

export interface AbstainHelpCardProps {
  onAction?: (query: string) => void;
  className?: string;
}

export const ABSTAIN_BANK_QUESTIONS = [
  'What is the difference between a beautiful state and a suffering state?',
  'How does meditation dissolve fear and anger?',
  'How can I cultivate inner peace through Soul Sync?',
] as const;

export const ABSTAIN_OKF_CONCEPTS = [
  'Beautiful State',
  'Dissolving Conflict',
  'Inner Peace',
  'Soul Sync Meditation',
  'Witness Consciousness',
] as const;

export const AbstainHelpCard: React.FC<AbstainHelpCardProps> = ({ onAction, className }) => {
  const { t } = useTranslation();
  const { open: openSereneMind } = useSereneMind();

  return (
    <div
      data-testid="abstain-help-card"
      className={cn(
        'rounded-2xl border border-ojas/20 dark:border-ojas/30 bg-gradient-to-br from-ojas/[0.04] via-card to-card p-4 sm:p-5 shadow-sm space-y-4 my-3',
        className,
      )}
    >
      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-ojas">
          <Sparkles className="h-4 w-4 text-ojas flex-shrink-0" aria-hidden="true" />
          <span>{t('chat.abstainHelp.title', 'Explore Verified Teachings')}</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {t(
            'chat.abstainHelp.subtitle',
            "While this specific question doesn't have an exact recorded discourse match, you can explore foundational principles or begin a centering practice:",
          )}
        </p>
      </div>

      {/* 3 Tappable Verified Bank Questions */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-foreground/80">
          <HelpCircle className="h-3.5 w-3.5 text-ojas" aria-hidden="true" />
          <span>{t('chat.abstainHelp.questionsHeader', 'Verified Inquiries')}</span>
        </div>
        <div className="grid gap-1.5">
          {ABSTAIN_BANK_QUESTIONS.map((question, idx) => (
            <button
              key={question}
              type="button"
              data-testid={`abstain-question-${idx}`}
              onClick={() => onAction?.(question)}
              className="group flex items-center justify-between gap-3 text-left w-full p-2.5 rounded-xl border border-border/60 bg-background/60 hover:bg-ojas/[0.07] hover:border-ojas/40 transition-all duration-200 text-xs sm:text-[13px] text-foreground/90 hover:text-foreground shadow-2xs"
            >
              <span className="leading-snug">{question}</span>
              <ArrowRight
                className="h-3.5 w-3.5 text-muted-foreground group-hover:text-ojas group-hover:translate-x-0.5 transition-all flex-shrink-0"
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
      </div>

      {/* Verified OKF Concept Chips */}
      <div className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-foreground/80">
          <BookOpen className="h-3.5 w-3.5 text-ojas" aria-hidden="true" />
          <span>{t('chat.abstainHelp.conceptsHeader', 'Foundational Principles')}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ABSTAIN_OKF_CONCEPTS.map((concept, idx) => (
            <button
              key={concept}
              type="button"
              data-testid={`abstain-chip-${idx}`}
              onClick={() => onAction?.(concept)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-border/80 bg-background/70 hover:bg-ojas/10 hover:border-ojas/40 text-foreground/85 hover:text-foreground transition-all duration-150 shadow-2xs"
            >
              <span>{concept}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Guided Meditation Quick-Launch */}
      <div className="pt-2 border-t border-border/40 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
            <Wind className="h-3.5 w-3.5 text-ojas" aria-hidden="true" />
            <span>{t('chat.abstainHelp.practiceHeading', 'Centering Practice')}</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {t(
              'chat.abstainHelp.practiceDesc',
              'Return to a calm, centered inner state with a 3-minute guided practice.',
            )}
          </p>
        </div>
        <button
          type="button"
          data-testid="abstain-serene-mind-btn"
          onClick={() => openSereneMind('audio', true)}
          className="inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-xl text-xs font-medium bg-ojas text-white hover:bg-ojas/90 transition-colors shadow-sm flex-shrink-0 w-full sm:w-auto"
        >
          <Play className="h-3 w-3 fill-current" aria-hidden="true" />
          <span>{t('chat.abstainHelp.practiceButton', 'Practice 3-Minute Serene Mind Meditation')}</span>
        </button>
      </div>
    </div>
  );
};
