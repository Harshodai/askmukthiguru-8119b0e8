import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, AlertTriangle, CheckCircle2, Heart, ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/hooks/use-toast';
import { supabase } from '@/integrations/supabase/client';
import { BACKEND_URL } from '@/lib/backendUrl';

export interface CancelFlowResult {
  saved: boolean;
  deletionDate?: string;
  retention?: 'keep_30_days' | 'keep_90_days' | 'delete_immediately';
}

export interface CancelFlowProps {
  onComplete: (result: CancelFlowResult) => void;
  onClose: () => void;
}

type Stage = 'intent' | 'survey' | 'offer' | 'confirm' | 'done';
type Intent = 'exploring_options' | 'definite_cancel';
type Reason =
  | 'journey_complete'
  | 'too_expensive'
  | 'not_using'
  | 'missing_feature'
  | 'found_alternative'
  | 'too_complicated'
  | 'taking_break'
  | 'technical_issues';
type Retention = 'keep_30_days' | 'keep_90_days' | 'delete_immediately';

interface SaveOffer {
  headline: string;
  description: string;
  cta: string;
  value: string;
}

interface CancelIntentResponse {
  next_stage: 'exit_survey' | 'save_offer';
  message: string;
}

interface ExitSurveyResponse {
  reason: string;
  save_offer_type: string;
  save_offer: SaveOffer;
  next_stage: string;
}

interface SaveOfferResponse {
  accepted: boolean;
  next_stage: 'confirmation_saved' | 'confirmation_cancelled';
  message: string;
}

interface CancelStatusResponse {
  status: string;
  deletion_date?: string;
  message: string;
}

const REASONS: Reason[] = [
  'journey_complete',
  'too_expensive',
  'not_using',
  'missing_feature',
  'found_alternative',
  'too_complicated',
  'taking_break',
  'technical_issues',
];

const RETENTIONS: Retention[] = ['keep_30_days', 'keep_90_days', 'delete_immediately'];

/** Authenticated fetch against the FastAPI cancel-flow endpoints. Mirrors the
 *  pattern in PushNotificationsManager / memoryApi: get Supabase session, attach
 *  Bearer token, POST JSON. Throws on non-ok with server message. */
async function cancelApi<TReq, TResp>(path: string, body: TReq): Promise<TResp> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error('Sign in required.');
  if (!BACKEND_URL) throw new Error('Backend unavailable.');
  const res = await fetch(`${BACKEND_URL}/api/account/${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status}).`;
    try {
      const err = await res.json();
      if (err && typeof err.detail === 'string') detail = err.detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<TResp>;
}

export const CancelFlow = ({ onComplete, onClose }: CancelFlowProps) => {
  const { t } = useTranslation();
  const { toast } = useToast();

  const [stage, setStage] = useState<Stage>('intent');
  const [loading, setLoading] = useState(false);
  const [reason, setReason] = useState<Reason | ''>('');
  const [details, setDetails] = useState('');
  const [offerType, setOfferType] = useState('');
  const [offer, setOffer] = useState<SaveOffer | null>(null);
  const [retention, setRetention] = useState<Retention | ''>('');
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [saved, setSaved] = useState(false);
  const [deletionDate, setDeletionDate] = useState<string | undefined>(undefined);

  const guard = (ok: boolean, msg: string): boolean => {
    if (!ok) toast({ title: 'Please complete this step', description: msg, variant: 'destructive' });
    return ok;
  };

  const handleIntent = async (intent: Intent) => {
    setLoading(true);
    try {
      const resp = await cancelApi<CancelIntentRequest, CancelIntentResponse>('cancel-intent', { intent });
      void resp; // next_stage is always exit_survey per backend
      setStage('survey');
    } catch (e) {
      toast({ title: 'Could not start', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleSurveySubmit = async () => {
    if (!guard(reason !== '', 'Choose a reason.')) return;
    setLoading(true);
    try {
      const resp = await cancelApi<ExitSurveyRequest, ExitSurveyResponse>('exit-survey', {
        reason: reason as Reason,
        details,
      });
      setOfferType(resp.save_offer_type);
      setOffer(resp.save_offer);
      setStage('offer');
    } catch (e) {
      toast({ title: 'Survey failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleOffer = async (accepted: boolean) => {
    setLoading(true);
    try {
      const resp = await cancelApi<SaveOfferRequest, SaveOfferResponse>('save-offer', {
        offer_type: offerType,
        accepted,
      });
      if (resp.accepted) {
        setSaved(true);
        setStage('done');
      } else {
        setStage('confirm');
      }
    } catch (e) {
      toast({ title: 'Offer failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!guard(retention !== '', 'Choose a data retention option.')) return;
    if (!guard(confirmChecked, 'Confirm the checkbox to proceed.')) return;
    setLoading(true);
    try {
      const resp = await cancelApi<CancelConfirmationRequest, CancelStatusResponse>('confirm-cancel', {
        confirm: true,
        data_retention: retention as Retention,
      });
      setDeletionDate(resp.deletion_date);
      setSaved(false);
      setStage('done');
    } catch (e) {
      toast({ title: 'Cancel failed', description: e instanceof Error ? e.message : 'unknown', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const finish = () => onComplete({ saved, deletionDate, retention: retention as Retention | undefined });

  return (
    <div className="space-y-5">
      {/* Stage progress dots */}
      <div className="flex items-center justify-center gap-1.5">
        {(['intent', 'survey', 'offer', 'confirm', 'done'] as Stage[]).map((s, i) => {
          const idx = (['intent', 'survey', 'offer', 'confirm', 'done'] as Stage[]).indexOf(stage);
          return (
            <span
              key={s}
              className={cn(
                'h-1.5 rounded-full transition-all',
                i <= idx ? 'bg-ojas w-6' : 'bg-muted w-1.5',
              )}
            />
          );
        })}
      </div>

      {stage === 'intent' && (
        <div className="space-y-4 text-center">
          <div className="mx-auto w-12 h-12 rounded-full bg-ojas/10 flex items-center justify-center text-ojas">
            <Heart className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-serif text-foreground">
              {t('cancelFlow.intent.title', 'Pause or leave your journey')}
            </h3>
            <p className="text-sm text-muted-foreground mt-1.5">
              {t('cancelFlow.intent.subtitle', "Before you go, we'd love to understand how we can better serve you.")}
            </p>
          </div>
          <div className="flex flex-col gap-2 pt-2">
            <Button
              variant="outline"
              disabled={loading}
              onClick={() => handleIntent('exploring_options')}
              className="h-11"
            >
              {t('cancelFlow.intent.explore', 'Explore options to stay')}
            </Button>
            <Button
              variant="destructive"
              disabled={loading}
              onClick={() => handleIntent('definite_cancel')}
              className="h-11"
            >
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('cancelFlow.intent.definite', 'Continue to cancellation')}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose} className="mt-1" disabled={loading}>
              {t('cancelFlow.intent.stay', 'Stay — I want to keep learning')}
            </Button>
          </div>
        </div>
      )}

      {stage === 'survey' && (
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => setStage('intent')}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> {t('cancelFlow.back', 'Back')}
          </button>
          <div>
            <h3 className="text-lg font-serif text-foreground">
              {t('cancelFlow.survey.title', "What's the main reason you're leaving?")}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              {t('cancelFlow.survey.subtitle', 'Your feedback shapes our path forward.')}
            </p>
          </div>
          <RadioGroup
            value={reason}
            onValueChange={(v) => setReason(v as Reason)}
            className="grid gap-2"
          >
            {REASONS.map((r) => (
              <label
                key={r}
                htmlFor={`reason-${r}`}
                className={cn(
                  'flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors',
                  reason === r
                    ? 'border-ojas bg-ojas/5 ring-1 ring-ojas/30'
                    : 'border-border hover:border-border-hover',
                )}
              >
                <RadioGroupItem value={r} id={`reason-${r}`} className="mt-0.5" />
                <div className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">
                    {t(`cancelFlow.survey.reasons.${r}`, r.replace(/_/g, ' '))}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {t(`cancelFlow.survey.hints.${r}`, '')}
                  </p>
                </div>
              </label>
            ))}
          </RadioGroup>
          <div className="space-y-1.5">
            <Label htmlFor="details">
              {t('cancelFlow.survey.details', 'Anything else you want to share?')}{' '}
              <span className="text-muted-foreground">({t('cancelFlow.optional', 'optional')})</span>
            </Label>
            <Textarea
              id="details"
              value={details}
              onChange={(e) => setDetails(e.target.value)}
              placeholder={t('cancelFlow.survey.detailsPlaceholder', 'Share more about your experience...')}
              className="min-h-[80px] resize-none"
              maxLength={500}
            />
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setStage('intent')} disabled={loading}>
              {t('cancelFlow.intent.stay', 'Stay — I want to keep learning')}
            </Button>
            <Button onClick={handleSurveySubmit} disabled={loading || reason === ''} className="ml-auto">
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('cancelFlow.survey.continue', 'Continue')}
            </Button>
          </div>
        </div>
      )}

      {stage === 'offer' && offer && (
        <div className="space-y-4">
          <div className="rounded-xl border border-ojas/20 bg-ojas/5 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-ojas border-ojas/30 bg-ojas/5">
                {offer.value}
              </Badge>
            </div>
            <h3 className="text-lg font-serif text-foreground leading-snug">{offer.headline}</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">{offer.description}</p>
          </div>
          <div className="flex flex-col gap-2">
            <Button
              onClick={() => handleOffer(true)}
              disabled={loading}
              className="h-11 bg-ojas hover:bg-ojas-light text-primary-foreground gap-2"
            >
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {offer.cta}
            </Button>
            <Button
              variant="ghost"
              onClick={() => handleOffer(false)}
              disabled={loading}
              className="h-10 text-muted-foreground"
            >
              {t('cancelFlow.offer.decline', 'No thanks, continue cancellation')}
            </Button>
          </div>
        </div>
      )}

      {stage === 'confirm' && (
        <div className="space-y-4">
          <div className="flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
            <AlertTriangle className="w-5 h-5 text-destructive shrink-0 mt-0.5" />
            <div>
              <h3 className="text-base font-medium text-destructive">
                {t('cancelFlow.confirm.title', 'Permanently delete your account?')}
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                {t('cancelFlow.confirm.warning', 'This deletes your account and all server-side data: profile, chats, meditation sessions. You will be signed out immediately.')}
              </p>
            </div>
          </div>

          <div className="space-y-2">
            <Label>{t('cancelFlow.confirm.retention', 'Data retention')}</Label>
            <RadioGroup
              value={retention}
              onValueChange={(v) => setRetention(v as Retention)}
              className="grid gap-2"
            >
              {RETENTIONS.map((r) => (
                <label
                  key={r}
                  htmlFor={`ret-${r}`}
                  className={cn(
                    'flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors',
                    retention === r
                      ? 'border-ojas bg-ojas/5 ring-1 ring-ojas/30'
                      : 'border-border hover:border-border-hover',
                  )}
                >
                  <RadioGroupItem value={r} id={`ret-${r}`} />
                  <div className="text-sm">
                    <p className="font-medium text-foreground">
                      {t(`cancelFlow.confirm.retentionLabels.${r}`, r.replace(/_/g, ' '))}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t(`cancelFlow.confirm.retentionHints.${r}`, '')}
                    </p>
                  </div>
                </label>
              ))}
            </RadioGroup>
          </div>

          <label htmlFor="confirm-box" className="flex items-start gap-2 cursor-pointer">
            <Checkbox
              id="confirm-box"
              checked={confirmChecked}
              onCheckedChange={(v) => setConfirmChecked(v === true)}
              className="mt-0.5"
            />
            <span className="text-xs text-muted-foreground">
              {t('cancelFlow.confirm.acknowledge', 'I understand this action is irreversible and my account will be permanently deleted.')}
            </span>
          </label>

          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => setStage('offer')} disabled={loading}>
              {t('cancelFlow.back', 'Back')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirm}
              disabled={loading || retention === '' || !confirmChecked}
              className="ml-auto"
            >
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {t('cancelFlow.confirm.permanent', 'Permanently Delete')}
            </Button>
          </div>
        </div>
      )}

      {stage === 'done' && (
        <div className="space-y-4 text-center">
          <div
            className={cn(
              'mx-auto w-12 h-12 rounded-full flex items-center justify-center',
              saved ? 'bg-prana/10 text-prana' : 'bg-ojas/10 text-ojas',
            )}
          >
            {saved ? <CheckCircle2 className="w-6 h-6" /> : <CheckCircle2 className="w-6 h-6" />}
          </div>
          <div>
            <h3 className="text-lg font-serif text-foreground">
              {saved
                ? t('cancelFlow.done.savedTitle', "We're so glad you're staying.")
                : t('cancelFlow.done.cancelledTitle', 'Your account is scheduled for deletion')}
            </h3>
            <p className="text-sm text-muted-foreground mt-1.5">
              {saved
                ? t('cancelFlow.done.savedBody', 'Your offer has been applied. Continue your journey whenever you are ready.')
                : deletionDate
                  ? t(
                      'cancelFlow.done.cancelledBody',
                      'Your account will be deleted on {{deletionDate}}. You can reactivate anytime before then.',
                      { deletionDate: new Date(deletionDate).toLocaleDateString() },
                    )
                  : t(
                      'cancelFlow.done.cancelledBodyNoDate',
                      'Your account is scheduled for deletion. You can reactivate anytime before then.',
                    )}
            </p>
            {!saved && (
              <p className="text-xs text-muted-foreground mt-2">
                {t('cancelFlow.done.reactivate', 'A reactivation link has been sent to your email.')}
              </p>
            )}
          </div>
          <Button onClick={finish} className="h-11">
            {t('cancelFlow.done.close', 'Close')}
          </Button>
        </div>
      )}
    </div>
  );
};

interface CancelIntentRequest { intent: Intent }
interface ExitSurveyRequest { reason: Reason; details: string }
interface SaveOfferRequest { offer_type: string; accepted: boolean }
interface CancelConfirmationRequest { confirm: boolean; data_retention: Retention }