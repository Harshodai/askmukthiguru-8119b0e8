"""Qdrant version compatibility check.

Sparse vectors (used by hybrid search in services/qdrant/searcher.py) require
Qdrant server >= 1.8. This is a non-fatal warning, not a hard startup abort —
matching the degrade-gracefully pattern used by every other lifespan check in
app/main.py (LightRAG init, background init): a stale version string format
or a transient handshake hiccup here must not take down production.
"""

import logging

logger = logging.getLogger(__name__)

MIN_QDRANT_VERSION = (1, 8)


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' into a tuple of ints for comparison. Non-numeric parts drop."""
    parts = []
    for p in version_str.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def check_qdrant_version(client) -> None:
    """Warn if the connected Qdrant server is older than MIN_QDRANT_VERSION.

    Args:
        client: QdrantClient instance (from QdrantClientManager.client)
    """
    try:
        info = client.info()
        version_str = getattr(info, "version", "") or ""
        parsed = _parse_version(version_str)

        if not parsed:
            logger.info(
                f"Qdrant version check: could not parse version string {version_str!r}, skipping"
            )
            return

        if parsed < MIN_QDRANT_VERSION:
            logger.warning(
                f"Qdrant server version {version_str} is older than the recommended "
                f"minimum {'.'.join(map(str, MIN_QDRANT_VERSION))} — sparse vector "
                "hybrid search may not work correctly. Upgrade Qdrant when possible."
            )
        else:
            logger.info(
                f"Qdrant version check: {version_str} OK (>= {'.'.join(map(str, MIN_QDRANT_VERSION))})"
            )
    except Exception as exc:
        # Never let a version-check hiccup take down startup — this is advisory only.
        logger.info(f"Qdrant version check skipped (non-fatal): {exc}")


if __name__ == "__main__":
    assert _parse_version("1.8.0") == (1, 8, 0)
    assert _parse_version("1.14.1") == (1, 14, 1)
    assert _parse_version("1.7.4") < MIN_QDRANT_VERSION
    assert _parse_version("1.8.0") >= MIN_QDRANT_VERSION
    assert _parse_version("") == ()
    print("✓ qdrant_version_check self-check passed")
