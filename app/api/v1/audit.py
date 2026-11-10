from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.audit import AuditEventResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("", response_model=List[AuditEventResponse])
async def list_audit_trail(
    actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Query the immutable, append-only audit trail with filtering by actor, action, and entity type.
    """
    _, _, org = context
    service = AuditService(db)
    return await service.list_events(
        organization_id=org.id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        skip=skip,
        limit=limit,
    )
