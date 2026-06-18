CREATE TABLE IF NOT EXISTS public.telemetry_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  session_id text,
  user_message_id text NOT NULL,
  last_message_id text,
  metric_type text NOT NULL,
  metric_value numeric NOT NULL,
  tags jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON public.telemetry_events TO authenticated;
GRANT ALL ON public.telemetry_events TO service_role;

ALTER TABLE public.telemetry_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read their own telemetry"
  ON public.telemetry_events FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Service role manages telemetry"
  ON public.telemetry_events FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS telemetry_events_user_msg_idx ON public.telemetry_events(user_message_id);
CREATE INDEX IF NOT EXISTS telemetry_events_user_id_created_idx ON public.telemetry_events(user_id, created_at DESC);