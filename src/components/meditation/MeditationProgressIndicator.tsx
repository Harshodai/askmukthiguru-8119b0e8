import { useTranslation } from 'react-i18next';
import { ProgressRing } from '@/components/common/ui/ProgressRing';

interface MeditationProgressIndicatorProps {
  currentStep: number;
  totalSteps: number;
  /** 0–1 progress within the current step */
  stepProgress: number;
}

/**
 * Two-palm "hand-in-hand" progress ring.
 * Renders as a circular progress ring with step dots.
 */
export const MeditationProgressIndicator = ({
  currentStep,
  totalSteps,
  stepProgress,
}: MeditationProgressIndicatorProps) => {
  const { t } = useTranslation();
  return (
  <ProgressRing
    currentStep={currentStep}
    totalSteps={totalSteps}
    stepProgress={stepProgress}
    centerContent={
      <div className="text-center">
        <p className="text-3xl font-semibold text-ojas">{currentStep + 1}</p>
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{t('meditation.stepXofY', { current: currentStep + 1, total: totalSteps })}</p>
      </div>
    }
  />
);
};
