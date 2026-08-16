import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAdmins } from "@/admin/hooks/useAdminData";
import { promoteAdmin, demoteAdmin } from "@/admin/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { fmtDate } from "@/admin/lib/formatters";
import { Trash2, Loader2 } from "lucide-react";
import { EmptyState } from "@/admin/components/EmptyState";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

export default function AdminsPage() {
  const { data, isLoading, isError, error } = useAdmins();
  const [email, setEmail] = useState("");
  const [isPromoting, setIsPromoting] = useState(false);
  const qc = useQueryClient();

  const handlePromote = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail) return;
    setIsPromoting(true);
    try {
      await promoteAdmin(cleanEmail);
      setEmail("");
      toast.success(`Promoted ${cleanEmail} to admin`);
      qc.invalidateQueries({ queryKey: ["admin", "admins"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to promote admin");
    } finally {
      setIsPromoting(false);
    }
  };

  const handleDemote = async (adminId: string, adminEmail?: string) => {
    try {
      await demoteAdmin(adminId);
      toast.success(`Revoked admin access${adminEmail ? ` for ${adminEmail}` : ""}`);
      qc.invalidateQueries({ queryKey: ["admin", "admins"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to revoke admin access");
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Admins</h1>
        <p className="text-sm text-muted-foreground">
          Promote a user to admin or revoke access.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Promote by email</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePromote} className="flex gap-2">
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              type="email"
              disabled={isPromoting}
            />
            <Button type="submit" disabled={isPromoting || !email.trim()}>
              {isPromoting ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              Promote
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Current admins</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {isLoading ? (
            <div className="p-4 text-sm text-muted-foreground">Loading…</div>
          ) : isError ? (
            <div className="p-4 text-sm text-destructive">
              Failed to load admins: {(error as Error)?.message || "Unknown error"}
            </div>
          ) : !data?.length ? (
            <EmptyState title="No admins found" />
          ) : (
            (data ?? []).map((a) => (
              <div
                key={a.id}
                className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
              >
                <div className="flex-1">
                  <div className="font-medium">{a?.email ?? "Unnamed admin"}</div>
                  <div className="text-xs text-muted-foreground">since {fmtDate(a?.created_at)}</div>
                </div>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="sm">
                      <Trash2 className="h-4 w-4" />
                      Revoke
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Revoke admin access?</AlertDialogTitle>
                      <AlertDialogDescription>
                        {a?.email ?? "This admin"} will immediately lose admin access. This cannot be undone from here — they would need to be promoted again.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => handleDemote(a.id, a.email)}
                      >
                        Revoke access
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
