-- ============================================================================
-- Upcoming events: admin-published events shown to seekers (same flow as daily teachings).
-- REVERT: manual undo, human review before prod, never auto-revert.
-- REVERT: DROP TABLE IF EXISTS public.upcoming_events;
-- REVERT: DELETE FROM storage.buckets WHERE id = 'event-media';  (empty the bucket first)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.upcoming_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
  description TEXT CHECK (description IS NULL OR char_length(description) <= 600),
  starts_at   TIMESTAMPTZ NOT NULL,
  ends_at     TIMESTAMPTZ,
  location    TEXT CHECK (location IS NULL OR char_length(location) <= 160),
  link_url    TEXT CHECK (link_url IS NULL OR link_url ~ '^https://'),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  CHECK (ends_at IS NULL OR ends_at >= starts_at)
);

-- Optional poster image (public URL from the daily-teachings storage bucket, events/ prefix).
ALTER TABLE public.upcoming_events
  ADD COLUMN IF NOT EXISTS image_url TEXT CHECK (image_url IS NULL OR image_url ~ '^https?://');

CREATE INDEX IF NOT EXISTS upcoming_events_starts_at_idx ON public.upcoming_events (starts_at);

ALTER TABLE public.upcoming_events ENABLE ROW LEVEL SECURITY;

-- Everyone sees events that have not finished yet.
CREATE POLICY "upcoming_events_read_active" ON public.upcoming_events
  FOR SELECT TO anon, authenticated
  USING (COALESCE(ends_at, starts_at) >= now());

-- Admins see everything (including past events) and manage the list.
CREATE POLICY "upcoming_events_admin_read" ON public.upcoming_events
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "upcoming_events_admin_insert" ON public.upcoming_events
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "upcoming_events_admin_update" ON public.upcoming_events
  FOR UPDATE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "upcoming_events_admin_delete" ON public.upcoming_events
  FOR DELETE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

-- Optional audio/video attachment. The file is deleted automatically after the event ends
-- (backend task tasks.event_media_tasks.purge_ended_event_media, hourly).
ALTER TABLE public.upcoming_events
  ADD COLUMN IF NOT EXISTS media_url  TEXT CHECK (media_url IS NULL OR media_url ~ '^https?://'),
  ADD COLUMN IF NOT EXISTS media_path TEXT,
  ADD COLUMN IF NOT EXISTS media_type TEXT CHECK (media_type IS NULL OR media_type IN ('audio', 'video'));

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('event-media', 'event-media', true, 52428800, ARRAY['audio/*', 'video/*'])
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "event_media_public_read" ON storage.objects
  FOR SELECT USING (bucket_id = 'event-media');

CREATE POLICY "event_media_admin_insert" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (bucket_id = 'event-media' AND public.has_role(auth.uid(), 'admin'));

CREATE POLICY "event_media_admin_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (bucket_id = 'event-media' AND public.has_role(auth.uid(), 'admin'));

CREATE POLICY "event_media_admin_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (bucket_id = 'event-media' AND public.has_role(auth.uid(), 'admin'));

-- Table privileges (row-level security above still decides which rows).
GRANT SELECT ON public.upcoming_events TO anon, authenticated;
GRANT INSERT, UPDATE, DELETE ON public.upcoming_events TO authenticated;
-- The backend's hourly media cleanup runs as service_role.
GRANT ALL ON public.upcoming_events TO service_role;

NOTIFY pgrst, 'reload schema';
