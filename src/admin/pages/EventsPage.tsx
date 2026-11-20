import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { InlineSpinner } from '@/components/common/BrandedSpinner';
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
} from '@/components/ui/alert-dialog';
import { supabase } from '@/integrations/supabase/client';
import { EVENT_COLUMNS, eventsTable, type UpcomingEvent } from '@/hooks/useUpcomingEvents';

const formatWhen = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
};

const MAX_POSTER_BYTES = 5 * 1024 * 1024;
const MAX_MEDIA_BYTES = 50 * 1024 * 1024;
const MEDIA_BUCKET = 'event-media';

const EMPTY_FORM = { title: '', description: '', startsAt: '', endsAt: '', location: '', linkUrl: '' };

/** Admin: publish and remove upcoming events. Seekers see the ones that have not finished. */
const EventsPage = () => {
  const [form, setForm] = useState(EMPTY_FORM);
  const [events, setEvents] = useState<UpcomingEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [poster, setPoster] = useState<File | null>(null);
  const [media, setMedia] = useState<File | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error: loadError } = await eventsTable().select(EVENT_COLUMNS).order('starts_at', { ascending: false });
    if (loadError) setError(`Could not load events: ${loadError.message}`);
    else setEvents((data ?? []) as UpcomingEvent[]);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const set = (key: keyof typeof EMPTY_FORM) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!form.title.trim() || !form.startsAt) {
      setError('A title and a start time are required.');
      return;
    }
    if (form.linkUrl.trim() && !form.linkUrl.trim().startsWith('https://')) {
      setError('The link must start with https://');
      return;
    }
    if (poster && (!poster.type.startsWith('image/') || poster.size > MAX_POSTER_BYTES)) {
      setError('The poster must be an image under 5 MB.');
      return;
    }
    const mediaType = media?.type.startsWith('video/') ? 'video' : media?.type.startsWith('audio/') ? 'audio' : null;
    if (media && (!mediaType || media.size > MAX_MEDIA_BYTES)) {
      setError('The recording must be an audio or video file under 50 MB.');
      return;
    }
    setSaving(true);
    let imageUrl: string | null = null;
    if (poster) {
      const extension = poster.name.split('.').pop()?.toLowerCase().replace(/[^a-z0-9]/g, '') || 'jpg';
      const path = `events/${crypto.randomUUID()}.${extension}`;
      const { error: uploadError } = await supabase.storage.from('daily-teachings').upload(path, poster);
      if (uploadError) {
        setSaving(false);
        setError(`Poster upload failed: ${uploadError.message}`);
        return;
      }
      imageUrl = supabase.storage.from('daily-teachings').getPublicUrl(path).data.publicUrl;
    }
    let mediaUrl: string | null = null;
    let mediaPath: string | null = null;
    if (media) {
      const extension = media.name.split('.').pop()?.toLowerCase().replace(/[^a-z0-9]/g, '') || 'bin';
      mediaPath = `${crypto.randomUUID()}.${extension}`;
      const { error: mediaError } = await supabase.storage.from(MEDIA_BUCKET).upload(mediaPath, media);
      if (mediaError) {
        setSaving(false);
        setError(`Recording upload failed: ${mediaError.message}`);
        return;
      }
      mediaUrl = supabase.storage.from(MEDIA_BUCKET).getPublicUrl(mediaPath).data.publicUrl;
    }
    const { data: userData } = await supabase.auth.getUser();
    const { error: insertError } = await eventsTable().insert({
      title: form.title.trim(),
      description: form.description.trim() || null,
      starts_at: new Date(form.startsAt).toISOString(),
      ends_at: form.endsAt ? new Date(form.endsAt).toISOString() : null,
      location: form.location.trim() || null,
      link_url: form.linkUrl.trim() || null,
      image_url: imageUrl,
      media_url: mediaUrl,
      media_path: mediaPath,
      media_type: mediaType,
      created_by: userData.user?.id ?? null,
    });
    setSaving(false);
    if (insertError) {
      setError(`Could not publish: ${insertError.message}`);
      return;
    }
    setForm(EMPTY_FORM);
    setPoster(null);
    setMedia(null);
    await load();
  };

  const remove = async (event: UpcomingEvent) => {
    setError(null);
    if (event.media_path) {
      const { error: removeError } = await supabase.storage.from(MEDIA_BUCKET).remove([event.media_path]);
      if (removeError) {
        setError(`Could not delete the recording: ${removeError.message}`);
        return;
      }
    }
    const id = event.id;
    const { error: deleteError } = await eventsTable().delete().eq('id', id);
    if (deleteError) setError(`Could not delete: ${deleteError.message}`);
    else await load();
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Publish an event</CardTitle>
          <CardDescription>Seekers see it on the Practices page until it ends.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="event-title">Title</Label>
              <Input id="event-title" value={form.title} maxLength={120} onChange={(e) => set('title')(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="event-start">Starts</Label>
              <Input id="event-start" type="datetime-local" value={form.startsAt} onChange={(e) => set('startsAt')(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="event-end">Ends (optional)</Label>
              <Input id="event-end" type="datetime-local" value={form.endsAt} onChange={(e) => set('endsAt')(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="event-location">Where (optional)</Label>
              <Input id="event-location" value={form.location} maxLength={160} onChange={(e) => set('location')(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="event-link">Link (optional, https)</Label>
              <Input id="event-link" type="url" value={form.linkUrl} onChange={(e) => set('linkUrl')(e.target.value)} />
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="event-poster">Poster image (optional, under 5 MB)</Label>
              <Input
                id="event-poster"
                type="file"
                accept="image/*"
                onChange={(e) => setPoster(e.target.files?.[0] ?? null)}
              />
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="event-media">Audio or video (optional, under 50 MB)</Label>
              <Input
                id="event-media"
                type="file"
                accept="audio/*,video/*"
                onChange={(e) => setMedia(e.target.files?.[0] ?? null)}
              />
              <p className="text-xs text-muted-foreground">The file is deleted automatically after the event ends.</p>
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="event-description">Details (optional)</Label>
              <Textarea id="event-description" value={form.description} maxLength={600} onChange={(e) => set('description')(e.target.value)} />
            </div>
            {error && (
              <p role="alert" className="sm:col-span-2 text-sm text-destructive">
                {error}
              </p>
            )}
            <div className="sm:col-span-2">
              <Button type="submit" disabled={saving}>
                {saving ? 'Publishing…' : 'Publish event'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>All events</CardTitle>
          <CardDescription>Including past ones, newest first.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <InlineSpinner className="p-4" />
          ) : events.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events yet.</p>
          ) : (
            <ul className="divide-y divide-border/40">
              {events.map((event) => (
                <li key={event.id} className="flex items-start justify-between gap-3 py-3">
                  {event.image_url && (
                    <img src={event.image_url} alt="" className="h-12 w-12 shrink-0 rounded-md object-cover" />
                  )}
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">{event.title}</p>
                    <p className="text-xs text-muted-foreground">{formatWhen(event.starts_at)}</p>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={`Delete ${event.title}`}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete this event?</AlertDialogTitle>
                        <AlertDialogDescription>
                          "{event.title}" will disappear for everyone. This cannot be undone.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => void remove(event)}>Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default EventsPage;
