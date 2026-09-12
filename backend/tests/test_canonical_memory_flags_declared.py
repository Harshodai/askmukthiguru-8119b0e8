"""The canonical-memory flags must exist, or the module cannot be configured.

`services/canonical_memory/chat_integration.py` reads five flags through
`getattr(settings, name, default)`. None were declared on Settings, so every one
resolved to its False default regardless of environment — the switches looked
real and controlled nothing.
"""

from app.config import Settings
from services.canonical_memory import chat_integration

FLAGS = (
    "canonical_memory_enabled",
    "canonical_memory_retrieval",
    "memory_shadow",
    "memory_write",
    "memory_influence",
)


def test_every_flag_the_module_reads_is_declared():
    s = Settings()
    for name in FLAGS:
        assert hasattr(s, name), f"{name} is read by chat_integration but not declared"


def test_flags_are_off_by_default():
    """The integration has no production caller; default-on would be a lie."""
    s = Settings()
    for name in FLAGS:
        assert getattr(s, name) is False


def test_module_reads_the_flags_directly():
    """Direct attribute access, not getattr on a variable name.

    A `getattr(settings, name, default)` is invisible to the dead-settings scan
    in test_wiring_invariants.py — which is exactly how these five came to be
    read here yet never declared, silently resolving to their defaults.
    """
    src = __import__("inspect").getsource(chat_integration)
    for name in FLAGS:
        assert f"settings.{name}" in src, f"{name} must be read as a real attribute"
