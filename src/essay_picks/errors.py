from __future__ import annotations


class EssayPicksError(Exception):
    """Base exception for application-owned failures."""


class ConfigFailure(EssayPicksError):
    """Raised when application configuration is invalid."""


class ValidationFailure(EssayPicksError):
    """Raised when untrusted source data violates the ingestion contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INVALID_SOURCE",
        retryable: bool = False,
        recovery_command: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.recovery_command = recovery_command


class PersistenceFailure(EssayPicksError):
    """Raised when immutable history or a projection cannot be persisted safely."""
