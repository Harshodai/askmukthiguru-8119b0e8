import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Mail } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { useTranslation } from 'react-i18next';

interface SupportCardProps {
  defaultName: string;
  defaultEmail: string;
}

const supportCategories = ['Feedback', 'Bug Report', 'Feature Request', 'Other'];

/** Contact Support: a single active error line instead of three static ones. */
export const SupportCard = ({ defaultName, defaultEmail }: SupportCardProps) => {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [supportForm, setSupportForm] = useState({ name: defaultName, email: defaultEmail, subject: '', message: '', category: 'Feedback' });
  const [supportLoading, setSupportLoading] = useState(false);
  const [supportSent, setSupportSent] = useState(false);
  const [supportError, setSupportError] = useState<string | null>(null);

  useEffect(() => {
    setSupportForm((prev) => ({
      ...prev,
      name: defaultName || prev.name,
      email: defaultEmail || prev.email,
    }));
  }, [defaultName, defaultEmail]);

  const supportCategoryLabel = (c: string): string =>
    t(`profile.support.category_${c.replace(/\s+/g, '')}`, c);

  const handleSupportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSupportLoading(true);
    setSupportSent(false);
    setSupportError(null);
    try {
      const { submitSupportForm } = await import('@/lib/supportApi');
      await submitSupportForm({
        name: supportForm.name,
        email: supportForm.email as string,
        subject: supportForm.subject,
        message: supportForm.message,
        category: supportForm.category,
      });
      setSupportSent(true);
      setSupportForm({
        name: defaultName,
        email: defaultEmail,
        subject: '',
        message: '',
        category: 'Feedback'
      });
      toast({ title: t('profile.support.messageSent', 'Message sent'), description: t('profile.support.responseTime', 'We will get back to you within 24–48 hours.') });
    } catch (err) {
      const message = err instanceof Error ? err.message : t('profile.support.tryAgain', 'Please try again.');
      setSupportError(message);
      toast({ title: t('profile.support.sendFailed', 'Failed to send'), description: message, variant: 'destructive' });
    } finally {
      setSupportLoading(false);
    }
  };

  return (
    <Card className="rounded-2xl border border-hairline bg-card shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <Mail className="h-5 w-5 text-ojas" aria-hidden="true" />
          <div>
            <CardTitle className="text-lg font-serif font-semibold text-foreground">{t('profile.support.title', 'Contact support')}</CardTitle>
            <CardDescription>
              {t('profile.support.description', 'Have a question, feedback, or run into an issue? We are here to help.')}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {supportSent ? (
          <div className="flex flex-col items-center justify-center py-8 text-center space-y-3">
            <CheckCircle2 className="h-12 w-12 text-prana" aria-hidden="true" />
            <p className="text-lg font-medium font-serif">{t('profile.support.success', 'Message sent')}</p>
            <p className="text-sm text-muted-foreground max-w-sm">
              {t('profile.support.sentDescription', 'We will get back to you within 24–48 hours. For urgent matters, please include "URGENT" in your subject line.')}
            </p>
            <Button variant="outline" className="mt-4 rounded-xl border-hairline" onClick={() => setSupportSent(false)}>
              {t('profile.support.sendAnother', 'Send another message')}
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSupportSubmit} className="space-y-4">
            {supportError && (
              <p role="alert" className="text-sm text-destructive rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3">
                {supportError}
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="s-name">{t('profile.support.name', 'Name')}</Label>
                <Input id="s-name" value={supportForm.name} onChange={e => { setSupportForm(p => ({ ...p, name: e.target.value })); setSupportError(null); }} placeholder={t('profile.support.namePlaceholder', 'Your name')} disabled={!!defaultName} className="min-h-[44px] rounded-xl" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="s-email">{t('profile.support.email', 'Email')} <span className="text-destructive">*</span></Label>
                <Input id="s-email" type="email" value={supportForm.email} onChange={e => { setSupportForm(p => ({ ...p, email: e.target.value })); setSupportError(null); }} placeholder={t('profile.support.emailPlaceholder', 'you@example.com')} required disabled={!!defaultEmail} className="min-h-[44px] rounded-xl" />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="s-category">{t('profile.support.category', 'Category')}</Label>
                <select id="s-category" value={supportForm.category} onChange={e => setSupportForm(p => ({ ...p, category: e.target.value }))} className="flex min-h-[44px] h-11 w-full rounded-xl border border-hairline bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                  {supportCategories.map(c => <option key={c} value={c}>{supportCategoryLabel(c)}</option>)}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="s-subject">{t('profile.support.subject', 'Subject')} <span className="text-destructive">*</span></Label>
                <Input id="s-subject" value={supportForm.subject} onChange={e => { setSupportForm(p => ({ ...p, subject: e.target.value })); setSupportError(null); }} placeholder={t('profile.support.subjectPlaceholder', 'Brief summary')} required className="min-h-[44px] rounded-xl" />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="s-message">{t('profile.support.message', 'Message')} <span className="text-destructive">*</span></Label>
              <Textarea id="s-message" value={supportForm.message} onChange={e => { setSupportForm(p => ({ ...p, message: e.target.value })); setSupportError(null); }} placeholder={t('profile.support.messagePlaceholder', 'Tell us how we can help...')} className="min-h-[140px] resize-none rounded-xl" required />
            </div>

            <div className="flex justify-end pt-2">
              <Button type="submit" disabled={supportLoading} className="w-full sm:w-auto min-h-[44px] rounded-xl bg-ojas hover:bg-ojas-light text-primary-foreground">
                {supportLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" aria-hidden="true" /> : <Mail className="h-4 w-4 mr-1" aria-hidden="true" />}
                {supportLoading ? t('common.loading', 'Loading…') : t('common.submit', 'Submit')}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
};
