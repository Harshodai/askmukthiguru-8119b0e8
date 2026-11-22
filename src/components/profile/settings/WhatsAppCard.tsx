import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, ShieldCheck, CheckCircle2, ArrowRight, Loader2, LogOut, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import type { Session } from '@supabase/supabase-js';
import { BACKEND_URL } from '@/lib/backendUrl';

interface LinkStatus {
  linked: boolean;
  masked_phone: string | null;
  sync_history_consent: boolean;
  memory_write_consent: boolean;
  linked_at: string | null;
}

export const WhatsAppCard = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<LinkStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      if (session) {
        fetchStatus(session.access_token);
      } else {
        setLoading(false);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (session) {
        fetchStatus(session.access_token);
      } else {
        setStatus(null);
        setLoading(false);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchStatus = async (token: string) => {
    setLoading(true);
    setIsUnavailable(false);
    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      } else {
        setIsUnavailable(true);
      }
    } catch (e) {
      console.error('Failed fetching WhatsApp connection status', e);
      setIsUnavailable(true);
    } finally {
      setLoading(false);
    }
  };

  const handleConsentToggle = async (key: 'sync_history_consent' | 'memory_write_consent', val: boolean) => {
    if (!session || !status) return;
    setUpdating(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/consent`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ [key]: val }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Update failed');
      }

      setStatus((prev) => (prev ? { ...prev, [key]: val } : null));
      toast.success(t('profile.whatsapp.preferenceUpdated', 'WhatsApp privacy preference updated'));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update preference';
      toast.error(msg);
    } finally {
      setUpdating(false);
    }
  };

  const handleUnlink = async () => {
    if (!session) return;
    if (!window.confirm(t('profile.whatsapp.confirmDisconnect', 'Disconnect your WhatsApp number from this account?'))) return;

    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/unlink`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });

      if (!res.ok) {
        throw new Error('Failed to unlink');
      }

      toast.info(t('profile.whatsapp.disconnected', 'WhatsApp disconnected'));
      setStatus({
        linked: false,
        masked_phone: null,
        sync_history_consent: false,
        memory_write_consent: false,
        linked_at: null,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error unlinking account';
      toast.error(msg);
    }
  };

  if (!session) {
    return null;
  }

  return (
    <Card className="border-hairline shadow-sm">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-md bg-emerald-500/10 text-emerald-600">
              <MessageSquare className="h-5 w-5" />
            </div>
            <CardTitle className="text-base font-semibold">
              {t('profile.whatsapp.title', 'WhatsApp Companion')}
            </CardTitle>
          </div>
          {status?.linked && (
            <Badge className="bg-emerald-600 text-white text-xs">
              <CheckCircle2 className="h-3 w-3 mr-1" />
              {t('profile.whatsapp.connected', 'Connected')}
            </Badge>
          )}
        </div>
        <CardDescription className="text-xs">
          {t(
            'profile.whatsapp.description',
            'Connect your WhatsApp account to receive morning wisdom, reflection check-ins, and ask questions on the go.',
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading ? (
          <div className="py-4 flex items-center justify-center text-xs text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            {t('common.loading', 'Loading…')}
          </div>
        ) : isUnavailable ? (
          <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs space-y-2">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400 font-medium">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{t('profile.whatsapp.unavailable', 'WhatsApp service temporarily unavailable')}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => session && fetchStatus(session.access_token)}
              disabled={loading}
            >
              {loading ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : null}
              {t('common.retry', 'Retry')}
            </Button>
          </div>
        ) : status?.linked ? (
          <div className="space-y-4">
            <div className="p-3 bg-muted/40 rounded-lg border text-xs flex items-center justify-between">
              <div>
                <span className="text-muted-foreground block">{t('profile.whatsapp.linkedNumber', 'Linked Number')}</span>
                <span className="font-mono font-semibold text-foreground text-sm">{status.masked_phone}</span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/20 h-8"
                onClick={handleUnlink}
              >
                <LogOut className="h-3.5 w-3.5 mr-1" />
                {t('profile.whatsapp.disconnect', 'Disconnect')}
              </Button>
            </div>

            {/* DPDP Consent Options */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                <span>{t('profile.whatsapp.privacyControls', 'Privacy & Data Controls (DPDP)')}</span>
              </div>

              <div className="flex items-center justify-between gap-4 p-3 rounded-lg border bg-background text-xs">
                <div className="space-y-0.5">
                  <div className="font-medium text-foreground">{t('profile.whatsapp.syncHistory', 'Sync Chat History')}</div>
                  <div className="text-muted-foreground">
                    {t('profile.whatsapp.syncHistoryDesc', 'Allow messages exchanged on WhatsApp to be visible in your web history.')}
                  </div>
                </div>
                <Switch
                  checked={status.sync_history_consent}
                  disabled={updating}
                  onCheckedChange={(val) => handleConsentToggle('sync_history_consent', val)}
                />
              </div>

              <div className="flex items-center justify-between gap-4 p-3 rounded-lg border bg-background text-xs">
                <div className="space-y-0.5">
                  <div className="font-medium text-foreground">{t('profile.whatsapp.spiritualMemory', 'Spiritual Journey Memory')}</div>
                  <div className="text-muted-foreground">
                    {t('profile.whatsapp.spiritualMemoryDesc', 'Allow WhatsApp reflections to enrich your spiritual profile and tailored practices.')}
                  </div>
                </div>
                <Switch
                  checked={status.memory_write_consent}
                  disabled={updating}
                  onCheckedChange={(val) => handleConsentToggle('memory_write_consent', val)}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 bg-muted/30 rounded-lg border">
            <div className="text-xs space-y-0.5">
              <span className="font-medium text-foreground block">{t('profile.whatsapp.notLinked', 'Not Connected')}</span>
              <span className="text-muted-foreground">
                {t('profile.whatsapp.connectPrompt', 'Link your phone number to converse with MukthiGuru directly from WhatsApp.')}
              </span>
            </div>
            <Button
              size="sm"
              className="bg-primary text-xs shrink-0"
              onClick={() => navigate('/link-whatsapp')}
            >
              {t('profile.whatsapp.connectNow', 'Connect WhatsApp')}
              <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
