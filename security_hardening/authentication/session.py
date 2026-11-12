"""Administrator session monitoring, fingerprinting, and revocation registry."""

import datetime
import uuid
from typing import Dict, List, Optional


class UserSession:
    def __init__(
        self,
        session_id: str,
        user_id: str,
        organization_id: str,
        ip_address: str,
        user_agent: str,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.organization_id = organization_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.created_at = datetime.datetime.now(datetime.timezone.utc)
        self.last_active_at = self.created_at
        self.is_active = True

    def touch(self) -> None:
        self.last_active_at = datetime.datetime.now(datetime.timezone.utc)


class SessionRegistry:
    """In-memory active session tracker with administrative inspection & termination."""

    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}

    def create_session(
        self,
        user_id: str,
        organization_id: str,
        ip_address: str,
        user_agent: str,
    ) -> UserSession:
        session_id = f"sess_{uuid.uuid4().hex}"
        session = UserSession(session_id, user_id, organization_id, ip_address, user_agent)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        session = self._sessions.get(session_id)
        if session and session.is_active:
            session.touch()
            return session
        return None

    def list_user_sessions(self, user_id: str) -> List[UserSession]:
        return [s for s in self._sessions.values() if s.user_id == user_id and s.is_active]

    def revoke_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session:
            session.is_active = False
            return True
        return False

    def revoke_all_for_user(self, user_id: str) -> int:
        count = 0
        for s in self._sessions.values():
            if s.user_id == user_id and s.is_active:
                s.is_active = False
                count += 1
        return count

    def detect_suspicious_activity(self, user_id: str, current_ip: str) -> bool:
        """Check if user is accessing concurrently from divergent IP addresses."""
        active_ips = {s.ip_address for s in self.list_user_sessions(user_id)}
        if len(active_ips) > 1 and current_ip not in active_ips:
            return True
        return False


session_registry = SessionRegistry()

