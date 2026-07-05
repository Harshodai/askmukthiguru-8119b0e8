import { useCallback, useEffect, useState } from 'react';
import { Quote, RefreshCw } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getWisdomTips, regenerateWisdomTips, type WisdomTipsPayload } from '@/admin/lib/api';

const daysUntil = (iso: string): number => {
  const ms = new Date(iso).getTime() - Date.now();
  return Math.max(0, Math.ceil(ms / (24 * 60 * 60 * 1000)));
};

type LoadState = 'loading' | 'ready' | 'unavailable' | 'error';

export default function TeachingTipsPage() {
  const [payload, setPayload] = useState<WisdomTipsPayload | null>(null);
  const [state, setState] = useState<LoadState>('loading');
  const [regenerating, setRegenerating] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const data = await getWisdomTips();
      setPayload(data);
      setState('ready');
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState(message.includes('404') ? 'unavailable' : 'error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setStatusMessage(null);
    try {
      const data = await regenerateWisdomTips();
      setPayload(data);
      setState('ready');
      setStatusMessage(`Regenerated ${data.tips.length} tips — next auto-refresh in ${daysUntil(data.expires_at)}d.`);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Regeneration failed');
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Quote className="w-4 h-4 text-ojas" /> Teaching Tips
            </CardTitle>
            <CardDescription>
              Wisdom quotes shown to seekers while an answer is generating. Cached for 7 days;
              regenerate to sample a fresh set from the ingested teachings.
            </CardDescription>
          </div>
          <Button onClick={handleRegenerate} disabled={regenerating} size="sm" className="gap-2">
            <RefreshCw className={`w-4 h-4 ${regenerating ? 'animate-spin' : ''}`} />
            {regenerating ? 'Regenerating…' : 'Regenerate Tips'}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {payload && state === 'ready' && (
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">{payload.tips.length} tips</Badge>
              <span>Generated {new Date(payload.generated_at).toLocaleString()}</span>
              <span>·</span>
              <span>Next auto-refresh in {daysUntil(payload.expires_at)}d</span>
            </div>
          )}
          {statusMessage && <p className="text-xs text-ojas">{statusMessage}</p>}

          {state === 'loading' && (
            <p className="text-sm text-muted-foreground animate-pulse">Loading tips…</p>
          )}
          {state === 'unavailable' && (
            <p className="text-sm text-muted-foreground">
              Tips service not available yet — the chat falls back to the curated static list.
            </p>
          )}
          {state === 'error' && (
            <p className="text-sm text-destructive">Could not load tips. Check the backend and try again.</p>
          )}

          {state === 'ready' && payload && (
            <ul className="grid gap-3 md:grid-cols-2">
              {payload.tips.map((tip) => (
                <li key={tip.id}>
                  <Card className="h-full border-ojas/20">
                    <CardContent className="pt-4 space-y-2">
                      <p className="font-serif italic text-sm leading-relaxed">“{tip.text}”</p>
                      <p className="text-[11px] text-muted-foreground">
                        🪷 {tip.teacher}
                        {tip.source && tip.source !== 'curated' && (
                          <span className="ml-1 opacity-70">· {tip.source}</span>
                        )}
                      </p>
                    </CardContent>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
