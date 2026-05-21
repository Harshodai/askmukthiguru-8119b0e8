"""
Mukthi Guru — Request ID Context Propagation

Provides a module-level context variable for correlation/request IDs
that is accessible from anywhere in the async call chain.
"""
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request ID from the async context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the current request ID in the async context."""
    request_id_var.set(request_id)
