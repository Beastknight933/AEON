"""Duplicate Payment and Purchase Request Anomaly Detector."""

import hashlib
import time
import threading
from typing import Dict, Tuple
from security_hardening.core.config import security_settings
from security_hardening.core.errors import SecurityHardeningError


class DuplicateTransactionError(SecurityHardeningError):
    def __init__(self, fingerprint: str, window_seconds: int):
        super().__init__(
            message="Duplicate transaction detected within cooldown window. Request rejected to prevent accidental double-spending.",
            code="DUPLICATE_TRANSACTION_DETECTED",
            details={"fingerprint": fingerprint, "window_seconds": window_seconds},
            status_code=409,
        )


class DuplicateTransactionDetector:
    """Detects rapid-fire identical purchase attempts from autonomous agents."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self._recent_requests: Dict[str, float] = {}  # fingerprint -> timestamp
        self.lock = threading.Lock()

    def generate_fingerprint(
        self,
        agent_id: str,
        item_description: str,
        category: str,
        amount_or_budget: str,
        currency: str,
    ) -> str:
        raw = f"{agent_id}:{item_description.strip().lower()}:{category.strip().lower()}:{amount_or_budget}:{currency.upper()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def check_and_record(
        self,
        agent_id: str,
        item_description: str,
        category: str,
        amount_or_budget: str,
        currency: str = "USD",
    ) -> str:
        fingerprint = self.generate_fingerprint(
            agent_id, item_description, category, amount_or_budget, currency
        )
        now = time.time()

        with self.lock:
            # Purge expired records
            cutoff = now - self.window_seconds
            self._recent_requests = {
                k: v for k, v in self._recent_requests.items() if v > cutoff
            }

            if fingerprint in self._recent_requests:
                last_time = self._recent_requests[fingerprint]
                if now - last_time < self.window_seconds:
                    raise DuplicateTransactionError(fingerprint, self.window_seconds)

            self._recent_requests[fingerprint] = now

        return fingerprint


duplicate_detector = DuplicateTransactionDetector(
    window_seconds=security_settings.DUPLICATE_TX_WINDOW_SECONDS
)

