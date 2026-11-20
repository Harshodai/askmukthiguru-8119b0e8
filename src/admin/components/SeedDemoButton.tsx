import { Button } from "@/components/ui/button";
import { Sprout } from "lucide-react";
import { useSeedDemo } from "@/admin/hooks/useSeedDemo";

export function SeedDemoButton() {
  const { loading, seed } = useSeedDemo();

  return (
    <Button variant="outline" size="sm" onClick={seed} disabled={loading}>
      <Sprout className="h-4 w-4" />
      {loading ? "Seeding…" : "Seed demo traces"}
    </Button>
  );
}
