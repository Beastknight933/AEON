import decimal
import uuid
import httpx
import pytest

from app.core.config import settings
from app.core.errors import PaymentError
from app.integrations.paypal.client import MockPayPalClient, PayPalClient
from app.schemas.payment import (
    PaymentCaptureRequest,
    PaymentCaptureResponse,
    PaymentOrderCreateRequest,
    PaymentOrderCreateResponse,
    PaymentStatusResponse,
)


@pytest.mark.asyncio
async def test_mock_paypal_client_create_and_capture_order():
    mock_client = MockPayPalClient()
    purchase_id = uuid.uuid4()
    amount = decimal.Decimal("149.99")
    currency = "USD"
    idempotency_key = "test_idem_123"

    # 1. Create order
    order_res = await mock_client.create_order(
        purchase_id=purchase_id,
        amount=amount,
        currency=currency,
        idempotency_key=idempotency_key,
    )
    assert order_res.id.startswith("ORDER-MOCK-")
    assert order_res.status == "CREATED"
    assert len(order_res.links) >= 1
    approve_link = next(l for l in order_res.links if l.rel == "approve")
    assert "token=" in approve_link.href

    assert len(mock_client.create_order_calls) == 1
    assert mock_client.create_order_calls[0]["purchase_id"] == purchase_id
    assert mock_client.create_order_calls[0]["amount"] == amount

    # 2. Capture order
    capture_res = await mock_client.capture_order(
        order_id=order_res.id,
        idempotency_key="cap_idem_123",
    )
    assert capture_res.id.startswith("CAPTURE-MOCK-")
    assert capture_res.status == "COMPLETED"
    assert len(mock_client.capture_order_calls) == 1


@pytest.mark.asyncio
async def test_mock_paypal_client_simulated_failures():
    # 1. Creation failure
    failing_create_client = MockPayPalClient(should_fail_create=True)
    with pytest.raises(PaymentError, match="Simulated PayPal create order error"):
        await failing_create_client.create_order(
            purchase_id=uuid.uuid4(),
            amount=decimal.Decimal("50.00"),
        )

    # 2. Capture failure (declined)
    declining_client = MockPayPalClient(should_fail_capture=True)
    cap_res = await declining_client.capture_order(order_id="ORDER-MOCK-123")
    assert cap_res.status == "DECLINED"

    # 3. Capture timeout (network failure / uncertain outcome)
    timing_out_client = MockPayPalClient(should_timeout_capture=True)
    with pytest.raises(httpx.ReadTimeout, match="Simulated PayPal capture network timeout"):
        await timing_out_client.capture_order(order_id="ORDER-MOCK-123")


@pytest.mark.asyncio
async def test_paypal_client_testing_mode():
    client = PayPalClient(client_id="mock_test_id", client_secret="mock_secret")
    assert client.is_mock_mode is True

    token = await client.get_access_token()
    assert token == "mock_paypal_access_token_12345"

    purchase_id = uuid.uuid4()
    order = await client.create_order(purchase_id=purchase_id, amount=decimal.Decimal("25.00"))
    assert order.id.startswith("ORDER-MOCK-")
    assert order.status == "CREATED"

    cap = await client.capture_order(order_id=order.id)
    assert cap.id.startswith("CAPTURE-MOCK-")
    assert cap.status == "COMPLETED"


def test_payment_pydantic_schemas():
    p_id = uuid.uuid4()
    req = PaymentOrderCreateRequest(purchase_request_id=p_id)
    assert req.purchase_request_id == p_id

    order_resp = PaymentOrderCreateResponse(
        payment_attempt_id=uuid.uuid4(),
        purchase_request_id=p_id,
        provider_order_id="ORDER-123",
        amount=decimal.Decimal("99.99"),
        currency="USD",
        status="ORDER_CREATED",
        approval_url="https://paypal.com/approve",
    )
    assert order_resp.provider_order_id == "ORDER-123"
    assert order_resp.amount == decimal.Decimal("99.99")

    cap_req = PaymentCaptureRequest(provider_order_id="ORDER-123")
    assert cap_req.provider_order_id == "ORDER-123"

    cap_resp = PaymentCaptureResponse(
        payment_attempt_id=uuid.uuid4(),
        purchase_request_id=p_id,
        provider_capture_id="CAP-123",
        amount=decimal.Decimal("99.99"),
        currency="USD",
        status="COMPLETED",
        transaction_id=uuid.uuid4(),
    )
    assert cap_resp.status == "COMPLETED"
