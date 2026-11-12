"""Enterprise Security Hardening API Endpoints.

Mounted under prefix /api/v1/security without modifying or colliding with existing endpoints.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_and_membership, require_roles
from app.core.constants import UserRole
from app.models.organization import Membership, Organization, User
from security_hardening.agent_security.kill_switch import agent_kill_switch
from security_hardening.audit.tamper_evident import audit_chain
from security_hardening.authentication.mfa import totp_engine, RecoveryCodeManager
from security_hardening.authentication.passkeys import passkey_manager
from security_hardening.integrations.webhook_guard import webhook_guard
from security_hardening.monitoring.security_events import security_event_bus

security_router = APIRouter(prefix="/security", tags=["Enterprise Security Hardening"])


# --- Schemas ---

class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    recovery_codes: List[str]


class MFAVerifyRequest(BaseModel):
    secret: str
    code: str


class MFAVerifyResponse(BaseModel):
    verified: bool
    message: str


class KillSwitchStatusResponse(BaseModel):
    global_freeze: bool
    frozen_agent_count: int
    frozen_agents: List[str]


class AgentFreezeRequest(BaseModel):
    agent_id: str
    reason: str


class AuditChainVerificationResponse(BaseModel):
    is_valid: bool
    total_blocks_verified: int
    error: Optional[str] = None
    failed_sequence: Optional[int] = None


# --- Endpoints ---

@security_router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
):
    """Generate TOTP secret, provisioning URI, and emergency recovery codes for MFA enrollment."""
    user, _, _ = context
    secret = totp_engine.generate_secret()
    uri = totp_engine.generate_provisioning_uri(secret, account_name=user.email, issuer="AEON Control Plane")
    plain_codes, _ = RecoveryCodeManager.generate_recovery_codes(10)

    return MFASetupResponse(
        secret=secret,
        provisioning_uri=uri,
        recovery_codes=plain_codes,
    )


@security_router.post("/mfa/verify", response_model=MFAVerifyResponse)
async def verify_mfa_code(
    req: MFAVerifyRequest,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
):
    """Verify a TOTP code during enrollment or login."""
    is_valid = totp_engine.verify_code(req.secret, req.code)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired TOTP code",
        )
    return MFAVerifyResponse(verified=True, message="MFA code verified successfully.")


@security_router.get("/kill-switch/status", response_model=KillSwitchStatusResponse)
async def get_kill_switch_status(
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN, UserRole.APPROVER])),
):
    """Inspect current agent kill switch and global purchasing freeze status."""
    return KillSwitchStatusResponse(**agent_kill_switch.get_status())


@security_router.post("/kill-switch/freeze-agent", response_model=Dict[str, Any])
async def freeze_agent(
    req: AgentFreezeRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
):
    """Immediately freeze an autonomous AI agent to prevent all transactions."""
    user, _, _ = context
    agent_kill_switch.freeze_agent(req.agent_id, reason=req.reason, frozen_by=str(user.id))
    return {"status": "frozen", "agent_id": req.agent_id, "reason": req.reason}


@security_router.post("/kill-switch/unfreeze-agent", response_model=Dict[str, Any])
async def unfreeze_agent(
    agent_id: str,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
):
    """Restore a frozen autonomous AI agent."""
    restored = agent_kill_switch.unfreeze_agent(agent_id)
    return {"status": "restored" if restored else "not_found", "agent_id": agent_id}


@security_router.get("/audit/verify-chain", response_model=AuditChainVerificationResponse)
async def verify_audit_hash_chain(
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN, UserRole.APPROVER])),
):
    """Traverse and verify cryptographic hash chain integrity across all audit batches."""
    is_valid, error, failed_seq = audit_chain.verify_integrity()
    return AuditChainVerificationResponse(
        is_valid=is_valid,
        total_blocks_verified=len(audit_chain.blocks),
        error=error,
        failed_sequence=failed_seq,
    )


@security_router.get("/events", response_model=List[Dict[str, Any]])
async def list_security_events(
    limit: int = 50,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
):
    """View recent structured security events with sensitive data automatically redacted."""
    return security_event_bus.list_recent_events(limit=limit)


@security_router.get("/dead-letters", response_model=List[Dict[str, Any]])
async def list_dead_letter_webhooks(
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
):
    """View rejected, replayed, or non-allowlisted PayPal webhooks quarantined in the dead-letter queue."""
    return webhook_guard.list_dead_letter_events()

