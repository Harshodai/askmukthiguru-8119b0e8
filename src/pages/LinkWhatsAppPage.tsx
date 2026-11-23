import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, CheckCircle2, Loader2, LogOut, MessageSquare, ShieldCheck, Smartphone } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useWhatsAppConnection } from '@/hooks/useWhatsAppConnection';
import { clearWhatsAppChallenge, readWhatsAppChallenge, rememberWhatsAppChallenge, safeWhatsAppReturnUrl } from '@/lib/whatsappConnection';
import { toast } from 'sonner';

export default function LinkWhatsAppPage() {
  usePageMeta({ title: 'Connect WhatsApp — AskMukthiGuru' });
  const navigate = useNavigate();
  const location = useLocation();
  const connection = useWhatsAppConnection();
  const { session, authLoading, status, loading, busy, error } = connection;
  const [code, setCode] = useState('');
  const [invalidLink, setInvalidLink] = useState(false);
  const [initialSyncConsent, setInitialSyncConsent] = useState(false);
  const [initialMemoryConsent, setInitialMemoryConsent] = useState(false);

  useEffect(() => {
    const fragment = new URLSearchParams(location.hash.replace(/^#/, ''));
    const query = new URLSearchParams(location.search);
    const token = fragment.get('code') || query.get('code');
    if (token !== null) {
      clearWhatsAppChallenge();
      const valid = rememberWhatsAppChallenge(token);
      setCode(valid ? token : '');
      setInvalidLink(!valid);
      // Auth return paths carry no challenge. Retain it only in expiring session storage.
      navigate('/link-whatsapp', { replace: true });
    } else {
      setCode(readWhatsAppChallenge());
    }
  }, [location.hash, location.search, navigate]);

  const handleVerify = async () => {
    const pending = readWhatsAppChallenge();
    if (!pending || pending !== code) { setCode(''); setInvalidLink(true); return; }
    if (await connection.verify(pending, initialSyncConsent, initialMemoryConsent)) {
      setCode('');
      toast.success('WhatsApp number connected successfully!');
    }
  };

  const handleConsent = async (key: 'sync_history_consent' | 'memory_write_consent', value: boolean) => {
    if (await connection.updateConsent(key, value)) toast.success('Privacy preference updated');
  };

  const handleUnlink = async () => {
    if (!window.confirm('Disconnect your WhatsApp number from this account? Your phone app will not be disconnected.')) return;
    if (await connection.unlink()) { setCode(''); toast.info('WhatsApp disconnected'); }
  };

  if (authLoading) return <div className="min-h-[60vh] flex items-center justify-center" role="status" aria-label="Checking sign-in"><Loader2 className="h-7 w-7 animate-spin motion-reduce:animate-none text-primary" /></div>;
  const returnUrl = safeWhatsAppReturnUrl(status?.return_url);

  return (
    <main className="max-w-xl mx-auto px-4 py-8 sm:py-12 space-y-6">
      <header className="space-y-3">
        <MessageSquare className="h-8 w-8 text-primary" aria-hidden="true" />
        <h1 className="text-2xl font-semibold">AskMukthiGuru on WhatsApp</h1>
      </header>

      {!session ? (
        <Card>
          <CardHeader><CardTitle className="text-lg">Sign in to complete linking</CardTitle><CardDescription>Use your AskMukthiGuru account. Never share your password or this private link in WhatsApp.</CardDescription></CardHeader>
          <CardContent><Button className="w-full" onClick={() => navigate('/auth?redirect=%2Flink-whatsapp')}>Sign In or Create Account<ArrowRight className="h-4 w-4 ml-2" /></Button></CardContent>
        </Card>
      ) : (
        <Card aria-busy={loading || busy}>
          <CardHeader>
            <div className="flex items-center gap-2">
              {status?.linked ? <CheckCircle2 className="h-5 w-5 text-primary shrink-0" /> : <Smartphone className="h-5 w-5 text-primary shrink-0" />}
              <CardTitle className="text-lg min-w-0">{status?.linked ? 'WhatsApp Connected' : loading ? 'Checking connection' : 'Confirm Connection'}</CardTitle>
            </div>
            {status?.linked && <CardDescription>Linked to <span className="font-mono text-foreground break-words">{status.masked_phone}</span></CardDescription>}
          </CardHeader>
          <CardContent className="space-y-5">
            {error && <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
              <div className="flex items-start gap-2"><AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-destructive" /><span>{error}</span></div>
              {!status && <Button variant="outline" disabled={loading} onClick={connection.retry}>Retry Connection</Button>}
            </div>}
            {loading ? <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" />Checking your connected number…</div> : status?.linked ? (
              <>
                <Badge variant="outline">Account linked</Badge>
                {returnUrl && <Button asChild className="w-full"><a href={returnUrl} rel="noreferrer"><MessageSquare className="h-4 w-4 mr-2" />Return to WhatsApp</a></Button>}
                <section className="space-y-4 border-t pt-4" aria-label="Privacy controls">
                  <h2 className="text-sm font-semibold flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />Privacy & Consent Controls</h2>
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 space-y-1"><label htmlFor="linked-history" className="text-sm font-medium">Sync Chat History</label><p className="text-xs text-muted-foreground">Show WhatsApp messages in website history.</p></div>
                    <Switch id="linked-history" aria-label="Sync Chat History" checked={status.sync_history_consent} disabled={busy} onCheckedChange={value => handleConsent('sync_history_consent', value)} />
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 space-y-1"><label htmlFor="linked-memory" className="text-sm font-medium">Spiritual Journey Memory</label><p className="text-xs text-muted-foreground">Allow WhatsApp reflections to be saved through your memory consent settings.</p></div>
                    <Switch id="linked-memory" aria-label="Spiritual Journey Memory" checked={status.memory_write_consent} disabled={busy} onCheckedChange={value => handleConsent('memory_write_consent', value)} />
                  </div>
                </section>
                <div className="flex flex-col sm:flex-row gap-3 border-t pt-4">
                  <Button variant="outline" onClick={() => navigate('/chat')}>Return to Chat</Button>
                  <Button variant="ghost" className="text-destructive" disabled={busy} onClick={handleUnlink}><LogOut className="h-4 w-4 mr-2" />Disconnect WhatsApp</Button>
                </div>
              </>
            ) : status && code ? (
              <>
                <p className="text-sm text-muted-foreground">Only continue if you requested this link from your own WhatsApp conversation.</p>
                <section className="space-y-4 border-t pt-4" aria-label="Optional privacy choices">
                  <h2 className="text-sm font-semibold">Optional privacy choices</h2>
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 space-y-1"><label htmlFor="initial-history" className="text-sm font-medium">Sync Chat History</label><p className="text-xs text-muted-foreground">Show WhatsApp messages in website history.</p></div>
                    <Switch id="initial-history" aria-label="Sync Chat History" checked={initialSyncConsent} disabled={busy} onCheckedChange={setInitialSyncConsent} />
                  </div>
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 space-y-1"><label htmlFor="initial-memory" className="text-sm font-medium">Spiritual Journey Memory</label><p className="text-xs text-muted-foreground">Allow saved WhatsApp reflections under your memory consent settings.</p></div>
                    <Switch id="initial-memory" aria-label="Spiritual Journey Memory" checked={initialMemoryConsent} disabled={busy} onCheckedChange={setInitialMemoryConsent} />
                  </div>
                </section>
                <Button className="w-full" disabled={busy} onClick={handleVerify}>{busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin motion-reduce:animate-none" /> : <ShieldCheck className="h-4 w-4 mr-2" />}Confirm & Link WhatsApp</Button>
              </>
            ) : status && (
              <div className="space-y-4">
                <p role={invalidLink ? 'alert' : undefined} className="text-sm text-muted-foreground">{invalidLink ? 'This connection link is invalid or expired. Request a fresh link from your WhatsApp conversation.' : 'No active connection link.'}</p>
                <Button variant="outline" onClick={() => navigate('/profile?tab=settings')}>Return to Profile</Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <footer className="border-t pt-4 text-xs leading-relaxed text-muted-foreground">
        Linking your account is separate from saving history or memory. Disconnecting here does not remove WhatsApp from your phone.
      </footer>
    </main>
  );
}
