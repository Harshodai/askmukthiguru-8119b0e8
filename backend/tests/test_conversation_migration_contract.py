from pathlib import Path

MIGRATIONS = Path(__file__).parents[2] / "supabase" / "migrations"
GRANTS = MIGRATIONS / "20260825000000_restore_conversation_table_grants.sql"
TRIGGER_FIX = MIGRATIONS / "20260825000001_fix_chat_message_profile_trigger.sql"
ACTIVITY_GRANTS = MIGRATIONS / "20260825000002_restore_user_activity_table_grants.sql"


def test_conversation_tables_have_authenticated_and_service_role_grants() -> None:
    sql = GRANTS.read_text(encoding="utf-8")

    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.conversations TO authenticated;" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO authenticated;" in sql
    assert "GRANT ALL ON public.conversations TO service_role;" in sql
    assert "GRANT ALL ON public.chat_messages TO service_role;" in sql


def test_user_activity_tables_have_authenticated_and_service_role_grants() -> None:
    sql = ACTIVITY_GRANTS.read_text(encoding="utf-8")

    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.meditation_sessions TO authenticated;" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_profiles TO authenticated;" in sql
    assert "GRANT ALL ON public.meditation_sessions TO service_role;" in sql
    assert "GRANT ALL ON public.user_profiles TO service_role;" in sql


def test_chat_message_profile_trigger_resolves_owner_through_parent_conversation() -> None:
    sql = TRIGGER_FIX.read_text(encoding="utf-8")

    assert "SELECT c.user_id" in sql
    assert "NEW.conversation_id" in sql
    assert "WHERE id = owner_id" in sql
    assert "NEW.user_id" not in sql
