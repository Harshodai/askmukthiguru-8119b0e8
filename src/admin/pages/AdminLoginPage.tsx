import { useState, FormEvent, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ShieldCheck, AlertCircle } from "lucide-react";
import { loginAdmin, verifyAdminSession } from "@/admin/lib/adminAuth";
import { useTranslation } from 'react-i18next';
import { usePageMeta } from '@/hooks/usePageMeta';

export default function AdminLoginPage() {
  usePageMeta({ title: 'Admin sign in — AskMukthiGuru', noindex: true });
  const nav = useNavigate();
  const [params] = useSearchParams();
  const redirectTo = params.get("redirect") || "/admin";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    verifyAdminSession().then(({ authenticated }) => {
      if (authenticated) nav(redirectTo, { replace: true });
    });
  }, [nav, redirectTo]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const res = await loginAdmin(email, password);
    setLoading(false);
    if (res.ok === true) {
      nav(redirectTo, { replace: true });
      return;
    }
    setError(res.error);
  }

  return (
    <div className="min-h-dvh bg-background text-foreground flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-primary/15 text-primary mb-3">
            <ShieldCheck className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-semibold">Admin Console</h1>
          <p className="text-muted-foreground text-sm mt-1">
            AskMukthiGuru observability dashboard
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Sign in</CardTitle>
            <CardDescription>
              Enter your admin credentials to access the dashboard.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="admin-email">Email</Label>
                <Input
                  id="admin-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@example.com"
                  autoFocus
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin-password">Password</Label>
                <Input
                  id="admin-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </div>
              {error && (
                <Alert variant="destructive" className="border-destructive/40 bg-destructive/5">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </Button>
              <div className="mt-3 text-center">
                <Link to="/auth" className="text-xs text-muted-foreground hover:text-foreground hover:underline">
                  Forgot password?
                </Link>
              </div>
            </form>
            <div className="mt-4 text-center text-sm text-muted-foreground">
              <Link to="/" className="hover:text-foreground">
                ← Back to app
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
