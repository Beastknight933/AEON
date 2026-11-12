"""Fine-Grained Agent Permission Scopes."""

from typing import List, Set
from security_hardening.core.constants import AgentScope
from security_hardening.core.errors import SecurityHardeningError


class AgentScopeViolationError(SecurityHardeningError):
    def __init__(self, required_scope: str, held_scopes: List[str]):
        super().__init__(
            message=f"Agent lacks required permission scope '{required_scope}'. Held scopes: {held_scopes}",
            code="AGENT_INSUFFICIENT_SCOPE",
            details={"required_scope": required_scope, "held_scopes": held_scopes},
            status_code=403,
        )


class AgentScopeValidator:
    """Validates that calling agent possesses necessary permission scopes for an action."""

    DEFAULT_AGENT_SCOPES = [
        AgentScope.PROCUREMENT_SUBMIT.value,
        AgentScope.PROCUREMENT_READ.value,
        AgentScope.QUOTES_READ.value,
    ]

    @classmethod
    def verify_scope(cls, held_scopes: List[str], required_scope: str) -> None:
        """Verify that held_scopes satisfies required_scope (supports wildcard admin:*)."""
        held_set = set(held_scopes or cls.DEFAULT_AGENT_SCOPES)
        if AgentScope.ADMIN_ALL.value in held_set:
            return

        if required_scope not in held_set:
            raise AgentScopeViolationError(required_scope, held_scopes)

