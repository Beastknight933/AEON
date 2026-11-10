import datetime
import uuid
from typing import Any, Dict, Optional
from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    organization_id: Optional[uuid.UUID]
    actor_type: str
    actor_id: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    metadata_json: Dict[str, Any]
    created_at: datetime.datetime

    class Config:
        from_attributes = True
