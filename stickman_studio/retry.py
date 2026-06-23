"""
retry.py
========
Centralized auto-retry / backoff for Vertex AI calls. Handles the
common transient failures: 429 (rate limit / quota), 503, 500, and
deadline exceeded. Uses tenacity for exponential backoff + jitter and
logs every retry attempt so rate limiting is visible in the logs.
"""

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
    before_sleep_log,
)

from .config import settings

log = logging.getLogger("stickman_studio.retry")

# Exception types from google-api-core that indicate a retryable condition.
_RATE_LIMIT_TYPE: type[BaseException] | None = None
try:
    from google.api_core import exceptions as gexc

    _RATE_LIMIT_TYPE = gexc.ResourceExhausted
    _RETRYABLE_TYPES: tuple[type[Exception], ...] = (
        gexc.ResourceExhausted,   # 429 — rate limit / quota
        gexc.ServiceUnavailable,  # 503
        gexc.InternalServerError, # 500
        gexc.DeadlineExceeded,    # 504 / timeout
        gexc.Aborted,
        gexc.TooManyRequests,
    )
except Exception:  # pragma: no cover - SDK not installed at lint time
    _RETRYABLE_TYPES = ()


def _is_retryable(exc: BaseException) -> bool:
    """Return True if the exception should trigger a retry."""
    if _RETRYABLE_TYPES and isinstance(exc, _RETRYABLE_TYPES):
        if _RATE_LIMIT_TYPE is not None and isinstance(exc, _RATE_LIMIT_TYPE):
            log.warning("Rate limit / quota hit (429). Backing off and retrying...")
        return True

    # Fallback: inspect the message for rate-limit signatures from any SDK layer.
    msg = str(exc).lower()
    signatures = ("429", "rate limit", "resource exhausted", "quota",
                  "503", "unavailable", "deadline exceeded", "try again")
    if any(s in msg for s in signatures):
        log.warning("Transient error detected (%s). Retrying with backoff...",
                    exc.__class__.__name__)
        return True
    return False


def with_retry(func):
    """Decorator applying the project-wide retry policy to a callable."""
    wrapped = retry(
        reraise=True,
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential_jitter(
            initial=settings.retry_base_delay,
            max=settings.retry_base_delay * 16,
        ),
        before_sleep=before_sleep_log(log, logging.WARNING),
    )(func)
    return wrapped
