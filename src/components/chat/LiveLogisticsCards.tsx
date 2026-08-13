import { ExternalLink, ShieldCheck } from 'lucide-react';
import type { LiveLogisticsEvent } from '@/lib/chat/types';

const isHttpsUrl = (value: string | null | undefined): value is string => {
  if (!value) return false;
  try { return new URL(value).protocol === 'https:'; } catch { return false; }
};

export function LiveLogisticsCards({ events }: { events?: LiveLogisticsEvent[] }) {
  const officialEvents = (events ?? []).filter((event) => isHttpsUrl(event.official_source_url));
  if (officialEvents.length === 0) return null;

  return (
    <section aria-label="Verified event and booking information" className="w-full rounded-xl border border-emerald-500/25 bg-emerald-500/[0.06] px-3 py-3 text-sm">
      <p className="flex items-center gap-2 font-semibold text-foreground"><ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden="true" />Official event information</p>
      <div className="mt-2 space-y-2">
        {officialEvents.map((event) => (
          <div key={`${event.event_name}-${event.official_source_url}`} className="rounded-lg bg-background/55 p-2.5">
            <p className="font-medium">{event.event_name}</p>
            <p className="mt-1 text-xs text-muted-foreground">Verified {new Date(event.verified_at).toLocaleString()}</p>
            <div className="mt-2 flex flex-wrap gap-3 text-xs">
              <a href={event.official_source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-ojas underline underline-offset-2">Official details <ExternalLink className="h-3 w-3" aria-hidden="true" /></a>
              {isHttpsUrl(event.booking_url) && <a href={event.booking_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-ojas underline underline-offset-2">Booking <ExternalLink className="h-3 w-3" aria-hidden="true" /></a>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
