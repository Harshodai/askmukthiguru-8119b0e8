-- Restore table privileges required by user-owned session and profile RLS policies.
-- RLS remains the row-level boundary; these grants only permit policy evaluation.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.meditation_sessions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_profiles TO authenticated;
GRANT ALL ON public.meditation_sessions TO service_role;
GRANT ALL ON public.user_profiles TO service_role;

DO $$
BEGIN
  IF NOT has_table_privilege(
    'authenticated',
    'public.meditation_sessions',
    'SELECT,INSERT,UPDATE,DELETE'
  ) THEN
    RAISE EXCEPTION 'authenticated meditation_sessions table grants were not applied';
  END IF;
  IF NOT has_table_privilege(
    'authenticated',
    'public.user_profiles',
    'SELECT,INSERT,UPDATE,DELETE'
  ) THEN
    RAISE EXCEPTION 'authenticated user_profiles table grants were not applied';
  END IF;
  IF NOT has_table_privilege(
    'service_role',
    'public.meditation_sessions',
    'SELECT,INSERT,UPDATE,DELETE'
  ) THEN
    RAISE EXCEPTION 'service_role meditation_sessions table grants were not applied';
  END IF;
  IF NOT has_table_privilege(
    'service_role',
    'public.user_profiles',
    'SELECT,INSERT,UPDATE,DELETE'
  ) THEN
    RAISE EXCEPTION 'service_role user_profiles table grants were not applied';
  END IF;
END
$$;
