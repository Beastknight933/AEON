import datetime
import decimal
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, model_validator


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
    expires_at: Optional[datetime.datetime] = None

    @model_validator(mode="after")
    def validate_totals_and_currency(self) -> "NormalizedQuote":
        expected_total = self.unit_price * self.quantity
        if abs(self.total_amount - expected_total) > decimal.Decimal("0.01"):
            raise ValueError(
                f"total_amount ({self.total_amount}) does not match unit_price * quantity ({expected_total})"
            )
        if self.currency.upper() != "USD":
            raise ValueError(f"Unsupported currency '{self.currency}': only USD is supported")
        return self

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.expires_at < now
