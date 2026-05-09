ALTER TABLE public.daily_teachings REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE public.daily_teachings;