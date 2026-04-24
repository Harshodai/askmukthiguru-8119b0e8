import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAdmins } from "@/admin/hooks/useAdminData";
import { promoteAdmin, demoteAdmin } from "@/admin/lib/mockData";
import { useQueryClient } from "@tanstack/react-query";
import { fmtDate } from "@/admin/lib/formatters";
import { Trash2 } from "lucide-react";

export default function AdminsPage() {
  const { data } = useAdmins();
  const [email, setEmail] = useState("");
  const qc = useQueryClient();

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
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (!email.trim()) return;
              await promoteAdmin(email.trim());
              setEmail("");
              qc.invalidateQueries({ queryKey: ["admin", "admins"] });
            }}
            className="flex gap-2"
          >
            <Input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              type="email"
            />
            <Button type="submit">Promote</Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Current admins</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data?.map((a) => (
            <div
              key={a.id}
              className="border border-border rounded-md p-3 text-sm flex items-center gap-3"
            >
              <div className="flex-1">
                <div className="font-medium">{a.email}</div>
                <div className="text-xs text-muted-foreground">since {fmtDate(a.created_at)}</div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => {
                  await demoteAdmin(a.id);
                  qc.invalidateQueries({ queryKey: ["admin", "admins"] });
                }}
              >
                <Trash2 className="h-4 w-4" />
                Revoke
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
