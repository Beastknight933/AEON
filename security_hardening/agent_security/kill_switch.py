"""Emergency Agent Kill-Switch and Global Purchasing Freeze."""

from __future__ import annotations

import datetime
import threading
from typing import Any, Dict, Optional, Set, Tuple
from security_hardening.core.errors import AgentKillSwitchError


class AgentKillSwitch:
    """Provides instant circuit-breaker mechanisms to freeze rogue or compromised AI agents."""

    def __init__(self):
        self._global_freeze: bool = False
        self._frozen_agents: Dict[str, Dict[str, Any]] = {}  # agent_id -> {reason, frozen_by, timestamp}
        self.lock = threading.Lock()

    def is_agent_frozen(self, agent_id: str) -> Tuple[bool, Optional[str]]:
        """Check if an agent is currently barred from executing transactions."""
        with self.lock:
            if self._global_freeze:
                return True, "Global emergency purchasing freeze is active across all autonomous agents."

            if agent_id in self._frozen_agents:
                reason = self._frozen_agents[agent_id].get("reason", "Agent suspended by administrator kill switch.")
                return True, reason

            return False, None

    def assert_agent_active(self, agent_id: str) -> None:
        """Raise AgentKillSwitchError if agent is frozen."""
        frozen, reason = self.is_agent_frozen(agent_id)
        if frozen:
            raise AgentKillSwitchError(agent_id=agent_id, reason=reason)

    def freeze_agent(self, agent_id: str, reason: str, frozen_by: str) -> None:
        """Freeze a specific autonomous agent."""
        with self.lock:
            self._frozen_agents[agent_id] = {
                "reason": reason,
                "frozen_by": frozen_by,
                "timestamp": datetime.datetime.now(datetime.timezone.utc),
            }

    def unfreeze_agent(self, agent_id: str) -> bool:
        """Restore an agent to active execution."""
        with self.lock:
            return self._frozen_agents.pop(agent_id, None) is not None

    def activate_global_freeze(self, reason: str, frozen_by: str) -> None:
        """Engage global emergency kill switch halting all agent purchasing."""
        with self.lock:
            self._global_freeze = True

    def deactivate_global_freeze(self) -> None:
        """Disengage global emergency freeze."""
        with self.lock:
            self._global_freeze = False

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "global_freeze": self._global_freeze,
                "frozen_agent_count": len(self._frozen_agents),
                "frozen_agents": list(self._frozen_agents.keys()),
            }


agent_kill_switch = AgentKillSwitch()

