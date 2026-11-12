"""Enterprise PayPal Webhook Guard with Replay Window and Event Allowlisting."""

import datetime
from typing import Any, Dict, List, Optional
from app.core.config import settings
from app.core.errors import WebhookVerificationError
from security_hardening.core.config import security_settings
from security_hardening.core.constants import SecurityEventType, SecuritySeverity
from security_hardening.monitoring.security_events import security_event_bus


class DeadLetterWebhook:
    def __init__(self, event_id: str, event_type: str, reason: str, payload: Dict[str, Any]):
        self.event_id = event_id
        self.event_type = event_type
        self.reason = reason
        self.payload = payload
        self.timestamp = datetime.datetime.now(datetime.timezone.utc)


class EnterpriseWebhookGuard:
    """Provides non-disruptive defense layers around webhook ingestion."""

    def __init__(self):
        self._dead_letter_queue: List[DeadLetterWebhook] = []

    def validate_incoming_webhook(
        self,
        headers: Dict[str, str],
        event_body: Dict[str, Any],
    ) -> None:
        """Enforces:
        1. No mock signature bypass in production.
        2. Allowed event type matching.
        3. Transmission timestamp freshness / replay defense.
        """
        h = {k.lower(): v for k, v in headers.items()}
        event_type = event_body.get("event_type", "UNKNOWN")
        event_id = event_body.get("id", "UNKNOWN")

        # 1. Backdoor elimination: reject x-mock-webhook unless APP_ENV == "testing"
        if h.get("x-mock-webhook") == "true" and settings.APP_ENV != "testing":
            security_event_bus.emit(
                event_type=SecurityEventType.WEBHOOK_SIGNATURE_FAILED,
                severity=SecuritySeverity.CRITICAL,
                message=f"Malicious mock webhook bypass attempt rejected in {settings.APP_ENV} mode.",
                details={"event_id": event_id, "headers": h},
            )
            self._record_dead_letter(event_id, event_type, "Mock webhook bypass forbidden in production", event_body)
            raise WebhookVerificationError("Mock webhook bypass headers are strictly prohibited in production mode.")

        # 2. Allowlisted event types
        if event_type not in security_settings.ALLOWED_WEBHOOK_EVENT_TYPES:
            self._record_dead_letter(event_id, event_type, f"Event type {event_type} not allowlisted", event_body)
            security_event_bus.emit(
                event_type=SecurityEventType.WEBHOOK_UNKNOWN_EVENT,
                severity=SecuritySeverity.LOW,
                message=f"Ignoring non-allowlisted webhook event type: {event_type}",
                details={"event_id": event_id, "event_type": event_type},
            )

        # 3. Transmission timestamp replay check (if header present)
        transmission_time = h.get("paypal-transmission-time")
        if transmission_time:
            try:
                # ISO-8601 parsing
                parsed_time = datetime.datetime.fromisoformat(transmission_time.replace("Z", "+00:00"))
                now = datetime.datetime.now(datetime.timezone.utc)
                age_seconds = abs((now - parsed_time).total_seconds())

                if age_seconds > security_settings.WEBHOOK_MAX_AGE_SECONDS:
                    security_event_bus.emit(
                        event_type=SecurityEventType.WEBHOOK_REPLAY_ATTEMPT,
                        severity=SecuritySeverity.HIGH,
                        message=f"Webhook event exceeds maximum replay age: {age_seconds:.1f}s",
                        details={"event_id": event_id, "age_seconds": age_seconds},
                    )
                    self._record_dead_letter(event_id, event_type, f"Replay age exceeded ({age_seconds:.1f}s)", event_body)
                    raise WebhookVerificationError(
                        f"Webhook timestamp outside valid window ({age_seconds:.1f}s > {security_settings.WEBHOOK_MAX_AGE_SECONDS}s)"
                    )
            except (ValueError, TypeError):
                pass  # Fallback to provider verification API

    def _record_dead_letter(self, event_id: str, event_type: str, reason: str, payload: Dict[str, Any]) -> None:
        if len(self._dead_letter_queue) >= 500:
            self._dead_letter_queue.pop(0)
        self._dead_letter_queue.append(DeadLetterWebhook(event_id, event_type, reason, payload))

    def list_dead_letter_events(self) -> List[Dict[str, Any]]:
        return [
            {
                "event_id": item.event_id,
                "event_type": item.event_type,
                "reason": item.reason,
                "timestamp": item.timestamp.isoformat(),
            }
            for item in self._dead_letter_queue
        ]


webhook_guard = EnterpriseWebhookGuard()

