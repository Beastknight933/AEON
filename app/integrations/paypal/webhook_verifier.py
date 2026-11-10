from typing import Any, Dict
import httpx
from app.core.config import settings
from app.core.errors import WebhookVerificationError
from app.core.logging import get_logger
from app.integrations.paypal.client import paypal_client

logger = get_logger("aeon.paypal_webhook")


class PayPalWebhookVerifier:
    @classmethod
    async def verify(
        cls,
        headers: Dict[str, str],
        event_body: Dict[str, Any],
    ) -> bool:
        """
        Verify incoming webhook notification authenticity using PayPal's verification API.
        """
        # In mock or testing mode, bypass remote PayPal verification if simulated
        if paypal_client.is_mock_mode:
            # Check for presence of basic webhook headers or mock token
            if headers.get("x-mock-webhook") == "true" or "event_type" in event_body:
                return True

        transmission_id = headers.get("paypal-transmission-id")
        transmission_time = headers.get("paypal-transmission-time")
        cert_url = headers.get("paypal-cert-url")
        auth_algo = headers.get("paypal-auth-algo")
        transmission_sig = headers.get("paypal-transmission-sig")

        if not all([transmission_id, transmission_time, cert_url, auth_algo, transmission_sig]):
            raise WebhookVerificationError("Missing required PayPal verification headers")

        token = await paypal_client.get_access_token()
        verification_payload = {
            "transmission_id": transmission_id,
            "transmission_time": transmission_time,
            "cert_url": cert_url,
            "auth_algo": auth_algo,
            "transmission_sig": transmission_sig,
            "webhook_id": settings.PAYPAL_WEBHOOK_ID,
            "webhook_event": event_body,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{paypal_client.base_url}/v1/notifications/verify-webhook-signature",
                json=verification_payload,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                raise WebhookVerificationError(f"PayPal webhook verification request failed: {resp.text}")

            result = resp.json()
            status = result.get("verification_status")
            if status != "SUCCESS":
                raise WebhookVerificationError(f"PayPal webhook signature invalid: status={status}")

            return True
