import datetime
import decimal
import uuid
from typing import Any, Dict, Optional, Tuple
import httpx

from app.core.config import settings
from app.core.errors import PaymentError
from app.core.logging import get_logger
from app.integrations.paypal.schemas import (
    PayPalCaptureResponse,
    PayPalLink,
    PayPalOrderResponse,
)

logger = get_logger("aeon.paypal")


class PayPalClient:
    def __init__(
        self,
        client_id: str = settings.PAYPAL_CLIENT_ID,
        client_secret: str = settings.PAYPAL_CLIENT_SECRET,
        base_url: str = settings.PAYPAL_API_BASE_URL,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url.rstrip("/")
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime.datetime] = None

    @property
    def is_mock_mode(self) -> bool:
        return (
            self.client_id.startswith("mock_")
            or "mock" in self.client_id
            or settings.APP_ENV == "testing"
        )

    async def get_access_token(self) -> str:
        if self.is_mock_mode:
            return "mock_paypal_access_token_12345"

        now = datetime.datetime.now(datetime.timezone.utc)
        if self._access_token and self._token_expiry and now < self._token_expiry:
            return self._access_token

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self.base_url}/v1/oauth2/token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json", "Accept-Language": "en_US"},
            )
            if resp.status_code != 200:
                raise PaymentError(f"PayPal authentication failed: {resp.text}")

            data = resp.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = now + datetime.timedelta(seconds=expires_in - 60)
            return self._access_token

    async def create_order(
        self,
        purchase_id: uuid.UUID,
        amount: decimal.Decimal,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
    ) -> PayPalOrderResponse:
        """
        Create PayPal Order with intent=CAPTURE.
        """
        if self.is_mock_mode:
            order_id = f"ORDER-MOCK-{uuid.uuid4().hex[:12].upper()}"
            approval_url = f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"
            return PayPalOrderResponse(
                id=order_id,
                status="CREATED",
                links=[
                    PayPalLink(href=approval_url, rel="approve", method="GET"),
                    PayPalLink(href=f"{self.base_url}/v2/checkout/orders/{order_id}/capture", rel="capture", method="POST"),
                ],
            )

        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": str(purchase_id),
                    "amount": {
                        "currency_code": currency,
                        "value": f"{amount:.2f}",
                    },
                    "description": f"AEON Purchase {purchase_id}",
                }
            ],
            "application_context": {
                "return_url": settings.PAYPAL_RETURN_URL,
                "cancel_url": settings.PAYPAL_CANCEL_URL,
                "user_action": "PAY_NOW",
            },
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{self.base_url}/v2/checkout/orders",
                json=payload,
                headers=headers,
            )
            if resp.status_code not in (200, 201):
                raise PaymentError(f"PayPal create order failed: {resp.text}")

            data = resp.json()
            return PayPalOrderResponse.model_validate(data)

    async def capture_order(
        self,
        order_id: str,
        idempotency_key: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        """
        Capture an approved PayPal Order.
        """
        if self.is_mock_mode:
            capture_id = f"CAPTURE-MOCK-{uuid.uuid4().hex[:12].upper()}"
            return PayPalCaptureResponse(
                id=capture_id,
                status="COMPLETED",
                create_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["PayPal-Request-Id"] = idempotency_key

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers=headers,
            )
            if resp.status_code not in (200, 201):
                raise PaymentError(f"PayPal capture order failed: {resp.text}")

            data = resp.json()
            capture_units = data.get("purchase_units", [{}])[0].get("payments", {}).get("captures", [])
            if capture_units:
                cap = capture_units[0]
                return PayPalCaptureResponse(
                    id=cap.get("id", order_id),
                    status=cap.get("status", "COMPLETED"),
                )
            return PayPalCaptureResponse(
                id=data.get("id", order_id),
                status=data.get("status", "COMPLETED"),
            )


paypal_client = PayPalClient()
