import datetime
import decimal
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from app.core.constants import ReservationStatus


class BudgetCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    allocated_amount: decimal.Decimal = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)
    agent_id: Optional[uuid.UUID] = None
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None


class BudgetUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=128)
    allocated_amount: Optional[decimal.Decimal] = Field(None, gt=0)
    is_active: Optional[bool] = None
    end_date: Optional[datetime.datetime] = None


class BudgetReservationCreateRequest(BaseModel):
    purchase_request_id: uuid.UUID
    amount: decimal.Decimal = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)


class BudgetResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    name: str
    currency: str
    allocated_amount: decimal.Decimal
    reserved_amount: decimal.Decimal
    spent_amount: decimal.Decimal
    available_amount: decimal.Decimal
    start_date: datetime.datetime
    end_date: Optional[datetime.datetime]
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class BudgetReservationResponse(BaseModel):
    id: uuid.UUID
    budget_id: uuid.UUID
    purchase_request_id: uuid.UUID
    amount: decimal.Decimal
    currency: str
    status: ReservationStatus
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
