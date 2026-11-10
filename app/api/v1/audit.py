import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.audit import AuditEventResponse
from app.schemas.common import PaginatedResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("", response_model=PaginatedResponse[AuditEventResponse])
async def list_audit_trail(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    actor_type: Optional[str] = Query(None, description="Filter by actor type (USER, AGENT, SYSTEM, WEBHOOK)"),
    actor_id: Optional[str] = Query(None, description="Filter by actor identifier"),
    action: Optional[str] = Query(None, description="Filter by action code"),
    entity_type: Optional[str] = Query(None, description="Filter by target entity type"),
    entity_id: Optional[str] = Query(None, description="Filter by target entity ID"),
    start_date: Optional[datetime.datetime] = Query(None, description="Filter events on or after UTC datetime"),
    end_date: Optional[datetime.datetime] = Query(None, description="Filter events on or before UTC datetime"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Query the immutable, append-only audit trail with filtering by actor, action, entity, date range, pagination, and sorting.
    """
    _, _, org = context
    service = AuditService(db)
    return await service.list_events_paginated(
        organization_id=org.id,
        page=page,
        page_size=page_size,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )
