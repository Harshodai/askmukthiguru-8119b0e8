CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role app_role)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  select exists (
    select 1 from public.user_roles
    where user_id = _user_id and role = _role
  )
  and (
    _user_id = auth.uid()
    or coalesce(auth.role(), '') = 'service_role'
    or session_user in ('postgres', 'supabase_admin')
    or exists (select 1 from public.user_roles where user_id = auth.uid() and role = 'admin')
  )
$$;

REVOKE ALL ON FUNCTION public.erase_launch_subscription(text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.erase_launch_subscription(text) TO service_role;