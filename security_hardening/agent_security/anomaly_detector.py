"""Agent Behavioral Anomaly and Velocity Monitoring."""

import datetime
import time
import threading
from typing import Dict, List, Optional, Tuple
from security_hardening.core.config import security_settings


class AgentAnomalyDetector:
    """Tracks purchasing velocity and flags anomalies (velocity spikes, high-frequency ordering)."""

    def __init__(self, velocity_window_seconds: int = 60, max_velocity_per_window: int = 30):
        self.window = velocity_window_seconds
        self.max_velocity = max_velocity_per_window
        self._history: Dict[str, List[float]] = {}  # agent_id -> list of timestamps
        self.lock = threading.Lock()

    def record_and_evaluate(self, agent_id: str) -> Tuple[bool, Optional[str]]:
        """Record an action and return (is_anomalous, description)."""
        now = time.time()
        with self.lock:
            timestamps = self._history.get(agent_id, [])
            # Filter within current sliding window
            cutoff = now - self.window
            filtered = [t for t in timestamps if t > cutoff]
            filtered.append(now)
            self._history[agent_id] = filtered

            if len(filtered) > self.max_velocity:
                return True, (
                    f"Agent velocity anomaly: {len(filtered)} purchase submissions in "
                    f"{self.window}s (threshold: {self.max_velocity})"
                )

            return False, None


agent_anomaly_detector = AgentAnomalyDetector(
    velocity_window_seconds=60,
    max_velocity_per_window=security_settings.AGENT_MAX_ACTIONS_PER_MINUTE,
)

