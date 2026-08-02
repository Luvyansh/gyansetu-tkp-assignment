"""Per-model async rate limiting for Gemini free-tier RPM caps."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from backend.app.logging_config import get_logger

logger = get_logger(__name__)

# Free-tier GenerateRequestsPerMinutePerProjectPerModel was observed at 5 for
# gemini-3.5-flash. Stay under that with headroom; lite is typically higher.
_DEFAULT_MAX_PER_MINUTE = 4
_LITE_MAX_PER_MINUTE = 8
_DEFAULT_CONCURRENCY = 1
_LITE_CONCURRENCY = 2


class ModelRateLimiter:
    """Sliding-window RPM limiter + concurrency semaphore, keyed by model id."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._sems: dict[str, asyncio.Semaphore] = {}

    def _max_per_minute(self, model: str) -> int:
        return _LITE_MAX_PER_MINUTE if "lite" in model.lower() else _DEFAULT_MAX_PER_MINUTE

    def _concurrency(self, model: str) -> int:
        return _LITE_CONCURRENCY if "lite" in model.lower() else _DEFAULT_CONCURRENCY

    def _semaphore(self, model: str) -> asyncio.Semaphore:
        if model not in self._sems:
            self._sems[model] = asyncio.Semaphore(self._concurrency(model))
        return self._sems[model]

    async def acquire(self, model: str) -> None:
        """Block until a request slot is available for ``model``."""
        sem = self._semaphore(model)
        await sem.acquire()
        try:
            await self._wait_for_rpm_slot(model)
        except BaseException:
            sem.release()
            raise

    def release(self, model: str) -> None:
        self._semaphore(model).release()

    async def _wait_for_rpm_slot(self, model: str) -> None:
        limit = self._max_per_minute(model)
        lock = self._locks[model]
        while True:
            async with lock:
                now = time.monotonic()
                window = self._windows[model]
                while window and now - window[0] >= 60.0:
                    window.popleft()
                if len(window) < limit:
                    window.append(now)
                    return
                wait_for = 60.0 - (now - window[0]) + 0.05
            logger.info(
                "gemini_rpm_throttle",
                model=model,
                wait_s=round(wait_for, 2),
                limit_per_minute=limit,
            )
            await asyncio.sleep(max(wait_for, 0.05))


_limiter = ModelRateLimiter()


class RateLimited:
    """Async context manager: ``async with RateLimited(model): ...``."""

    def __init__(self, model: str) -> None:
        self._model = model

    async def __aenter__(self) -> None:
        await _limiter.acquire(self._model)
        return None

    async def __aexit__(self, *args: object) -> None:
        _limiter.release(self._model)


# Back-compat alias used at call sites as a context-manager factory name.
rate_limited = RateLimited
