import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { AppShell } from '@/components/layout/AppShell';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, XCircle, AlertCircle, Loader2, RefreshCw, Copy } from 'lucide-react';
import { usePageMeta } from '@/hooks/usePageMeta';
import { toast } from 'sonner';

type Status = 'pending' | 'ok' | 'fail' | 'warn';

interface Check {
  id: string;
  label: string;
  status: Status;
  detail?: string;
  raw?: unknown;
}

const ICON: Record<Status, React.ReactNode> = {
  pending: <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />,
  ok: <CheckCircle2 className="w-4 h-4 text-emerald-500" />,
  warn: <AlertCircle className="w-4 h-4 text-amber-500" />,
  fail: <XCircle className="w-4 h-4 text-destructive" />,
};

const AuthDiagnosticsPage = () => {
  usePageMeta({
    title: 'Auth Diagnostics — AskMukthiGuru',
    description: 'Self-test for session, profile, roles, admin status, and backend reachability.',
    canonical: 'https://askmukthiguru.lovable.app/auth/diagnostics',
  });

  const [checks, setChecks] = useState<Check[]>([]);
  const [running, setRunning] = useState(false);

  const update = useCallback((c: Check) => {
    setChecks((prev) => {
      const i = prev.findIndex((p) => p.id === c.id);
      if (i === -1) return [...prev, c];
      const copy = [...prev];
      copy[i] = c;
      return copy;
    });
  }, []);

  const runAll = useCallback(async () => {
    setRunning(true);
    setChecks([]);

    // 1. Session
    update({ id: 'session', label: 'Supabase session', status: 'pending' });
    const { data: sessionData, error: sessionErr } = await supabase.auth.getSession();
    const session = sessionData?.session;
    if (sessionErr || !session) {
      update({
        id: 'session',
        label: 'Supabase session',
        status: 'fail',
        detail: sessionErr?.message ?? 'No active session — sign in first.',
      });
      setRunning(false);
      return;
    }
    update({
      id: 'session',
      label: 'Supabase session',
      status: 'ok',
      detail: `${session.user.email} · expires ${new Date((session.expires_at ?? 0) * 1000).toLocaleString()}`,
      raw: { user_id: session.user.id, email: session.user.email },
    });

    // 2. whoami_diagnostics RPC
    update({ id: 'whoami', label: 'Profile + role lookup (RPC)', status: 'pending' });
    const { data: who, error: whoErr } = await supabase.rpc('whoami_diagnostics');
    if (whoErr) {
      update({
        id: 'whoami',
        label: 'Profile + role lookup (RPC)',
        status: 'fail',
        detail: whoErr.message,
        raw: whoErr,
      });
    } else {
      const w = who as {
        authenticated: boolean;
        profile_present: boolean;
        roles: string[];
        is_admin: boolean;
        display_name?: string;
      };
      update({
        id: 'whoami',
        label: 'Profile + role lookup (RPC)',
        status: 'ok',
        detail: `display_name=${w.display_name ?? '(unset)'}, roles=[${w.roles.join(', ') || 'none'}]`,
        raw: w,
      });

      // 3. Profile
      update({
        id: 'profile',
        label: 'Profile row exists',
        status: w.profile_present ? 'ok' : 'fail',
        detail: w.profile_present
          ? 'Row found in profiles table.'
          : 'No profile row. The signup trigger may have failed — re-sign-up or run the migration.',
      });

      // 4. Roles
      update({
        id: 'roles',
        label: 'user_roles entry',
        status: w.roles.length > 0 ? 'ok' : 'fail',
        detail:
          w.roles.length > 0
            ? `Roles assigned: ${w.roles.join(', ')}`
            : 'No roles assigned. Ask an existing admin to grant the admin role, or insert a row into user_roles.',
      });

      // 5. Admin
      update({
        id: 'admin',
        label: 'Admin role check (has_role)',
        status: w.is_admin ? 'ok' : 'warn',
        detail: w.is_admin
          ? 'You ARE an admin — /admin will load.'
          : 'You are NOT an admin. Insert (user_id, \'admin\') into public.user_roles to grant access.',
      });
    }

    // 6. has_role direct call (cross-check)
    update({ id: 'has_role', label: 'has_role(admin) direct RPC', status: 'pending' });
    const { data: roleOk, error: roleErr } = await supabase.rpc('has_role', {
      _user_id: session.user.id,
      _role: 'admin',
    });
    update({
      id: 'has_role',
      label: 'has_role(admin) direct RPC',
      status: roleErr ? 'fail' : roleOk ? 'ok' : 'warn',
      detail: roleErr ? roleErr.message : roleOk ? 'true' : 'false',
    });

    // 7. Backend env
    const backendUrl = import.meta.env.VITE_BACKEND_URL || '(empty — using relative /api/chat)';
    update({
      id: 'backend_env',
      label: 'VITE_BACKEND_URL',
      status: 'ok',
      detail: backendUrl,
    });

    // 8. Backend health
    update({ id: 'backend_health', label: 'Backend /api/health', status: 'pending' });
    try {
      const base = import.meta.env.VITE_BACKEND_URL || '';
      const url = base ? `${base.replace(/\/$/, '')}/api/health` : '/api/health';
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 4000);
      const res = await fetch(url, { signal: ctrl.signal });
      clearTimeout(t);
      const ct = res.headers.get('content-type') || '';
      update({
        id: 'backend_health',
        label: 'Backend /api/health',
        status: res.ok && ct.includes('json') ? 'ok' : 'warn',
        detail: `${res.status} ${res.statusText} · ${ct}`,
      });
    } catch (e) {
      update({
        id: 'backend_health',
        label: 'Backend /api/health',
        status: 'warn',
        detail:
          e instanceof Error
            ? e.message
            : 'Backend unreachable (chat will work in placeholder mode).',
      });
    }

    setRunning(false);
  }, [update]);

  useEffect(() => {
    runAll();
  }, [runAll]);

  const copyReport = () => {
    const report = checks
      .map((c) => `[${c.status.toUpperCase()}] ${c.label}: ${c.detail ?? ''}`)
      .join('\n');
    navigator.clipboard.writeText(report);
    toast.success('Diagnostic report copied');
  };

  return (
    <AppShell title="Auth Diagnostics">
      <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-lg">Self-test</CardTitle>
                <CardDescription>
                  Verifies session, profile, roles, admin status, and backend reachability.
                </CardDescription>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={copyReport} disabled={running}>
                  <Copy className="w-3.5 h-3.5 mr-1.5" /> Copy
                </Button>
                <Button size="sm" onClick={runAll} disabled={running}>
                  <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${running ? 'animate-spin' : ''}`} />
                  Re-run
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {checks.length === 0 && (
              <p className="text-sm text-muted-foreground">Running checks…</p>
            )}
            {checks.map((c) => (
              <div
                key={c.id}
                className="flex items-start gap-3 p-3 rounded-lg border border-border/50 bg-card/40"
              >
                <div className="mt-0.5">{ICON[c.status]}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{c.label}</p>
                    <Badge
                      variant="outline"
                      className={
                        c.status === 'ok'
                          ? 'border-emerald-500/40 text-emerald-600'
                          : c.status === 'fail'
                            ? 'border-destructive/40 text-destructive'
                            : c.status === 'warn'
                              ? 'border-amber-500/40 text-amber-600'
                              : ''
                      }
                    >
                      {c.status}
                    </Badge>
                  </div>
                  {c.detail && (
                    <p className="text-xs text-muted-foreground mt-1 break-all font-mono">
                      {c.detail}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Common fixes</CardTitle>
          </CardHeader>
          <CardContent className="text-sm space-y-2 text-muted-foreground">
            <p>
              <strong className="text-foreground">No profile row?</strong> Re-sign-up so the
              <code className="mx-1 px-1 py-0.5 rounded bg-muted text-xs">handle_new_user</code>
              trigger fires, or have an admin insert a row into{' '}
              <code className="mx-1 px-1 py-0.5 rounded bg-muted text-xs">profiles</code>.
            </p>
            <p>
              <strong className="text-foreground">Not an admin?</strong> An existing admin must
              run:{' '}
              <code className="block mt-1 p-2 rounded bg-muted text-xs whitespace-pre-wrap">
                INSERT INTO public.user_roles (user_id, role) VALUES ('&lt;your-uuid&gt;', 'admin');
              </code>
            </p>
            <p>
              <strong className="text-foreground">Backend unreachable?</strong> Set{' '}
              <code className="px-1 py-0.5 rounded bg-muted text-xs">VITE_BACKEND_URL</code> in
              your local <code>.env</code> and start the FastAPI service. Without it the chat
              falls back to placeholder responses.
            </p>
            <p className="pt-2">
              <Link to="/auth" className="text-ojas hover:underline">
                Back to sign-in →
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
};

export default AuthDiagnosticsPage;
