import { useState, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';

export interface UseSeedDemoReturn {
  loading: boolean;
  seed: () => Promise<void>;
}

type SeedRpc = {
  rpc: (fn: string) => Promise<{ data: { ok?: boolean; reason?: string } | null; error: Error | null }>;
};

export function useSeedDemo(): UseSeedDemoReturn {
  const [loading, setLoading] = useState(false);
  const qc = useQueryClient();

  const seed = useCallback(async () => {
    setLoading(true);
    try {
      const { data, error } = await (supabase as unknown as SeedRpc).rpc('seed_admin_demo');
      if (error) throw error;
      if (data?.ok === false) {
        toast.error(`Seed failed: ${data.reason ?? 'unknown'}`);
      } else {
        toast.success('Demo traces seeded. Open Queries to drill in.');
        qc.invalidateQueries({ queryKey: ['admin'] });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`Seed failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [qc]);

  return { loading, seed };
}
