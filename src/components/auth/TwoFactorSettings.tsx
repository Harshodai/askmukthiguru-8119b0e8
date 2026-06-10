import { useEffect, useState } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Shield, ShieldCheck, Loader2, Trash2 } from 'lucide-react';

interface Factor {
  id: string;
  friendly_name?: string;
  factor_type: string;
  status: string;
}

interface EnrollState {
  factorId: string;
  qr: string;
  secret: string;
  uri: string;
}

export const TwoFactorSettings = () => {
  const { toast } = useToast();
  const [factors, setFactors] = useState<Factor[]>([]);
  const [loading, setLoading] = useState(true);
  const [enrollment, setEnrollment] = useState<EnrollState | null>(null);
  const [code, setCode] = useState('');
  const [verifying, setVerifying] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase.auth.mfa.listFactors();
      if (error) throw error;
      const verified = (data?.totp ?? []).filter((f) => f.status === 'verified');
      setFactors(verified as unknown as Factor[]);
    } catch (e) {
      console.error('[MFA] listFactors failed', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const startEnroll = async () => {
    setEnrollment(null);
    try {
      const { data, error } = await supabase.auth.mfa.enroll({
        factorType: 'totp',
        friendlyName: `Authenticator (${new Date().toLocaleDateString()})`,
      });
      if (error) throw error;
      setEnrollment({
        factorId: data.id,
        qr: data.totp.qr_code,
        secret: data.totp.secret,
        uri: data.totp.uri,
      });
    } catch (e) {
      toast({
        title: 'Could not start 2FA setup',
        description: e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const verifyEnroll = async () => {
    if (!enrollment || code.length < 6) return;
    setVerifying(true);
    try {
      const challenge = await supabase.auth.mfa.challenge({ factorId: enrollment.factorId });
      if (challenge.error) throw challenge.error;
      const verify = await supabase.auth.mfa.verify({
        factorId: enrollment.factorId,
        challengeId: challenge.data.id,
        code: code.trim(),
      });
      if (verify.error) throw verify.error;
      toast({ title: '2FA enabled', description: 'Your account is now protected.' });
      setEnrollment(null);
      setCode('');
      await refresh();
    } catch (e) {
      toast({
        title: 'Code did not match',
        description: e instanceof Error ? e.message : 'Try again',
        variant: 'destructive',
      });
    } finally {
      setVerifying(false);
    }
  };

  const removeFactor = async (factorId: string) => {
    try {
      const { error } = await supabase.auth.mfa.unenroll({ factorId });
      if (error) throw error;
      toast({ title: 'Two-factor removed' });
      await refresh();
    } catch (e) {
      toast({
        title: 'Could not remove factor',
        description: e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {factors.length > 0 ? (
            <ShieldCheck className="w-5 h-5 text-prana" />
          ) : (
            <Shield className="w-5 h-5 text-muted-foreground" />
          )}
          <CardTitle className="text-lg">Two-factor authentication</CardTitle>
        </div>
        <CardDescription>
          Add an extra layer of protection. You'll enter a 6-digit code from your authenticator app at sign-in.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        )}

        {!loading && factors.length > 0 && (
          <div className="space-y-2">
            {factors.map((f) => (
              <div key={f.id} className="flex items-center justify-between p-3 rounded-lg border border-border bg-card/40">
                <div>
                  <p className="text-sm font-medium">{f.friendly_name || 'Authenticator app'}</p>
                  <p className="text-xs text-muted-foreground">TOTP · {f.status}</p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => removeFactor(f.id)} className="text-destructive hover:text-destructive">
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Remove
                </Button>
              </div>
            ))}
          </div>
        )}

        {!loading && !enrollment && (
          <Button onClick={startEnroll} className="bg-ojas hover:bg-ojas-light text-primary-foreground">
            {factors.length > 0 ? 'Add another device' : 'Enable two-factor'}
          </Button>
        )}

        {enrollment && (
          <div className="space-y-3 p-4 rounded-xl border border-ojas/30 bg-ojas/5">
            <p className="text-sm font-medium">Scan this QR with your authenticator app</p>
            <div className="bg-white p-3 rounded-lg inline-block">
              <img src={enrollment.qr} alt="2FA QR code" className="w-40 h-40" />
            </div>
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                Can't scan? Enter the key manually
              </summary>
              <code className="block mt-2 break-all bg-muted px-2 py-1 rounded">{enrollment.secret}</code>
            </details>
            <div className="space-y-2">
              <label className="text-xs text-muted-foreground">Enter the 6-digit code from your app</label>
              <div className="flex gap-2">
                <Input
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  placeholder="123456"
                  inputMode="numeric"
                  className="font-mono tracking-widest text-center max-w-[140px]"
                />
                <Button onClick={verifyEnroll} disabled={code.length < 6 || verifying}>
                  {verifying ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Verify & enable'}
                </Button>
                <Button variant="ghost" onClick={() => { setEnrollment(null); setCode(''); }}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default TwoFactorSettings;
