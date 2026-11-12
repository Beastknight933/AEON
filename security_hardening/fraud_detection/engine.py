"""Heuristic Fraud Scoring and Risk Assessment Engine."""

from __future__ import annotations

import decimal
import datetime
from typing import Any, Dict, List, Optional, Tuple
from security_hardening.core.constants import SecuritySeverity


class FraudScoreResult:
    def __init__(
        self,
        score: float,
        severity: SecuritySeverity,
        risk_flags: List[str],
        recommended_action: str,  # "ALLOW", "FLAG_FOR_REVIEW", "BLOCK"
    ):
        self.score = round(score, 1)
        self.severity = severity
        self.risk_flags = risk_flags
        self.recommended_action = recommended_action

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "severity": self.severity.value,
            "risk_flags": self.risk_flags,
            "recommended_action": self.recommended_action,
        }


class FraudDetectionEngine:
    """Evaluates transactional risk based on velocity, amount anomalies, and supplier patterns."""

    @classmethod
    def evaluate_purchase(
        cls,
        amount: decimal.Decimal,
        max_budget: decimal.Decimal,
        supplier_code: str,
        recent_tx_count_last_hour: int = 0,
        historical_avg_amount: Optional[decimal.Decimal] = None,
    ) -> FraudScoreResult:
        score = 0.0
        flags = []

        # 1. High-utilization factor (request consumes >= 95% of maximum allowed budget)
        if max_budget > decimal.Decimal("0.00"):
            ratio = float(amount / max_budget)
            if ratio >= 0.95:
                score += 20.0
                flags.append("NEAR_MAXIMUM_BUDGET_UTILIZATION")

        # 2. Velocity spike factor
        if recent_tx_count_last_hour > 20:
            score += 35.0
            flags.append("HIGH_VELOCITY_SUBMISSIONS")
        elif recent_tx_count_last_hour > 10:
            score += 15.0
            flags.append("MODERATE_VELOCITY_SUBMISSIONS")

        # 3. Sudden amount jump relative to historical baseline
        if historical_avg_amount and historical_avg_amount > decimal.Decimal("0.00"):
            multiplier = float(amount / historical_avg_amount)
            if multiplier >= 5.0:
                score += 30.0
                flags.append("ABNORMAL_AMOUNT_SPIKE")
            elif multiplier >= 2.5:
                score += 15.0
                flags.append("ELEVATED_AMOUNT_DEVIATION")

        # 4. Off-hours purchasing check (midnight to 5 AM UTC)
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        if 0 <= now_utc.hour <= 4:
            score += 10.0
            flags.append("OFF_HOURS_EXECUTION")

        score = min(100.0, score)

        if score >= 70.0:
            severity = SecuritySeverity.HIGH
            action = "FLAG_FOR_REVIEW"
        elif score >= 40.0:
            severity = SecuritySeverity.MEDIUM
            action = "FLAG_FOR_REVIEW"
        else:
            severity = SecuritySeverity.LOW
            action = "ALLOW"

        return FraudScoreResult(score, severity, flags, action)


fraud_detection_engine = FraudDetectionEngine()

