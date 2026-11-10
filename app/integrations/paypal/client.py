import abc
import datetime
import decimal
import uuid
from typing import Any, Dict, List, Optional
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


class BasePayPalClient(abc.ABC):
    """
    Abstract interface for PayPal Orders v2 integration.
    """

    @abc.abstractmethod
    async def create_order(
        self,
        purchase_id: uuid.UUID,
        amount: decimal.Decimal,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
    ) -> PayPalOrderResponse:
        pass

    @abc.abstractmethod
    async def capture_order(
        self,
        order_id: str,
        idempotency_key: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        pass

    @abc.abstractmethod
    async def get_order(self, order_id: str) -> Dict[str, Any]:
        """
        Fetch authoritative order status and payment capture details from PayPal.
        """
        pass

    @abc.abstractmethod
    async def get_capture(self, capture_id: str) -> Dict[str, Any]:
        """
        Fetch authoritative capture status and details from PayPal.
        """
        pass


class PayPalClient(BasePayPalClient):
    """
    Production/Sandbox PayPal Orders v2 client.
    Handles OAuth2 token acquisition, caching, order creation (CAPTURE intent),
    and server-to-server capture with idempotency.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.client_id = client_id or settings.PAYPAL_CLIENT_ID
        self.client_secret = client_secret or settings.PAYPAL_CLIENT_SECRET
        self.base_url = (base_url or settings.PAYPAL_API_BASE_URL).rstrip("/")
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

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        if self.is_mock_mode:
            return {
                "id": order_id,
                "status": "COMPLETED",
                "purchase_units": [
                    {
                        "payments": {
                            "captures": [
                                {
                                    "id": f"CAPTURE-MOCK-{uuid.uuid4().hex[:8].upper()}",
                                    "status": "COMPLETED",
                                    "amount": {"value": "100.00", "currency_code": "USD"},
                                }
                            ]
                        }
                    }
                ],
            }

        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/v2/checkout/orders/{order_id}", headers=headers)
            if resp.status_code != 200:
                raise PaymentError(f"PayPal get_order failed: {resp.text}")
            return resp.json()

    async def get_capture(self, capture_id: str) -> Dict[str, Any]:
        if self.is_mock_mode:
            return {
                "id": capture_id,
                "status": "COMPLETED",
                "amount": {"value": "100.00", "currency_code": "USD"},
            }

        token = await self.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{self.base_url}/v2/payments/captures/{capture_id}", headers=headers)
            if resp.status_code != 200:
                raise PaymentError(f"PayPal get_capture failed: {resp.text}")
            return resp.json()


class MockPayPalClient(BasePayPalClient):
    """
    Configurable Mock PayPal client for unit and integration testing.
    Can simulate order creation, successful capture, network timeouts,
    declined captures, authoritative reconciliation, and inspect called arguments.
    """

    def __init__(
        self,
        should_fail_create: bool = False,
        should_fail_capture: bool = False,
        should_timeout_capture: bool = False,
        capture_status: str = "COMPLETED",
        default_order_status: str = "COMPLETED",
    ):
        self.should_fail_create = should_fail_create
        self.should_fail_capture = should_fail_capture
        self.should_timeout_capture = should_timeout_capture
        self.capture_status = capture_status
        self.default_order_status = default_order_status
        self.create_order_calls: List[Dict[str, Any]] = []
        self.capture_order_calls: List[Dict[str, Any]] = []
        self.get_order_calls: List[Dict[str, Any]] = []
        self.mock_orders: Dict[str, Dict[str, Any]] = {}

    def set_mock_order(
        self,
        order_id: str,
        status: str,
        capture_id: Optional[str] = None,
        capture_status: Optional[str] = None,
        amount: str = "100.00",
        currency: str = "USD",
    ) -> None:
        captures = []
        if capture_id or capture_status:
            captures.append({
                "id": capture_id or f"CAPTURE-MOCK-{uuid.uuid4().hex[:8].upper()}",
                "status": capture_status or status,
                "amount": {"value": amount, "currency_code": currency},
            })
        self.mock_orders[order_id] = {
            "id": order_id,
            "status": status,
            "purchase_units": [
                {
                    "payments": {
                        "captures": captures,
                    }
                }
            ],
        }

    async def create_order(
        self,
        purchase_id: uuid.UUID,
        amount: decimal.Decimal,
        currency: str = "USD",
        idempotency_key: Optional[str] = None,
    ) -> PayPalOrderResponse:
        self.create_order_calls.append({
            "purchase_id": purchase_id,
            "amount": amount,
            "currency": currency,
            "idempotency_key": idempotency_key,
        })
        if self.should_fail_create:
            raise PaymentError("Simulated PayPal create order error")

        order_id = f"ORDER-MOCK-{uuid.uuid4().hex[:12].upper()}"
        approval_url = f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"
        return PayPalOrderResponse(
            id=order_id,
            status="CREATED",
            links=[
                PayPalLink(href=approval_url, rel="approve", method="GET"),
                PayPalLink(href=f"https://api-m.sandbox.paypal.com/v2/checkout/orders/{order_id}/capture", rel="capture", method="POST"),
            ],
        )

    async def capture_order(
        self,
        order_id: str,
        idempotency_key: Optional[str] = None,
    ) -> PayPalCaptureResponse:
        self.capture_order_calls.append({
            "order_id": order_id,
            "idempotency_key": idempotency_key,
        })
        if self.should_timeout_capture:
            raise httpx.ReadTimeout("Simulated PayPal capture network timeout (uncertain outcome)")

        if self.should_fail_capture:
            return PayPalCaptureResponse(
                id=order_id,
                status="DECLINED",
            )

        capture_id = f"CAPTURE-MOCK-{uuid.uuid4().hex[:12].upper()}"
        return PayPalCaptureResponse(
            id=capture_id,
            status=self.capture_status,
            create_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    async def get_order(self, order_id: str) -> Dict[str, Any]:
        self.get_order_calls.append({"order_id": order_id})
        if order_id in self.mock_orders:
            return self.mock_orders[order_id]

        cap_id = f"CAPTURE-MOCK-{uuid.uuid4().hex[:8].upper()}"
        return {
            "id": order_id,
            "status": self.default_order_status,
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": cap_id,
                                "status": self.default_order_status,
                                "amount": {"value": "100.00", "currency_code": "USD"},
                            }
                        ]
                    }
                }
            ],
        }

    async def get_capture(self, capture_id: str) -> Dict[str, Any]:
        return {
            "id": capture_id,
            "status": "COMPLETED",
            "amount": {"value": "100.00", "currency_code": "USD"},
        }


# Global singleton instance
paypal_client: BasePayPalClient = PayPalClient()


def get_paypal_client() -> BasePayPalClient:
    return paypal_client


def set_paypal_client(client: BasePayPalClient) -> None:
    global paypal_client
    paypal_client = client
