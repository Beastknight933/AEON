import datetime
import decimal
import uuid
import pytest
from pydantic import ValidationError

from app.core.constants import PurchaseStatus
from app.core.errors import StateTransitionError
from app.integrations.suppliers.mock_supplier_a import MockSupplierA
from app.integrations.suppliers.mock_supplier_b import MockSupplierB
from app.integrations.suppliers.registry import SupplierRegistry
from app.integrations.suppliers.schemas import NormalizedQuote
from app.models.purchase import PurchaseRequest
from app.models.supplier import Supplier, SupplierQuote
from app.services.procurement_service import transition_purchase_status, VALID_PURCHASE_TRANSITIONS


def test_normalized_quote_validations():
    # 1. Valid quote
    now = datetime.datetime.now(datetime.timezone.utc)
    future = now + datetime.timedelta(hours=2)
    q = NormalizedQuote(
        supplier_code="test_supp",
        supplier_name="Test Supplier",
        item_id="sku-1",
        unit_price=decimal.Decimal("25.00"),
        quantity=4,
        total_amount=decimal.Decimal("100.00"),
        currency="USD",
        expires_at=future,
    )
    assert q.is_expired is False

    # 2. Expired quote
    past = now - datetime.timedelta(hours=1)
    q_exp = NormalizedQuote(
        supplier_code="test_supp",
        supplier_name="Test Supplier",
        item_id="sku-1",
        unit_price=decimal.Decimal("25.00"),
        quantity=2,
        total_amount=decimal.Decimal("50.00"),
        currency="USD",
        expires_at=past,
    )
    assert q_exp.is_expired is True

    # 3. Total amount mismatch raises ValidationError
    with pytest.raises(ValidationError):
        NormalizedQuote(
            supplier_code="test_supp",
            supplier_name="Test Supplier",
            item_id="sku-1",
            unit_price=decimal.Decimal("25.00"),
            quantity=2,
            total_amount=decimal.Decimal("999.00"),  # Expected 50.00
            currency="USD",
        )

    # 4. Non-USD currency raises ValidationError
    with pytest.raises(ValidationError):
        NormalizedQuote(
            supplier_code="test_supp",
            supplier_name="Test Supplier",
            item_id="sku-1",
            unit_price=decimal.Decimal("25.00"),
            quantity=1,
            total_amount=decimal.Decimal("25.00"),
            currency="EUR",  # Non-USD
        )

    # 5. Non-positive unit_price raises ValidationError
    with pytest.raises(ValidationError):
        NormalizedQuote(
            supplier_code="test_supp",
            supplier_name="Test Supplier",
            item_id="sku-1",
            unit_price=decimal.Decimal("-10.00"),
            quantity=1,
            total_amount=decimal.Decimal("-10.00"),
            currency="USD",
        )


@pytest.mark.asyncio
async def test_mock_supplier_pricing_heuristics():
    supp_a = MockSupplierA()
    supp_b = MockSupplierB()

    # Compute pricing
    q_a_compute = await supp_a.fetch_quote("Server Rack Node", "compute", {"quantity": 2})
    assert q_a_compute.unit_price == decimal.Decimal("120.00")
    assert q_a_compute.total_amount == decimal.Decimal("240.00")
    assert q_a_compute.estimated_delivery_days == 0

    q_b_compute = await supp_b.fetch_quote("Server Rack Node", "compute", {"quantity": 2})
    assert q_b_compute.unit_price == decimal.Decimal("135.00")
    assert q_b_compute.total_amount == decimal.Decimal("270.00")
    assert q_b_compute.estimated_delivery_days == 2

    # Storage pricing
    q_a_storage = await supp_a.fetch_quote("SSD Drive", "storage", {"quantity": 1})
    assert q_a_storage.unit_price == decimal.Decimal("45.00")

    q_b_storage = await supp_b.fetch_quote("HDD Drive", "storage", {"quantity": 1})
    assert q_b_storage.unit_price == decimal.Decimal("40.00")


@pytest.mark.asyncio
async def test_supplier_registry_collection_and_db_persistence(db_session):
    registry = SupplierRegistry()

    # Ensure in DB
    models = await registry.ensure_suppliers_in_db(db_session)
    assert "mock_supplier_a" in models
    assert "mock_supplier_b" in models
    assert models["mock_supplier_a"].id is not None

    # Collect quotes concurrently
    quotes = await registry.collect_quotes("Cloud Database Instance", "compute", {"quantity": 1})
    assert len(quotes) == 2
    codes = {q.supplier_code for q in quotes}
    assert "mock_supplier_a" in codes
    assert "mock_supplier_b" in codes


def test_purchase_status_state_machine_transitions():
    pr = PurchaseRequest(
        organization_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        item_description="Test Item",
        category="compute",
        max_budget=decimal.Decimal("100.00"),
        currency="USD",
        status=PurchaseStatus.REQUESTED,
    )

    # REQUESTED -> QUOTING (allowed)
    transition_purchase_status(pr, PurchaseStatus.QUOTING)
    assert pr.status == PurchaseStatus.QUOTING

    # QUOTING -> RECOMMENDED (allowed)
    transition_purchase_status(pr, PurchaseStatus.RECOMMENDED)
    assert pr.status == PurchaseStatus.RECOMMENDED

    # RECOMMENDED -> AUTHORIZED (allowed)
    transition_purchase_status(pr, PurchaseStatus.AUTHORIZED)
    assert pr.status == PurchaseStatus.AUTHORIZED

    # AUTHORIZED -> BLOCKED (disallowed -> StateTransitionError)
    with pytest.raises(StateTransitionError):
        transition_purchase_status(pr, PurchaseStatus.BLOCKED)

    # Terminal state BLOCKED cannot transition to anything
    pr_blocked = PurchaseRequest(
        organization_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        item_description="Blocked Item",
        category="compute",
        max_budget=decimal.Decimal("100.00"),
        currency="USD",
        status=PurchaseStatus.BLOCKED,
    )
    with pytest.raises(StateTransitionError):
        transition_purchase_status(pr_blocked, PurchaseStatus.AUTHORIZED)
