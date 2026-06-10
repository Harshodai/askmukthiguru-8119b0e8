"""Result type — explicit success/failure without exceptions.

Pattern: Every fallible operation returns ``Result[T]``.
Callers must handle both branches.

Example::

    result = await some_operation()
    match result:
        case Ok(value):
            print(value)
        case Err(error):
            logger.error(error)
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


class Result(Generic[T]):
    """Monad-like Result — either Ok(value) or Err(error)."""

    def __init__(self, *, value: T | None = None, error: Any | None = None) -> None:
        self._value = value
        self._error = error

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def err(cls, error: Any) -> "Result[T]":
        return cls(error=error)

    # ------------------------------------------------------------------
    # Predicates
    # ------------------------------------------------------------------

    @property
    def is_ok(self) -> bool:
        return self._error is None

    @property
    def is_err(self) -> bool:
        return self._error is not None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def unwrap(self) -> T:
        """Return value or raise RuntimeError."""
        if self.is_err:
            raise RuntimeError(f"Called unwrap on Err({self._error})")
        return self._value  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        """Return value or a default."""
        return self._value if self.is_ok else default  # type: ignore[return-value]

    def unwrap_or_else(self, fn: Any) -> T:
        """Return value or the result of calling fn with the error."""
        return self._value if self.is_ok else fn(self._error)  # type: ignore[return-value]

    def map(self, fn: Any) -> "Result[U]":
        """Apply fn to value if Ok, pass Err through."""
        if self.is_ok:
            return Result.ok(fn(self._value))
        return Result.err(self._error)  # type: ignore[return-value]

    def map_err(self, fn: Any) -> "Result[T]":
        """Map the error side."""
        if self.is_err:
            return Result.err(fn(self._error))
        return self

    def and_then(self, fn: Any) -> "Result[U]":
        """Chain another fallible operation."""
        if self.is_ok:
            return fn(self._value)
        return Result.err(self._error)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Pretty
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self.is_ok:
            return f"Ok({self._value!r})"
        return f"Err({self._error!r})"
