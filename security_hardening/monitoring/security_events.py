"""Structured Security Event Logger and Non-Blocking Event Bus."""

from __future__ import annotations

import datetime
from collections import deque
from typing import Any, Dict, List, Optional
from app.core.logging import get_logger
from security_hardening.core.constants import SecurityEventType, SecuritySeverity
from security_hardening.monitoring.redactor import SensitiveDataRedactor

logger = get_logger("aeon.security_events")


class SecurityEventRecord:
    def __init__(
        self,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        message: str,
        actor_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.timestamp = datetime.datetime.now(datetime.timezone.utc)
        self.event_type = event_type
        self.severity = severity
        self.message = message
        self.actor_id = actor_id
        self.organization_id = organization_id
        self.ip_address = ip_address
        self.details = SensitiveDataRedactor.redact_data(details or {})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "actor_id": self.actor_id,
            "organization_id": self.organization_id,
            "ip_address": self.ip_address,
            "details": self.details,
        }


class SecurityEventBus:
    """Thread-safe ring buffer for structured security event observability."""

    def __init__(self, buffer_size: int = 500):
        self._buffer: deque = deque(maxlen=buffer_size)

    def emit(
        self,
        event_type: SecurityEventType,
        severity: SecuritySeverity,
        message: str,
        actor_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> SecurityEventRecord:
        record = SecurityEventRecord(
            event_type=event_type,
            severity=severity,
            message=message,
            actor_id=actor_id,
            organization_id=organization_id,
            ip_address=ip_address,
            details=details,
        )
        self._buffer.append(record)

        # Standard log emission
        log_msg = f"[{record.severity.value}] {record.event_type.value}: {record.message}"
        if record.severity in (SecuritySeverity.HIGH, SecuritySeverity.CRITICAL):
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return record

    def list_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        events = list(self._buffer)
        return [e.to_dict() for e in reversed(events[-limit:])]


security_event_bus = SecurityEventBus()

