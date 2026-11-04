"""Pure helpers for enforcing the pytest-only Redis safety boundary."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit, urlunsplit

LOCAL_TEST_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "redis", "redis-test", "host.docker.internal"}
)
COMPOSE_REDIS_HOSTS = frozenset({"redis", "redis-test"})


def _authority(parts, host_override: str | None = None) -> str:
    hostname = host_override or parts.hostname
    if not hostname:
        return parts.netloc
    userinfo = ""
    if parts.username or parts.password:
        userinfo = parts.username or ""
        if parts.password:
            userinfo += f":{parts.password}"
        userinfo += "@"
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    port = f":{parts.port}" if parts.port else ""
    return f"{userinfo}{host}{port}"


def _without_db_query(parts) -> str:
    """Drop every ``db`` query parameter: redis-py lets it override the path."""
    return "&".join(
        item for item in parts.query.split("&") if item and item.split("=", 1)[0] != "db"
    )


def force_test_database(
    redis_url: str,
    *,
    database: int = 15,
    host_override: str | None = None,
) -> str:
    """Rewrite only the database selector, preserving credentials and options."""
    parts = urlsplit(redis_url)
    if parts.hostname:
        return urlunsplit(
            (
                parts.scheme,
                _authority(parts, host_override),
                f"/{database}",
                _without_db_query(parts),
                "",
            )
        )
    query = _without_db_query(parts)
    query = f"{query}&db={database}" if query else f"db={database}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def validate_test_redis_url(
    redis_url: str,
    *,
    database: int = 15,
    allow_remote: bool = False,
) -> str:
    """Reject unsupported schemes, app DBs, and unapproved remote hosts."""
    parts = urlsplit(redis_url)
    if parts.scheme not in {"redis", "rediss", "unix"}:
        raise RuntimeError("pytest Redis URL must use redis, rediss, or unix scheme")
    if parts.hostname:
        if parts.hostname.casefold() not in LOCAL_TEST_HOSTS and not allow_remote:
            raise RuntimeError("pytest Redis host is not an approved local test endpoint")
        # redis-py's parse_url lets a ``db`` query parameter override the path,
        # so validate the value redis-py will actually select.
        selected_database = parse_qs(parts.query).get("db", [None])[0] or parts.path.strip("/")
    else:
        selected_database = parse_qs(parts.query).get("db", [None])[0]
    if selected_database != str(database):
        raise RuntimeError(f"pytest Redis URL must target reserved DB /{database}")
    return redis_url
