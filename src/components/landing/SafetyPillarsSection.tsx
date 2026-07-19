import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { Shield, HeartHandshake, PhoneCall, AlertCircle, X } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export const SafetyPillarsSection = () => {
  const { t } = useTranslation();
  const [crisisOpen, setCrisisOpen] = useState(false);

  return (
    <section className="bg-card dark:bg-[#1a1412] border-t border-border py-12 md:py-16 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 bg-gradient-to-r from-saffron-gold/0 via-saffron-gold/[0.02] to-saffron-gold/0 pointer-events-none" />

      <div className="relative z-10 container mx-auto px-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {/* Pillar 1: Privacy */}
          <div className="flex flex-col items-center text-center p-4">
            <div className="w-12 h-12 rounded-full bg-saffron-gold/10 flex items-center justify-center mb-4 text-saffron-gold shadow-sm">
              <Shield className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-deep-earth dark:text-foreground/90 mb-2">
              {t('landing.safety.privacyTitle', 'Privacy First')}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-xs leading-relaxed">
              {t('landing.safety.privacyDesc', 'Gated conversation history and zero model training. Your spiritual journey is private.')}
            </p>
            <Link
              to="/privacy"
              className="text-xs font-semibold text-saffron-gold hover:underline"
            >
              {t('landing.safety.viewPrivacy', 'Read Privacy Policy')}
            </Link>
          </div>

          {/* Pillar 2: Boundaries */}
          <div className="flex flex-col items-center text-center p-4 border-y md:border-y-0 md:border-x border-border/40">
            <div className="w-12 h-12 rounded-full bg-saffron-gold/10 flex items-center justify-center mb-4 text-saffron-gold shadow-sm">
              <HeartHandshake className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-deep-earth dark:text-foreground/90 mb-2">
              {t('landing.safety.boundariesTitle', 'Compassionate Boundaries')}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-xs leading-relaxed">
              {t('landing.safety.boundariesDesc', 'Mukthi Guru is an AI spiritual guide, not a medical professional, therapist, or counselor.')}
            </p>
            <Link
              to="/terms"
              className="text-xs font-semibold text-saffron-gold hover:underline"
            >
              {t('landing.safety.viewTerms', 'Read Terms of Service')}
            </Link>
          </div>

          {/* Pillar 3: Crisis Support */}
          <div className="flex flex-col items-center text-center p-4">
            <div className="w-12 h-12 rounded-full bg-saffron-gold/10 flex items-center justify-center mb-4 text-saffron-gold shadow-sm">
              <PhoneCall className="w-6 h-6" />
            </div>
            <h3 className="text-lg font-semibold text-deep-earth dark:text-foreground/90 mb-2">
              {t('landing.safety.crisisTitle', 'Crisis Support')}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-xs leading-relaxed">
              {t('landing.safety.crisisDesc', 'If you are experiencing acute distress or a crisis, please reach out to qualified professional help.')}
            </p>
            <button
              onClick={() => setCrisisOpen(true)}
              className="text-xs font-semibold text-saffron-gold hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-saffron-gold focus-visible:ring-offset-2 rounded"
            >
              {t('landing.safety.viewHelplines', 'Find Helplines & Resources')}
            </button>
          </div>
        </div>
      </div>

      {/* Crisis Dialog */}
      <Dialog open={crisisOpen} onOpenChange={setCrisisOpen}>
        <DialogContent className="sm:max-w-md border border-border/80 bg-card p-6 md:p-8 rounded-2xl shadow-xl">
          <DialogHeader className="gap-2">
            <div className="mx-auto w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-2">
              <AlertCircle className="w-6 h-6 text-destructive" />
            </div>
            <DialogTitle className="text-center font-sacred text-2xl font-light">
              {t('common.importantNotice')}
            </DialogTitle>
            <DialogDescription className="text-center text-sm text-muted-foreground mt-2">
              {t('common.disclaimerWarning')}
            </DialogDescription>
          </DialogHeader>

          <div className="mt-6 p-4 rounded-xl bg-muted/30 border border-border/40 text-center">
            <h4 className="text-xs uppercase tracking-widest font-bold text-deep-earth dark:text-foreground/80 mb-3">
              {t('crisisDialog.heading', 'Crisis Support Resources')}
            </h4>
            
            <div className="space-y-4">
              <div>
                <p className="text-xs text-muted-foreground">{t('crisisDialog.indiaHelplines', 'India Helplines')}</p>
                <p className="text-sm font-semibold text-foreground mt-1">
                  iCall: <a href="tel:9152987821" className="text-saffron-gold hover:underline">9152987821</a>
                  <span className="text-xs font-normal text-muted-foreground block mt-0.5">
                    {t('crisisDialog.icallAvailability', 'Monday–Saturday, 10:00–20:00 IST')}
                  </span>
                </p>
                <p className="text-sm font-semibold text-foreground mt-2">
                  Vandrevala Foundation: <a href="tel:+919999666555" className="text-saffron-gold hover:underline">+91 9999 666 555</a>
                </p>
              </div>

              <div className="border-t border-border/40 pt-3">
                <p className="text-xs text-muted-foreground">{t('crisisDialog.unitedStates', 'United States')}</p>
                <p className="text-sm font-semibold text-foreground mt-1">
                  {t('crisisDialog.usLifeline', 'Suicide & Crisis Lifeline')}: <a href="tel:988" className="text-saffron-gold hover:underline">988</a>
                </p>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <Button
              onClick={() => setCrisisOpen(false)}
              className="w-full bg-gradient-to-r from-saffron-gold to-pale-gold hover:scale-[1.01] transition-all text-primary-foreground font-semibold rounded-full"
            >
              {t('common.dismiss', 'Close')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
};
