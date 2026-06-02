import { useState } from "react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

export function SeedDemoButton() {
  const [loading, setLoading] = useState(false);
  const qc = useQueryClient();

  const onClick = async () => {
    setLoading(true);
    try {
      const { data, error } = await (supabase as unknown as { rpc: (fn: string) => Promise<{ data: { ok?: boolean; reason?: string } | null; error: Error | null }> }).rpc("seed_admin_demo");
      if (error) throw error;
      if (data?.ok === false) {
        toast.error(`Seed failed: ${data.reason ?? "unknown"}`);
      } else {
        toast.success("Demo traces seeded. Open Queries to drill in.");
        qc.invalidateQueries({ queryKey: ["admin"] });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Seed failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button variant="outline" size="sm" onClick={onClick} disabled={loading}>
      <Sparkles className="h-4 w-4" />
      {loading ? "Seeding…" : "Seed demo traces"}
    </Button>
  );
}
