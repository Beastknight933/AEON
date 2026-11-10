import datetime
import decimal
import uuid
from typing import List, Optional
from pydantic import BaseModel
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


class ReconciliationResponse(BaseModel):
    total_transactions_count: int
    total_spent_amount: decimal.Decimal
    total_refunded_amount: decimal.Decimal
    currency: str
    pending_count: int
    settled_count: int
    failed_count: int
    reconciled_at: datetime.datetime
