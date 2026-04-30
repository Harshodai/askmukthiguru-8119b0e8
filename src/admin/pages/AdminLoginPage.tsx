import { useState, FormEvent, useEffect } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { ShieldCheck, FlaskConical } from "lucide-react";
import { loginAdmin, isAdminAuthenticated } from "@/admin/lib/adminAuth";

export default function AdminLoginPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const redirectTo = params.get("redirect") || "/admin";
  const [email, setEmail] = useState("admin");
  const [password, setPassword] = useState("admin");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isAdminAuthenticated()) nav(redirectTo, { replace: true });
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
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
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
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Sign in</CardTitle>
              <Badge variant="secondary" className="gap-1.5">
                <FlaskConical className="h-3 w-3" />
                DEV MODE
              </Badge>
            </div>
            <CardDescription>
              Use <code className="text-xs">admin / admin</code>. Real Supabase auth wires
              in when backend auth is enabled.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email or username</Label>
                <Input
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? "Signing in…" : "Sign in"}
              </Button>
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
