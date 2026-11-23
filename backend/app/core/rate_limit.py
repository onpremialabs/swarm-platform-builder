"""In-memory throttling for authentication endpoints.

Protects ``/auth/login`` and ``/auth/register`` against brute-force and
credential-stuffing attacks with two complementary controls:

* **Sliding-window rate limiting** per client identifier (IP) and action, so a
  single source cannot hammer the endpoints.
* **Account lockout** that temporarily blocks an account after a configurable
  number of consecutive failed logins, regardless of the source IP (defends
  against distributed credential stuffing against one account).

State is process-local (no external dependency). This is sufficient for a
single-worker deployment and for CI; a multi-worker/replicated production
deployment should back these stores with a shared store such as Redis. The
public helpers below intentionally read their thresholds from the caller so the
limits stay configurable (``app.core.config.settings``) and testable.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


class SlidingWindowCounter:
    """Counts attempts per key inside a moving time window.

    Thread-safe. ``check_and_record`` returns ``None`` when the attempt is
    allowed (and records it) or the number of seconds the caller should wait
    before retrying when the window is saturated.
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check_and_record(
        self,
        key: str,
        max_attempts: int,
        window_seconds: float,
        now: float | None = None,
    ) -> float | None:
        if max_attempts <= 0:
            return None  # limiter disabled
        now = time.monotonic() if now is None else now
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits.setdefault(key, [])
            # Drop timestamps that fell out of the window.
            bucket[:] = [ts for ts in bucket if ts > cutoff]
            if len(bucket) >= max_attempts:
                retry_after = window_seconds - (now - bucket[0])
                return max(retry_after, 1.0)
            bucket.append(now)
            return None

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


@dataclass
class _LockState:
    failures: int = 0
    locked_until: float = 0.0


class AccountLockoutTracker:
    """Tracks consecutive failed logins per account and locks it temporarily."""

    def __init__(self) -> None:
        self._state: dict[str, _LockState] = {}
        self._lock = threading.Lock()

    def locked_for(self, key: str, now: float | None = None) -> float | None:
        """Return remaining lock seconds if ``key`` is locked, else ``None``."""
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._state.get(key)
            if state and state.locked_until > now:
                return state.locked_until - now
            return None

    def record_failure(
        self,
        key: str,
        max_failed: int,
        lockout_seconds: float,
        now: float | None = None,
    ) -> bool:
        """Register a failed attempt. Returns ``True`` if it triggered a lock."""
        if max_failed <= 0:
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._state.setdefault(key, _LockState())
            # A previous lock that already expired resets the counter.
            if state.locked_until and state.locked_until <= now:
                state.failures = 0
                state.locked_until = 0.0
            state.failures += 1
            if state.failures >= max_failed:
                state.locked_until = now + lockout_seconds
                return True
            return False

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._state.clear()
            else:
                self._state.pop(key, None)


# ─── Process-wide singletons used by the auth router ──────────────────────────
login_ip_limiter = SlidingWindowCounter()
register_ip_limiter = SlidingWindowCounter()
#: Búsquedas de literatura (T22.11), por persona usuaria: cada una sale a APIs de terceros.
literature_search_limiter = SlidingWindowCounter()
account_lockout = AccountLockoutTracker()


def reset_auth_throttling() -> None:
    """Clear all throttling state (used by tests and on a clean startup)."""
    login_ip_limiter.reset()
    register_ip_limiter.reset()
    literature_search_limiter.reset()
    account_lockout.reset()
