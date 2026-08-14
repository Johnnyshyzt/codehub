"""Provider-level errors used by Router fallback."""

from __future__ import annotations


class ProviderError(Exception):
    """Base error for model provider failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable


class RateLimitError(ProviderError):
    def __init__(self, message: str = "Rate limited", *, provider: str | None = None):
        super().__init__(message, provider=provider, status_code=429, retryable=True)


class TimeoutError(ProviderError):
    def __init__(self, message: str = "Request timed out", *, provider: str | None = None):
        super().__init__(message, provider=provider, status_code=None, retryable=True)


class AuthError(ProviderError):
    def __init__(self, message: str = "Authentication failed", *, provider: str | None = None):
        super().__init__(message, provider=provider, status_code=401, retryable=False)


class ServerError(ProviderError):
    def __init__(
        self,
        message: str = "Upstream server error",
        *,
        provider: str | None = None,
        status_code: int = 500,
    ):
        super().__init__(message, provider=provider, status_code=status_code, retryable=True)
