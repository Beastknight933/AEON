import datetime
import decimal
import uuid
from typing import Optional
from pydantic import BaseModel, Field
from app.core.constants import PaymentStatus


class PaymentOrderCreateRequest(BaseModel):
    purchase_request_id: uuid.UUID


class PaymentOrderCreateResponse(BaseModel):
    payment_attempt_id: uuid.UUID
    purchase_request_id: uuid.UUID
    provider_order_id: str
    amount: decimal.Decimal
    currency: str
    status: PaymentStatus
    approval_url: Optional[str]
    created_at: datetime.datetime


class PaymentCaptureRequest(BaseModel):
    provider_order_id: str


class PaymentCaptureResponse(BaseModel):
    payment_attempt_id: uuid.UUID
    purchase_request_id: uuid.UUID
    provider_capture_id: str
    amount: decimal.Decimal
    currency: str
    status: PaymentStatus
    transaction_id: Optional[uuid.UUID]
    completed_at: datetime.datetime


class PaymentStatusResponse(BaseModel):
    id: uuid.UUID
    purchase_request_id: uuid.UUID
    provider: str
    status: PaymentStatus
    amount: decimal.Decimal
    currency: str
    provider_order_id: Optional[str]
    provider_capture_id: Optional[str]
    approval_url: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
