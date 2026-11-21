import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { supabase } from "@/integrations/supabase/client";
import type { Session } from "@supabase/supabase-js";
import { BACKEND_URL } from "@/lib/backendUrl";
import { MessageSquare, ShieldCheck, CheckCircle2, AlertCircle, Loader2, ArrowRight, Smartphone, LogOut } from "lucide-react";
import { toast } from "sonner";
import { usePageMeta } from "@/hooks/usePageMeta";

interface LinkStatus {
  linked: boolean;
  masked_phone: string | null;
  sync_history_consent: boolean;
  memory_write_consent: boolean;
  linked_at: string | null;
}

export default function LinkWhatsAppPage() {
  usePageMeta({ title: "Connect WhatsApp — AskMukthiGuru" });
  const navigate = useNavigate();
  const location = useLocation();

  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  // Link token from URL
  const [code, setCode] = useState<string>("");
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Current connection state
  const [status, setStatus] = useState<LinkStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [updatingConsent, setUpdatingConsent] = useState(false);

  // Extract challenge token from hash #code=... or query ?code=...
  useEffect(() => {
    let token = "";
    if (location.hash) {
      const match = location.hash.match(/code=([^&]+)/);
      if (match) token = decodeURIComponent(match[1]);
    }
    if (!token && location.search) {
      const params = new URLSearchParams(location.search);
      token = params.get("code") || "";
    }
    if (token) {
      setCode(token);
    }
  }, [location]);

  // Auth session tracking
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
      setAuthLoading(false);
      if (session) {
        fetchStatus(session.access_token);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setAuthLoading(false);
      if (session) {
        fetchStatus(session.access_token);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const fetchStatus = async (token: string) => {
    setStatusLoading(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (e) {
      console.error("Failed fetching WhatsApp status", e);
    } finally {
      setStatusLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!code.trim() || !session) return;
    setLinking(true);
    setLinkError(null);

    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/verify`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ code }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Verification failed");
      }

      toast.success("WhatsApp number connected successfully!");
      setStatus({
        linked: true,
        masked_phone: data.masked_phone,
        sync_history_consent: data.sync_history_consent ?? false,
        memory_write_consent: data.memory_write_consent ?? false,
        linked_at: data.linked_at,
      });
      setCode("");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to link WhatsApp account";
      setLinkError(msg);
      toast.error(msg);
    } finally {
      setLinking(false);
    }
  };

  const handleConsentToggle = async (key: "sync_history_consent" | "memory_write_consent", val: boolean) => {
    if (!session || !status) return;
    setUpdatingConsent(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/consent`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ [key]: val }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Update failed");
      }

      setStatus((prev) => prev ? { ...prev, [key]: val } : null);
      toast.success("Privacy preference updated");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update preference";
      toast.error(msg);
    } finally {
      setUpdatingConsent(false);
    }
  };

  const handleUnlink = async () => {
    if (!session) return;
    if (!window.confirm("Disconnect your WhatsApp number from this account?")) return;

    try {
      const res = await fetch(`${BACKEND_URL}/api/whatsapp/link/unlink`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
        },
      });

      if (!res.ok) {
        throw new Error("Failed to unlink");
      }

      toast.info("WhatsApp disconnected");
      setStatus({
        linked: false,
        masked_phone: null,
        sync_history_consent: false,
        memory_write_consent: false,
        linked_at: null,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Error unlinking account";
      toast.error(msg);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-[70vh] flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto px-4 py-12 space-y-6">
      {/* Top Banner */}
      <div className="text-center space-y-2">
        <div className="inline-flex p-3 rounded-full bg-emerald-500/10 text-emerald-600 mb-2">
          <MessageSquare className="h-8 w-8" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight">WhatsApp Companion Connection</h1>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">
          Connect your WhatsApp to receive teachings, practice check-ins, and continue your spiritual journey seamlessly.
        </p>
      </div>

      {/* Case 1: Unauthenticated */}
      {!session ? (
        <Card className="border-border/60 shadow-sm">
          <CardHeader className="text-center pb-4">
            <CardTitle className="text-lg">Sign in to complete linking</CardTitle>
            <CardDescription className="text-xs">
              To bind your WhatsApp number securely, please sign in or create your AskMukthiGuru account.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              className="w-full bg-primary"
              onClick={() => {
                const target = code ? `/auth?redirect=${encodeURIComponent(`/link-whatsapp#code=${code}`)}` : "/auth";
                navigate(target);
              }}
            >
              Sign In or Create Account
              <ArrowRight className="h-4 w-4 ml-1.5" />
            </Button>
            <p className="text-[11px] text-center text-muted-foreground">
              Your credentials are never shared with or sent through WhatsApp.
            </p>
          </CardContent>
        </Card>
      ) : status?.linked ? (
        /* Case 2: Already Linked / Successful Link */
        <Card className="border-emerald-500/30 bg-emerald-500/[0.02] shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <CardTitle className="text-lg">WhatsApp Connected</CardTitle>
              </div>
              <Badge className="bg-emerald-600 text-white text-xs">Active</Badge>
            </div>
            <CardDescription className="text-xs">
              Linked to <span className="font-mono font-semibold text-foreground">{status.masked_phone}</span>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* DPDP Consent Controls */}
            <div className="space-y-4 pt-2 border-t">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                <ShieldCheck className="h-4 w-4 text-primary" />
                <span>Privacy & Consent Controls (DPDP)</span>
              </div>

              {/* Consent 1: History Sync */}
              <div className="flex items-center justify-between gap-4 p-3 rounded-lg border bg-background">
                <div className="space-y-0.5">
                  <div className="text-sm font-medium">Sync Chat History</div>
                  <div className="text-xs text-muted-foreground">
                    Allow messages sent on WhatsApp to appear in your Web conversation history.
                  </div>
                </div>
                <Switch
                  checked={status.sync_history_consent}
                  disabled={updatingConsent}
                  onCheckedChange={(val) => handleConsentToggle("sync_history_consent", val)}
                />
              </div>

              {/* Consent 2: Memory Write */}
              <div className="flex items-center justify-between gap-4 p-3 rounded-lg border bg-background">
                <div className="space-y-0.5">
                  <div className="text-sm font-medium">Spiritual Journey Memory</div>
                  <div className="text-xs text-muted-foreground">
                    Allow reflections shared via WhatsApp to personalize future guidance and practices.
                  </div>
                </div>
                <Switch
                  checked={status.memory_write_consent}
                  disabled={updatingConsent}
                  onCheckedChange={(val) => handleConsentToggle("memory_write_consent", val)}
                />
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t">
              <Button variant="outline" size="sm" className="w-full sm:w-auto text-xs" onClick={() => navigate("/chat")}>
                Return to Chat
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="w-full sm:w-auto text-xs text-rose-600 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-rose-950/20"
                onClick={handleUnlink}
              >
                <LogOut className="h-3.5 w-3.5 mr-1" />
                Disconnect WhatsApp
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        /* Case 3: Authenticated with Pending Code */
        <Card className="border-border/60 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Smartphone className="h-5 w-5 text-primary" />
              Confirm Connection
            </CardTitle>
            <CardDescription className="text-xs">
              Confirm linking your WhatsApp number to your active account ({session.user.email || "Signed In"}).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {code ? (
              <div className="space-y-3">
                <div className="bg-muted/40 p-3 rounded-lg border text-xs space-y-1">
                  <span className="text-muted-foreground block">Verification Code:</span>
                  <code className="text-primary font-mono font-bold block truncate">{code}</code>
                </div>

                {linkError && (
                  <div className="p-3 bg-rose-500/10 border border-rose-500/30 text-rose-700 dark:text-rose-400 text-xs rounded-lg flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0" />
                    <span>{linkError}</span>
                  </div>
                )}

                <Button className="w-full bg-primary" disabled={linking} onClick={handleVerify}>
                  {linking ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <ShieldCheck className="h-4 w-4 mr-1.5" />}
                  Confirm & Link WhatsApp
                </Button>
              </div>
            ) : (
              <div className="space-y-4 text-center py-4">
                <p className="text-xs text-muted-foreground">
                  To connect, text <code className="bg-muted px-1.5 py-0.5 rounded font-mono font-bold">LINK</code> to our WhatsApp companion number. You will receive a direct link to open on this device.
                </p>
                <Button variant="outline" size="sm" onClick={() => navigate("/chat")}>
                  Return to Chat
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Safety Notice */}
      <div className="bg-muted/30 border rounded-xl p-4 text-xs text-muted-foreground space-y-1.5">
        <span className="font-semibold text-foreground flex items-center gap-1.5">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Two-Channel Security Invariant
        </span>
        <p className="leading-relaxed">
          AskMukthiGuru uses cryptographic single-use challenges to bind channels. We never ask for your password on WhatsApp, and authentication tokens are never transmitted via chat. You can text <code className="font-mono">STOP</code> or <code className="font-mono">RESET</code> on WhatsApp at any time.
        </p>
      </div>
    </div>
  );
}
