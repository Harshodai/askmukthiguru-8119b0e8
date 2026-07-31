-- Verify RLS UPDATE policies have both USING and WITH CHECK ownership predicates.
-- Idempotent: checks pg_policy for the four UPDATE policies and only recreates
-- them if either USING or WITH CHECK is missing. No-op when migration
-- 20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql already applied.
DO $$
DECLARE
    v_rec RECORD;
    v_sql TEXT;
BEGIN
    FOR v_rec IN
        SELECT
            pol.polname AS policy_name,
            ns.nspname AS schema_name,
            cls.relname AS table_name,
            pol.polqual IS NOT NULL AS has_using,
            pol.polwithcheck IS NOT NULL AS has_check
        FROM pg_policy pol
        JOIN pg_class cls ON cls.oid = pol.polrelid
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        WHERE (cls.relname, ns.nspname, pol.polname) IN (
            ('conversations', 'public', 'own_conversations_update'),
            ('chat_messages', 'public', 'own_messages_update'),
            ('meditation_sessions', 'public', 'own_sessions_update'),
            ('user_profiles', 'public', 'Users can update their own profiles')
        )
    LOOP
        IF v_rec.has_using AND v_rec.has_check THEN
            RAISE NOTICE 'Policy % on %.% already has USING and WITH CHECK; skipping.',
                v_rec.policy_name, v_rec.schema_name, v_rec.table_name;
            CONTINUE;
        END IF;

        RAISE NOTICE 'Recreating policy % on %.% to enforce USING + WITH CHECK ownership.',
            v_rec.policy_name, v_rec.schema_name, v_rec.table_name;

        v_sql := format('DROP POLICY IF EXISTS %I ON %I.%I;', v_rec.policy_name, v_rec.schema_name, v_rec.table_name);
        EXECUTE v_sql;

        IF v_rec.table_name = 'chat_messages' THEN
            v_sql := format(
                'CREATE POLICY %I ON %I.%I FOR UPDATE TO authenticated '
                || 'USING (conversation_id IN (SELECT c.id FROM public.conversations c WHERE c.user_id = auth.uid())) '
                || 'WITH CHECK (conversation_id IN (SELECT c.id FROM public.conversations c WHERE c.user_id = auth.uid()));',
                v_rec.policy_name, v_rec.schema_name, v_rec.table_name
            );
        ELSE
            v_sql := format(
                'CREATE POLICY %I ON %I.%I FOR UPDATE TO authenticated '
                || 'USING (user_id = auth.uid()) '
                || 'WITH CHECK (user_id = auth.uid());',
                v_rec.policy_name, v_rec.schema_name, v_rec.table_name
            );
        END IF;
        EXECUTE v_sql;
    END LOOP;
END $$;
