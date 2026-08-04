"""Bounded exponential backoff with injectable sleep/jitter for fake tests."""

from __future__ import annotations

from collections.abc import Callable
from random import Random

Sleep = Callable[[float], None]
Jitter = Callable[[], float]

_RETRYABLE_STATUS = frozenset({408, 429})


def is_retryable_status(status: int) -> bool:
    """408/429 and every 5xx are transient and retryable."""
    return status in _RETRYABLE_STATUS or 500 <= status <= 599


class RetryPolicy:
    """Exponential backoff with full jitter, capped and bounded by max_retries."""

    def __init__(
        self,
        *,
        max_retries: int,
        base_delay: float = 0.25,
        max_delay: float = 4.0,
        rng: Random | None = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._rng = rng or Random()

    def should_retry(self, *, attempt: int, retryable: bool) -> bool:
        if attempt >= self.max_retries:
            return False
        return retryable

    def delay_for(self, attempt: int) -> float:
        """Full-jitter delay in [0, min(base * 2**attempt, max_delay)]."""
        cap = min(self.base_delay * (2**attempt), self.max_delay)
        if cap <= 0:
            return 0.0
        return self._rng.uniform(0.0, cap)

    def sleep_before_retry(self, attempt: int, sleep: Sleep) -> None:
        sleep(self.delay_for(attempt))
