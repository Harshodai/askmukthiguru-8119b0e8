import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, CheckCircle2, Loader2, LogOut, MessageSquare, ShieldCheck } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { useWhatsAppConnection } from '@/hooks/useWhatsAppConnection';
import { toast } from 'sonner';

export const WhatsAppCard = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const connection = useWhatsAppConnection();
  const { session, status, loading, busy, error } = connection;
  if (!session) return null;

  const handleConsent = async (key: 'sync_history_consent' | 'memory_write_consent', value: boolean) => {
    if (await connection.updateConsent(key, value)) toast.success(t('profile.whatsapp.preferenceUpdated', 'WhatsApp privacy preference updated'));
  };
  const handleUnlink = async () => {
    if (!window.confirm(t('profile.whatsapp.confirmDisconnect', 'Disconnect your WhatsApp number from this account?'))) return;
    if (await connection.unlink()) toast.info(t('profile.whatsapp.disconnected', 'WhatsApp disconnected'));
  };

  return (
    <Card className="border-hairline shadow-sm" aria-busy={loading || busy}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base font-semibold flex items-center gap-2"><MessageSquare className="h-5 w-5 text-primary shrink-0" />{t('profile.whatsapp.title', 'WhatsApp Companion')}</CardTitle>
          {!loading && status?.linked && <Badge variant="outline"><CheckCircle2 className="h-3 w-3 mr-1" />{t('profile.whatsapp.connected', 'Connected')}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <div role="alert" className="space-y-3 text-sm">
          <div className="flex items-start gap-2"><AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-destructive" /><span>{t('profile.whatsapp.unavailable', 'WhatsApp connection could not be confirmed.')}</span></div>
          {!status && <Button variant="outline" disabled={loading} onClick={connection.retry}>{t('common.retry', 'Retry')}</Button>}
        </div>}
        {loading ? <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />{t('common.loading', 'Loading…')}</div> : status?.linked ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
              <div className="min-w-0"><span className="text-xs text-muted-foreground block">{t('profile.whatsapp.linkedNumber', 'Linked Number')}</span><span className="font-mono text-sm break-words">{status.masked_phone}</span></div>
              <Button variant="ghost" size="sm" className="text-destructive" disabled={busy} onClick={handleUnlink}><LogOut className="h-4 w-4 mr-1" />{t('profile.whatsapp.disconnect', 'Disconnect')}</Button>
            </div>
            <h3 className="flex items-center gap-2 text-sm font-medium"><ShieldCheck className="h-4 w-4 text-primary" />{t('profile.whatsapp.privacyControls', 'Privacy & Data Controls')}</h3>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1"><label htmlFor="profile-wa-history" className="text-sm font-medium">{t('profile.whatsapp.syncHistory', 'Sync Chat History')}</label><p className="text-xs text-muted-foreground">{t('profile.whatsapp.syncHistoryDesc', 'Allow messages exchanged on WhatsApp to be visible in your web history.')}</p></div>
              <Switch id="profile-wa-history" aria-label={t('profile.whatsapp.syncHistory', 'Sync Chat History')} checked={status.sync_history_consent} disabled={busy} onCheckedChange={value => handleConsent('sync_history_consent', value)} />
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 space-y-1"><label htmlFor="profile-wa-memory" className="text-sm font-medium">{t('profile.whatsapp.spiritualMemory', 'Spiritual Journey Memory')}</label><p className="text-xs text-muted-foreground">{t('profile.whatsapp.spiritualMemoryDesc', 'Allow WhatsApp reflections to enrich your spiritual profile and tailored practices.')}</p></div>
              <Switch id="profile-wa-memory" aria-label={t('profile.whatsapp.spiritualMemory', 'Spiritual Journey Memory')} checked={status.memory_write_consent} disabled={busy} onCheckedChange={value => handleConsent('memory_write_consent', value)} />
            </div>
          </>
        ) : status && (
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{t('profile.whatsapp.notLinked', 'Not Connected')}</span>
            <Button size="sm" onClick={() => navigate('/link-whatsapp')}>{t('profile.whatsapp.connectNow', 'Connect WhatsApp')}<ArrowRight className="h-4 w-4 ml-2" /></Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
