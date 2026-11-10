import datetime
import math
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventResponse
from app.schemas.common import PaginatedResponse


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_event(
        self,
        organization_id: Optional[uuid.UUID],
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        entity_type: str,
        entity_id: Optional[str],
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        event = AuditEvent(
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata_json or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events_paginated(
        self,
        organization_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        actor_type: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> PaginatedResponse[AuditEventResponse]:
        """
        Query the immutable, append-only audit trail with filtering, sorting, and pagination.
        """
        stmt = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        count_stmt = select(func.count(AuditEvent.id)).where(AuditEvent.organization_id == organization_id)

        if actor_type:
            stmt = stmt.where(AuditEvent.actor_type == actor_type)
            count_stmt = count_stmt.where(AuditEvent.actor_type == actor_type)
        if actor_id:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
            count_stmt = count_stmt.where(AuditEvent.actor_id == actor_id)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
            count_stmt = count_stmt.where(AuditEvent.action == action)
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)
            count_stmt = count_stmt.where(AuditEvent.entity_type == entity_type)
        if entity_id:
            stmt = stmt.where(AuditEvent.entity_id == entity_id)
            count_stmt = count_stmt.where(AuditEvent.entity_id == entity_id)
        if start_date:
            stmt = stmt.where(AuditEvent.created_at >= start_date)
            count_stmt = count_stmt.where(AuditEvent.created_at >= start_date)
        if end_date:
            stmt = stmt.where(AuditEvent.created_at <= end_date)
            count_stmt = count_stmt.where(AuditEvent.created_at <= end_date)

        total = (await self.session.scalar(count_stmt)) or 0

        sort_col = getattr(AuditEvent, sort_by, AuditEvent.created_at)
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_col.asc())
        else:
            stmt = stmt.order_by(sort_col.desc())

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        events = list((await self.session.scalars(stmt)).all())
        items = [AuditEventResponse.model_validate(e) for e in events]
        total_pages = math.ceil(total / page_size) if page_size > 0 else 1

        return PaginatedResponse[AuditEventResponse](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def list_events(
        self,
        organization_id: uuid.UUID,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        entity_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[AuditEventResponse]:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
        )
        if actor_id:
            stmt = stmt.where(AuditEvent.actor_id == actor_id)
        if action:
            stmt = stmt.where(AuditEvent.action == action)
        if entity_type:
            stmt = stmt.where(AuditEvent.entity_type == entity_type)

        stmt = stmt.order_by(AuditEvent.created_at.desc()).offset(skip).limit(limit)
        events = list((await self.session.scalars(stmt)).all())
        return [AuditEventResponse.model_validate(e) for e in events]
