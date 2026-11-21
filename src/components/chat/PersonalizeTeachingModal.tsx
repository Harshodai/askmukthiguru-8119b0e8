import React from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { EkamGoldenOrb } from '@/components/common/EkamGoldenOrb';
import { Brain, LogIn, Sparkles, ShieldCheck } from 'lucide-react';

export type PersonalizeModalMode = 'auth_required' | 'memory_empty';

interface PersonalizeTeachingModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: PersonalizeModalMode;
}

export const PersonalizeTeachingModal: React.FC<PersonalizeTeachingModalProps> = ({
  open,
  onOpenChange,
  mode,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const isAuthMode = mode === 'auth_required';

  const handlePrimaryAction = () => {
    onOpenChange(false);
    if (isAuthMode) {
      navigate('/auth?redirect=/chat');
    } else {
      navigate('/profile?tab=memory');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="personalize-teaching-modal"
        className="sm:max-w-[440px] border-ojas/20 bg-background/95 backdrop-blur-md shadow-xl p-5 sm:p-6"
      >
        <DialogHeader className="gap-2 text-left">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center justify-center w-9 h-9 rounded-full bg-gradient-to-br from-ojas/20 to-ojas/5 border border-ojas/30 shrink-0">
              {isAuthMode ? (
                <EkamGoldenOrb className="w-5 h-5 text-ojas" />
              ) : (
                <Brain className="w-5 h-5 text-ojas" />
              )}
            </div>
            <DialogTitle className="text-base sm:text-lg font-semibold tracking-tight text-foreground">
              {isAuthMode
                ? t('chat.personalizeAuthModalTitle', 'Tune This Wisdom to Your Life')
                : t('chat.personalizeMemoryModalTitle', 'Make This Teaching Yours')}
            </DialogTitle>
          </div>
          <DialogDescription className="text-xs sm:text-sm text-muted-foreground leading-relaxed pt-1">
            {isAuthMode
              ? t(
                  'chat.personalizeAuthModalDesc',
                  "Sign in to connect Sri Bhagavan and Sri Amma's teachings with your personal reflections and life journey."
                )
              : t(
                  'chat.personalizeMemoryModalDesc',
                  "Personalization tailors teachings using reflections and insights you save in your Second Brain. You haven't saved any reflections yet."
                )}
          </DialogDescription>
        </DialogHeader>

        <div className="my-2 rounded-xl border border-ojas/15 bg-ojas/5 p-3.5 flex flex-col gap-2">
          {isAuthMode ? (
            <>
              <div className="flex items-start gap-2 text-xs text-foreground/90">
                <Sparkles className="w-4 h-4 text-ojas shrink-0 mt-0.5" />
                <span>
                  {t(
                    'chat.personalizeAuthBenefit1',
                    'Tailored reflections on what teachings mean for your unique challenges.'
                  )}
                </span>
              </div>
              <div className="flex items-start gap-2 text-xs text-foreground/90">
                <ShieldCheck className="w-4 h-4 text-ojas shrink-0 mt-0.5" />
                <span>
                  {t(
                    'chat.personalizeAuthBenefit2',
                    'Private, encrypted reflections with complete control to pause or delete anytime.'
                  )}
                </span>
              </div>
            </>
          ) : (
            <div className="flex items-start gap-2 text-xs text-foreground/90">
              <Brain className="w-4 h-4 text-ojas shrink-0 mt-0.5" />
              <span>
                {t(
                  'chat.personalizeMemoryBenefit',
                  'Save reflections from your conversations or add personal insights in Second Brain to unlock tailored guidance.'
                )}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-col-reverse sm:flex-row items-center justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="w-full sm:w-auto text-xs text-muted-foreground hover:text-foreground"
          >
            {t('common.maybeLater', 'Maybe later')}
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handlePrimaryAction}
            className="w-full sm:w-auto bg-gradient-to-r from-ojas to-ojas-light text-primary-foreground font-semibold px-4 py-2 text-xs shadow-xs hover:opacity-90 gap-1.5"
          >
            {isAuthMode ? (
              <>
                <LogIn className="w-3.5 h-3.5" />
                <span>{t('chat.personalizeAuthModalCta', 'Sign In or Sign Up')}</span>
              </>
            ) : (
              <>
                <Brain className="w-3.5 h-3.5" />
                <span>{t('chat.personalizeMemoryModalCta', 'Go to Second Brain')}</span>
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
