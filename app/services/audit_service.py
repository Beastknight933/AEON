import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditEvent
from app.schemas.audit import AuditEventResponse


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
