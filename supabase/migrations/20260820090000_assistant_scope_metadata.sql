-- Assistant scope metadata is server-authoritative retrieval policy.
-- It is separate from user-editable assistant prompts and is service-role managed.
CREATE TABLE IF NOT EXISTS public.assistant_scope_metadata (
  assistant_id UUID PRIMARY KEY REFERENCES public.assistants(id) ON DELETE CASCADE,
  corpus_id TEXT NOT NULL DEFAULT 'askmukthiguru',
  teacher_id TEXT,
  graph_namespace TEXT,
  source_release_id TEXT,
  assistant_scope_version TEXT NOT NULL DEFAULT 'v1',
  rights_status TEXT NOT NULL DEFAULT 'pending' CHECK (rights_status IN ('approved', 'pending', 'revoked')),
  rollout_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ingestion_source_filter JSONB NOT NULL DEFAULT '{}'::jsonb,
  knowledge_tags TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.assistant_scope_metadata ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.assistant_scope_metadata FROM anon, authenticated;
GRANT ALL ON TABLE public.assistant_scope_metadata TO service_role;

DROP TRIGGER IF EXISTS assistant_scope_metadata_touch ON public.assistant_scope_metadata;
CREATE TRIGGER assistant_scope_metadata_touch
  BEFORE UPDATE ON public.assistant_scope_metadata
  FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

INSERT INTO public.assistant_scope_metadata (
  assistant_id,
  corpus_id,
  teacher_id,
  assistant_scope_version,
  rights_status,
  rollout_enabled,
  knowledge_tags
)
SELECT
  a.id,
  CASE a.slug
    WHEN 'general' THEN 'askmukthiguru'
    WHEN 'relationship' THEN 'askmukthiguru'
    WHEN 'sky' THEN 'sky-private'
    ELSE 'askmukthiguru'
  END,
  NULL,
  'v1',
  CASE WHEN a.slug = 'sky' THEN 'pending' ELSE 'approved' END,
  CASE WHEN a.slug = 'sky' THEN FALSE ELSE TRUE END,
  COALESCE(a.knowledge_tags, '{}')
FROM public.assistants AS a
WHERE a.slug IN ('general', 'relationship', 'sky')
ON CONFLICT (assistant_id) DO UPDATE SET
  corpus_id = EXCLUDED.corpus_id,
  rights_status = EXCLUDED.rights_status,
  rollout_enabled = EXCLUDED.rollout_enabled,
  knowledge_tags = EXCLUDED.knowledge_tags,
  updated_at = now();

NOTIFY pgrst, 'reload schema';
