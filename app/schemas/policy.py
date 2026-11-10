import decimal
import datetime
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field


class PolicyVersionCreate(BaseModel):
    max_amount_per_transaction: decimal.Decimal = Field(..., gt=0)
    max_amount_per_day: decimal.Decimal = Field(..., gt=0)
    approval_threshold_amount: decimal.Decimal = Field(..., ge=0)
    allowed_suppliers: List[str] = Field(default_factory=list)
    allowed_currencies: List[str] = Field(default_factory=lambda: ["USD"])


class PolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    max_amount_per_transaction: decimal.Decimal = Field(..., gt=0)
    max_amount_per_day: decimal.Decimal = Field(..., gt=0)
    approval_threshold_amount: decimal.Decimal = Field(..., ge=0)
    allowed_suppliers: List[str] = Field(default_factory=list)
    allowed_currencies: List[str] = Field(default_factory=lambda: ["USD"])


class PolicyVersionResponse(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    version: int
    max_amount_per_transaction: decimal.Decimal
    max_amount_per_day: decimal.Decimal
    approval_threshold_amount: decimal.Decimal
    allowed_suppliers: List[str]
    allowed_currencies: List[str]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PolicyResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str]
    is_active: bool
    current_version: int
    created_at: datetime.datetime
    updated_at: datetime.datetime
    versions: List[PolicyVersionResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class PolicyAssignmentRequest(BaseModel):
    policy_id: uuid.UUID


class PolicyAssignmentResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    policy_id: uuid.UUID
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    reason_codes: List[str]
    policy_id: Optional[uuid.UUID] = None
    policy_version: Optional[int] = None
    approved_max_amount: Optional[decimal.Decimal] = None
    currency: str = "USD"


class PolicyEvaluationRequest(BaseModel):
    agent_id: uuid.UUID
    amount: decimal.Decimal = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)
    supplier_code: str = Field(..., min_length=1, max_length=64)
    daily_spent_and_reserved: Optional[decimal.Decimal] = Field(default=decimal.Decimal("0.00"), ge=0)
