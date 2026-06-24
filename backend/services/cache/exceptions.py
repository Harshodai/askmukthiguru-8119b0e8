"""Cache-specific exceptions."""


class CacheInitializationError(RuntimeError):
    """Raised when a cache adapter cannot initialize in fail-closed mode."""
