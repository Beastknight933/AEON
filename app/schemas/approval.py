import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from app.core.constants import ApprovalStatus


class ApprovalDecideRequest(BaseModel):
    decision: str = Field(..., pattern="^(APPROVE|REJECT)$")
    notes: Optional[str] = Field(None, max_length=1024)


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    purchase_request_id: uuid.UUID
    approver_id: Optional[uuid.UUID]
    status: ApprovalStatus
    notes: Optional[str]
    decided_at: Optional[datetime.datetime]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
