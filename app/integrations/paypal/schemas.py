import decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PayPalAmount(BaseModel):
    currency_code: str = "USD"
    value: str


class PayPalPurchaseUnit(BaseModel):
    reference_id: Optional[str] = None
    amount: PayPalAmount
    description: Optional[str] = None


class PayPalOrderCreatePayload(BaseModel):
    intent: str = "CAPTURE"
    purchase_units: List[PayPalPurchaseUnit]
    application_context: Dict[str, Any] = Field(default_factory=dict)


class PayPalLink(BaseModel):
    href: str
    rel: str
    method: str


class PayPalOrderResponse(BaseModel):
    id: str
    status: str
    links: List[PayPalLink] = Field(default_factory=list)


class PayPalCaptureResponse(BaseModel):
    id: str
    status: str
    amount: Optional[PayPalAmount] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None
