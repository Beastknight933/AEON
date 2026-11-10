import datetime
import decimal
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
    selected_quote_id: Optional[uuid.UUID] = None
    amount: decimal.Decimal
    currency: str
    policy_version: Optional[int] = None
    expires_at: Optional[datetime.datetime] = None
    approver_id: Optional[uuid.UUID] = None
    status: ApprovalStatus
    notes: Optional[str] = None
    decided_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class ApprovalDetailResponse(ApprovalResponse):
    item_description: Optional[str] = None
    category: Optional[str] = None
    supplier_name: Optional[str] = None
    is_expired: bool = False
