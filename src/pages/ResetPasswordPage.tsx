import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { AuthApiError } from '@supabase/supabase-js';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useToast } from '@/hooks/use-toast';
import { Sparkles, Lock, AlertCircle } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { useTranslation } from 'react-i18next';

const ResetPasswordPage = () => {
  usePageMeta({
    title: 'Reset your password — AskMukthiGuru',
    description: 'Set a new password for your AskMukthiGuru account.',
    canonical: 'https://askmukthiguru.lovable.app/reset-password',
  });
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  // The recovery flow lands here with a hash like #access_token=...&type=recovery.
  // Supabase auto-exchanges it; we just wait for a session to appear.
  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY' || (session?.user && window.location.hash.includes('type=recovery'))) {
        setReady(true);
      }
    });
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) setReady(true);
    });
    return () => subscription.unsubscribe();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 12) return setError('Password must be at least 12 characters.');
    if (password !== confirm) return setError('Passwords do not match.');

    setLoading(true);
    try {
      const { error: updateError } = await supabase.auth.updateUser({ password });
      if (updateError) throw updateError;
    } catch (error: unknown) {
      setLoading(false);
      const msg = error instanceof AuthApiError
        ? (error.message.includes('expired')
          ? 'Password reset link has expired. Please request a new one.'
          : error.message)
        : 'Failed to reset password. Please try again.';
      setError(msg);
      toast({
        title: 'Password Reset Failed',
        description: msg,
        variant: 'destructive',
      });
      return;
    }
    setLoading(false);
    toast({ title: 'Password updated', description: 'You can now sign in with your new password.' });
    navigate('/auth', { replace: true });
  };

  return (
    <div className="min-h-dvh flex items-center justify-center bg-gradient-to-br from-background via-ojas/5 to-background px-4">
      <div className="w-full max-w-[400px] mx-4 sm:mx-auto space-y-6 shadow-xl shadow-foreground/5 border border-border/40 rounded-xl p-6 sm:p-8">
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-full bg-ojas/15 border border-ojas/25 flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6 text-ojas" />
          </div>
          <h1 className="text-xl font-semibold text-foreground">Set a new password</h1>
          <p className="text-sm text-muted-foreground">Choose something memorable, dear seeker.</p>
        </div>

        {!ready && (
          <Alert className="border-border/50">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">
              Verifying your reset link… If nothing happens, request a new link from the sign-in page.
            </AlertDescription>
          </Alert>
        )}

        {error && (
          <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-sm">{error}</AlertDescription>
          </Alert>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="pw" className="text-xs text-muted-foreground">New password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="pl-9 h-10" required minLength={6} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="pw2" className="text-xs text-muted-foreground">Confirm password</Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input id="pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} className="pl-9 h-10" required minLength={6} />
            </div>
          </div>
          <Button type="submit" className="w-full h-10 bg-ojas hover:bg-ojas-light text-primary-foreground" disabled={loading || !ready}>
            {loading ? 'Updating…' : 'Update password'}
          </Button>
        </form>
      </div>
    </div>
  );
};

export default ResetPasswordPage;
