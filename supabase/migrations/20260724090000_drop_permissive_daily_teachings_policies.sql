DROP POLICY IF EXISTS "Public can read teachings" ON public.daily_teachings;
DROP POLICY IF EXISTS "daily_teachings_public" ON public.daily_teachings;

NOTIFY pgrst, 'reload schema';
