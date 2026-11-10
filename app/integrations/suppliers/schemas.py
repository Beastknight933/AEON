import decimal
import uuid
from typing import Any, Dict
from pydantic import BaseModel, Field


class NormalizedQuote(BaseModel):
    supplier_code: str
    supplier_name: str
    item_id: str
    unit_price: decimal.Decimal = Field(..., gt=0)
    quantity: int = Field(1, ge=1)
    total_amount: decimal.Decimal = Field(..., gt=0)
    currency: str = "USD"
    estimated_delivery_days: int = Field(0, ge=0)
    reliability_score: decimal.Decimal = Field(decimal.Decimal("1.00"), ge=0, le=1)
    raw_data: Dict[str, Any] = Field(default_factory=dict)
