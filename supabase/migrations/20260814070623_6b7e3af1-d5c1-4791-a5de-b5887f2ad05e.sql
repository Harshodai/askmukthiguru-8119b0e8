CREATE TABLE IF NOT EXISTS public.doctrine_faqs (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  question text NOT NULL,
  answer text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT doctrine_faqs_question_unique UNIQUE (question)
);

GRANT SELECT ON public.doctrine_faqs TO anon;
GRANT SELECT ON public.doctrine_faqs TO authenticated;
GRANT ALL ON public.doctrine_faqs TO service_role;

ALTER TABLE public.doctrine_faqs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Active doctrine FAQs are publicly readable" ON public.doctrine_faqs;
CREATE POLICY "Active doctrine FAQs are publicly readable"
  ON public.doctrine_faqs FOR SELECT
  USING (is_active);

DROP POLICY IF EXISTS "Admins manage doctrine FAQs" ON public.doctrine_faqs;
CREATE POLICY "Admins manage doctrine FAQs"
  ON public.doctrine_faqs FOR ALL
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

DROP TRIGGER IF EXISTS doctrine_faqs_touch_updated_at ON public.doctrine_faqs;
CREATE TRIGGER doctrine_faqs_touch_updated_at
  BEFORE UPDATE ON public.doctrine_faqs
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

NOTIFY pgrst, 'reload schema';