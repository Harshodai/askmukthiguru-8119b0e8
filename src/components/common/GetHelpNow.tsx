import { Phone } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { CrisisLines } from '@/components/common/CrisisLines';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { INDIA_CRISIS_LINES } from '@/lib/crisisHelplines';
import { cn } from '@/lib/utils';

/**
 * Persistent help control (NEW-A11Y-8, A11Y-10, WCAG 3.2.6 Consistent Help).
 * It sits in the header of every page shell so a seeker finds help in the same
 * place everywhere. The numbers come from `@/lib/crisisHelplines` through
 * `CrisisLines`; nothing is typed here. Wording is a draft for owner review.
 */
export const GetHelpNow = ({ className }: { className?: string }) => {
  const { t } = useTranslation();
  const label = t('safety.getHelpNow', 'Get help now');
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          data-testid="get-help-now"
          className={cn(
            'inline-flex min-h-[44px] items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-destructive-ink',
            'ring-1 ring-destructive/40 active:scale-95 transition-all duration-200 ease-out hover:bg-destructive/10',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ojas',
            className,
          )}
        >
          <Phone className="h-3.5 w-3.5" aria-hidden="true" />
          {label}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>{label}</DialogTitle>
        <DialogDescription>
          {t(
            'safety.getHelpNowBody',
            'If you are in danger or thinking of harming yourself, call one of these lines now. Mukthi Guru is not a crisis service.',
          )}
        </DialogDescription>
        <CrisisLines lines={INDIA_CRISIS_LINES} className="text-sm" />
      </DialogContent>
    </Dialog>
  );
};

export default GetHelpNow;
