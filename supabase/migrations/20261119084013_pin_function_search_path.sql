-- Supabase advisor 0011 (function_search_path_mutable), 2026-11-19.
-- These three functions reference only built-ins and schema-qualified public
-- tables, so a fixed search_path changes no behaviour; it stops a caller's
-- search_path from resolving their unqualified names to another schema.
ALTER FUNCTION public.push_devices_touch_updated_at() SET search_path = public, pg_temp;
ALTER FUNCTION public.touch_canonical_memories_updated_at() SET search_path = public, pg_temp;
ALTER FUNCTION public.append_healing_step(uuid, text, text, integer) SET search_path = public, pg_temp;
