import datetime
import decimal
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.core.constants import TransactionStatus, TransactionType


class TransactionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    purchase_request_id: uuid.UUID
    budget_id: Optional[uuid.UUID]
    type: TransactionType
    status: TransactionStatus
    amount: decimal.Decimal
    currency: str
    provider_transaction_id: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class PurchaseSummaryForTransaction(BaseModel):
    id: uuid.UUID
    item_description: str
    category: str
    status: str
    fulfillment_status: str
    agent_id: uuid.UUID
    agent_name: str
    supplier_name: Optional[str] = None
    unit_price: Optional[decimal.Decimal] = None
    quantity: Optional[int] = None


class PaymentAttemptSummaryForTransaction(BaseModel):
    id: uuid.UUID
    provider: str
    status: str
    provider_order_id: Optional[str] = None
    provider_capture_id: Optional[str] = None
    approval_url: Optional[str] = None


class TransactionDetailResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    purchase_request_id: uuid.UUID
    budget_id: Optional[uuid.UUID]
    type: TransactionType
    status: TransactionStatus
    amount: decimal.Decimal
    currency: str
    provider_transaction_id: Optional[str]
    created_at: datetime.datetime
    updated_at: datetime.datetime
    purchase_request: Optional[PurchaseSummaryForTransaction] = None
    payment_attempt: Optional[PaymentAttemptSummaryForTransaction] = None

    class Config:
        from_attributes = True


class TimelineEventItem(BaseModel):
    id: uuid.UUID
    timestamp: datetime.datetime
    action: str
    actor_type: str
    actor_id: Optional[str]
    description: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class TransactionTimelineResponse(BaseModel):
    transaction_id: uuid.UUID
    purchase_request_id: uuid.UUID
    events: List[TimelineEventItem]


class TransactionReceiptResponse(BaseModel):
    receipt_number: str
    issued_at: datetime.datetime
    transaction_id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    purchase_request_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    item_description: str
    category: str
    supplier_name: str
    quantity: int
    unit_price: decimal.Decimal
    total_amount: decimal.Decimal
    currency: str = "USD"
    status: TransactionStatus
    payment_method: str = "PayPal Orders v2 (CAPTURE)"
    provider_capture_id: Optional[str] = None
    provider_order_id: Optional[str] = None
    policy_name: Optional[str] = None


class ReconciliationResponse(BaseModel):
    total_transactions_count: int
    total_spent_amount: decimal.Decimal
    total_refunded_amount: decimal.Decimal
    currency: str
    pending_count: int
    settled_count: int
    failed_count: int
    reconciled_at: datetime.datetime
