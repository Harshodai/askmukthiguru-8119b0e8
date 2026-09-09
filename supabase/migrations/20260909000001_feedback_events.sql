CREATE TABLE IF NOT EXISTS feedback_events (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  message_id TEXT,
  feedback_type TEXT NOT NULL CHECK (feedback_type IN ('positive', 'negative')),
  query_text TEXT,
  response_summary TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE feedback_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users own feedback" ON feedback_events
  FOR ALL USING (auth.uid() = user_id);
