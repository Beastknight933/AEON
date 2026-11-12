"""Multi-Tier In-Memory Token Bucket Rate Limiter with Lockout and Burstable Quotas."""

import time
import threading
from typing import Dict, Optional, Tuple
from security_hardening.core.config import security_settings
from security_hardening.core.errors import RateLimitExceededError


class TokenBucket:
    """Thread-safe Token Bucket implementation."""

    def __init__(self, capacity: float, replenish_rate: float):
        self.capacity = float(capacity)
        self.replenish_rate = float(replenish_rate)
        self.tokens = float(capacity)
        self.last_update = time.time()
        self.lock = threading.Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.replenish_rate)

            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False


class LockoutTracker:
    """Tracks failed authentication attempts with progressive cooldown."""

    def __init__(self, max_attempts: int = 5, lockout_seconds: int = 300):
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, Tuple[int, float]] = {}  # key -> (attempt_count, last_failure_time)
        self.lock = threading.Lock()

    def record_failure(self, key: str) -> bool:
        """Record failure. Returns True if key is now locked out."""
        with self.lock:
            now = time.time()
            count, last_time = self._failures.get(key, (0, 0.0))
            if now - last_time > self.lockout_seconds:
                count = 0  # reset after window
            count += 1
            self._failures[key] = (count, now)
            return count >= self.max_attempts

    def is_locked_out(self, key: str) -> Tuple[bool, int]:
        with self.lock:
            now = time.time()
            count, last_time = self._failures.get(key, (0, 0.0))
            if count >= self.max_attempts:
                elapsed = now - last_time
                if elapsed < self.lockout_seconds:
                    return True, int(self.lockout_seconds - elapsed)
                else:
                    self._failures.pop(key, None)
            return False, 0

    def record_success(self, key: str) -> None:
        with self.lock:
            self._failures.pop(key, None)


class MultiTierRateLimiter:
    """Manages separate rate-limit buckets for IPs, Agents, and Login endpoints."""

    def __init__(self):
        self._ip_buckets: Dict[str, TokenBucket] = {}
        self._agent_buckets: Dict[str, TokenBucket] = {}
        self._lockout_tracker = LockoutTracker(
            max_attempts=security_settings.AUTH_ATTEMPTS_MAX_BURST,
            lockout_seconds=security_settings.AUTH_ATTEMPTS_LOCKOUT_SECONDS,
        )
        self.lock = threading.Lock()

    def check_ip_limit(self, client_ip: str) -> None:
        """Check per-IP request velocity."""
        if not security_settings.RATE_LIMIT_ENABLED:
            return

        with self.lock:
            if client_ip not in self._ip_buckets:
                self._ip_buckets[client_ip] = TokenBucket(
                    capacity=security_settings.RATE_LIMIT_PER_IP_BURST,
                    replenish_rate=security_settings.RATE_LIMIT_PER_IP_REPLENISH,
                )
            bucket = self._ip_buckets[client_ip]

        if not bucket.consume(1.0):
            raise RateLimitExceededError(
                message=f"Rate limit exceeded for IP {client_ip}. Please slow down.",
                retry_after=5,
            )

    def check_agent_limit(self, agent_id_or_prefix: str) -> None:
        """Check per-agent request velocity."""
        if not security_settings.RATE_LIMIT_ENABLED:
            return

        with self.lock:
            if agent_id_or_prefix not in self._agent_buckets:
                self._agent_buckets[agent_id_or_prefix] = TokenBucket(
                    capacity=security_settings.RATE_LIMIT_AGENT_BURST,
                    replenish_rate=security_settings.RATE_LIMIT_AGENT_REPLENISH,
                )
            bucket = self._agent_buckets[agent_id_or_prefix]

        if not bucket.consume(1.0):
            raise RateLimitExceededError(
                message=f"Rate limit exceeded for Agent {agent_id_or_prefix}.",
                retry_after=5,
            )

    def check_auth_lockout(self, identifier: str) -> None:
        """Check if email or IP is currently locked out due to credential stuffing."""
        locked, remaining = self._lockout_tracker.is_locked_out(identifier)
        if locked:
            raise RateLimitExceededError(
                message=f"Account temporarily locked due to repeated authentication failures. Try again in {remaining}s.",
                retry_after=remaining,
            )

    def record_auth_failure(self, identifier: str) -> None:
        self._lockout_tracker.record_failure(identifier)

    def record_auth_success(self, identifier: str) -> None:
        self._lockout_tracker.record_success(identifier)


rate_limiter = MultiTierRateLimiter()

