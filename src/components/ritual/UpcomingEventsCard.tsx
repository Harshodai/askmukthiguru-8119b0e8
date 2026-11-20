import { useTranslation } from 'react-i18next';
import { CalendarDays, ExternalLink, MapPin } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { useUpcomingEvents, type UpcomingEvent } from '@/hooks/useUpcomingEvents';

const formatWhen = (event: UpcomingEvent): string => {
  const start = new Date(event.starts_at);
  if (Number.isNaN(start.getTime())) return '';
  return start.toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Upcoming events published by admins. Renders nothing when there are none,
 * so an empty list never shows a placeholder or an invented event.
 */
export const UpcomingEventsCard = () => {
  const { t } = useTranslation();
  const { events, loading } = useUpcomingEvents();

  if (loading || events.length === 0) return null;

  return (
    <Card className="rounded-2xl border-hairline p-5" data-testid="upcoming-events">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <CalendarDays className="h-4 w-4 text-ojas" aria-hidden="true" />
        {t('events.title', 'Upcoming events')}
      </h2>
      <ul className="mt-3 divide-y divide-border/40">
        {events.map((event) => (
          <li key={event.id} className="py-3 first:pt-0 last:pb-0">
            {event.image_url && (
              <img
                src={event.image_url}
                alt={event.title}
                loading="lazy"
                className="mb-3 max-h-80 w-full rounded-xl border border-border/40 object-contain bg-muted/20"
              />
            )}
            {event.media_url && event.media_type === 'video' && (
              <video
                src={event.media_url}
                controls
                preload="metadata"
                className="mb-3 max-h-80 w-full rounded-xl bg-black"
                aria-label={event.title}
              />
            )}
            {event.media_url && event.media_type === 'audio' && (
              <audio src={event.media_url} controls preload="metadata" className="mb-3 w-full" aria-label={event.title} />
            )}
            <p className="text-sm font-medium text-foreground">{event.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">{formatWhen(event)}</p>
            {event.location && (
              <p className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" />
                {event.location}
              </p>
            )}
            {event.description && (
              <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{event.description}</p>
            )}
            {event.link_url && (
              <a
                href={event.link_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex min-h-11 items-center gap-1 text-sm font-medium text-ojas-ink hover:underline dark:text-ojas"
              >
                {t('events.details', 'Details')}
                <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </a>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
};
