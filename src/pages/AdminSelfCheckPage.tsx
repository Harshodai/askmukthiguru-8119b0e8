import { useEffect, useState } from "react";
import { supabase } from "@/integrations/supabase/client";

type Diag = {
  authenticated: boolean;
  user_id?: string;
  profile_present?: boolean;
  display_name?: string;
  roles?: string[];
  is_admin?: boolean;
};

type Row = { label: string; pass: boolean; detail?: string };

/**
 * /admin/self-check — public route (guarded by auth, not admin) that shows a
 * granular checklist so a designated admin can verify their grant took effect.
 */
export default function AdminSelfCheckPage() {
  const [diag, setDiag] = useState<Diag | null>(null);
  const [email, setEmail] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data: session } = await supabase.auth.getSession();
        setEmail(session.session?.user?.email ?? "");
        const { data, error } = await supabase.rpc("whoami_diagnostics");
        if (error) throw error;
        setDiag(data as unknown as Diag);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const rows: Row[] = diag
    ? [
        { label: "Authenticated", pass: !!diag.authenticated, detail: email },
        { label: "Profile row exists", pass: !!diag.profile_present, detail: diag.display_name },
        {
          label: "Base 'user' role assigned",
          pass: (diag.roles ?? []).includes("user"),
          detail: (diag.roles ?? []).join(", ") || "(none)",
        },
        {
          label: "'admin' role assigned",
          pass: (diag.roles ?? []).includes("admin"),
        },
        { label: "has_role(admin) = true", pass: !!diag.is_admin },
      ]
    : [];

  const allPass = rows.length > 0 && rows.every((r) => r.pass);

  return (
    <div className="mx-auto max-w-2xl p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Admin permission self-check</h1>
      <p className="text-sm text-muted-foreground">
        Verifies that the currently signed-in account has admin privileges wired end-to-end.
      </p>

      {loading && <div>Loading diagnostics…</div>}
      {err && (
        <div className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {err}
        </div>
      )}

      {!loading && !err && (
        <>
          <div
            data-testid="admin-selfcheck-status"
            className={
              "rounded-lg border p-4 text-sm " +
              (allPass
                ? "border-emerald-500/40 bg-emerald-500/5 text-emerald-700"
                : "border-amber-500/40 bg-amber-500/5 text-amber-700")
            }
          >
            {allPass
              ? "✓ All checks passed — you have full admin access."
              : "✗ At least one check failed. Details below."}
          </div>

          <ul className="divide-y rounded-lg border">
            {rows.map((r) => (
              <li
                key={r.label}
                className="flex items-start justify-between gap-4 p-3"
                data-testid={`selfcheck-row-${r.label.replace(/\s+/g, "-").toLowerCase()}`}
              >
                <div>
                  <div className="font-medium">{r.label}</div>
                  {r.detail && (
                    <div className="text-xs text-muted-foreground">{r.detail}</div>
                  )}
                </div>
                <div
                  className={
                    "text-sm font-mono " + (r.pass ? "text-emerald-600" : "text-red-600")
                  }
                >
                  {r.pass ? "PASS" : "FAIL"}
                </div>
              </li>
            ))}
          </ul>

          <details className="rounded border p-3 text-xs">
            <summary className="cursor-pointer text-muted-foreground">Raw diagnostics</summary>
            <pre className="mt-2 overflow-auto">{JSON.stringify(diag, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
