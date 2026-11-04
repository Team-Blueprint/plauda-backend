"""In-process sliding-window rate limiting for expensive public chat turns.

Single-process by design for v1, matching the SSE hub. Replace with Redis/Postgres when the API
runs on more than one instance.
"""

import math
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitCheck:
    scope: str
    key: str
    limit: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    scope: str | None = None
    retry_after: int = 0


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = {}

    def consume(
        self,
        checks: list[RateLimitCheck],
        *,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitResult:
        if window_seconds <= 0:
            return RateLimitResult(allowed=True)
        now = time.monotonic() if now is None else now
        cutoff = now - window_seconds

        active: list[tuple[RateLimitCheck, deque[float]]] = []
        for check in checks:
            if check.limit <= 0:
                continue
            events = self._events.setdefault((check.scope, check.key), deque())
            while events and events[0] <= cutoff:
                events.popleft()
            active.append((check, events))

        for check, events in active:
            if len(events) >= check.limit:
                retry_after = max(1, math.ceil(window_seconds - (now - events[0])))
                return RateLimitResult(
                    allowed=False,
                    scope=check.scope,
                    retry_after=retry_after,
                )

        for _check, events in active:
            events.append(now)
        return RateLimitResult(allowed=True)

    def reset(self) -> None:
        self._events.clear()


chat_turn_limiter = SlidingWindowLimiter()
