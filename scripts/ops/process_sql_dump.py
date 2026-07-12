import re
import sys

def main():
    filepath = "public_schema_dump.sql"
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        sys.exit(1)

    print("Post-processing SQL schema dump...")

    # 1. Add IF NOT EXISTS to CREATE SCHEMA
    content = content.replace("CREATE SCHEMA public;", "CREATE SCHEMA IF NOT EXISTS public;")

    # 2. Add IF NOT EXISTS to CREATE TABLE
    content = re.sub(
        r"CREATE TABLE public\.(\w+)",
        r"CREATE TABLE IF NOT EXISTS public.\1",
        content
    )

    # 3. Add IF NOT EXISTS to CREATE SEQUENCE
    content = re.sub(
        r"CREATE SEQUENCE public\.(\w+)",
        r"CREATE SEQUENCE IF NOT EXISTS public.\1",
        content
    )

    # 4. Add IF NOT EXISTS to CREATE INDEX
    content = re.sub(
        r"CREATE INDEX (\w+)",
        r"CREATE INDEX IF NOT EXISTS \1",
        content
    )
    content = re.sub(
        r"CREATE UNIQUE INDEX (\w+)",
        r"CREATE UNIQUE INDEX IF NOT EXISTS \1",
        content
    )

    # 5. Wrap CREATE TYPE public.app_role block
    app_role_target = """CREATE TYPE public.app_role AS ENUM (
    'admin',
    'user'
);"""
    app_role_replacement = """DO $$
BEGIN
    CREATE TYPE public.app_role AS ENUM (
        'admin',
        'user'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;"""
    content = content.replace(app_role_target, app_role_replacement)

    # 6. Wrap CREATE TYPE public.assistant_visibility block
    visibility_target = """CREATE TYPE public.assistant_visibility AS ENUM (
    'public',
    'link',
    'private'
);"""
    visibility_replacement = """DO $$
BEGIN
    CREATE TYPE public.assistant_visibility AS ENUM (
        'public',
        'link',
        'private'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;"""
    content = content.replace(visibility_target, visibility_replacement)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print("Successfully processed public_schema_dump.sql to schema-only with IF NOT EXISTS qualifiers!")

if __name__ == "__main__":
    main()
