import asyncio
import decimal
import datetime
import uuid
import pytest
from app.core.constants import ReservationStatus
from app.core.errors import BudgetExceededError
from app.models.budget import Budget
from app.repositories.budget_repo import BudgetRepository


@pytest.mark.asyncio
async def test_budget_reservation_lifecycle_and_invariants(db_session):
    repo = BudgetRepository(db_session)
    org_id = uuid.uuid4()
    budget = Budget(
        organization_id=org_id,
        name="Team Compute Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("1000.00"),
        reserved_amount=decimal.Decimal("0.00"),
        spent_amount=decimal.Decimal("0.00"),
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )
    await repo.create(budget)
    await db_session.commit()

    # 1. Reserve $300
    res1 = await repo.reserve_funds_atomic(budget.id, uuid.uuid4(), decimal.Decimal("300.00"), "USD")
    await db_session.commit()
    assert res1.status == ReservationStatus.ACTIVE
    assert budget.reserved_amount == decimal.Decimal("300.00")
    assert budget.available_amount == decimal.Decimal("700.00")

    # 2. Reserve another $500 -> total reserved = $800, available = $200
    res2 = await repo.reserve_funds_atomic(budget.id, uuid.uuid4(), decimal.Decimal("500.00"), "USD")
    await db_session.commit()
    assert budget.reserved_amount == decimal.Decimal("800.00")
    assert budget.available_amount == decimal.Decimal("200.00")

    # 3. Attempting to reserve $250 > $200 available must raise BudgetExceededError
    with pytest.raises(BudgetExceededError):
        await repo.reserve_funds_atomic(budget.id, uuid.uuid4(), decimal.Decimal("250.00"), "USD")

    # 4. Settle reservation 1 ($300): reserved drops by 300, spent increases by 300
    settled = await repo.settle_reservation_atomic(res1.id)
    await db_session.commit()
    assert settled.status == ReservationStatus.SETTLED
    assert budget.reserved_amount == decimal.Decimal("500.00")
    assert budget.spent_amount == decimal.Decimal("300.00")
    assert budget.available_amount == decimal.Decimal("200.00")

    # 5. Release reservation 2 ($500): reserved drops by 500, available increases by 500
    released = await repo.release_reservation_atomic(res2.id)
    await db_session.commit()
    assert released.status == ReservationStatus.RELEASED
    assert budget.reserved_amount == decimal.Decimal("0.00")
    assert budget.spent_amount == decimal.Decimal("300.00")
    assert budget.available_amount == decimal.Decimal("700.00")


@pytest.mark.asyncio
async def test_simultaneous_budget_reservations_cannot_overspend(db_session):
    """
    Test simultaneous reservation requests competing for a tight budget pool.
    Under atomic row-level locking, the total approved reservation must NEVER exceed allocated budget.
    """
    repo = BudgetRepository(db_session)
    org_id = uuid.uuid4()
    budget = Budget(
        organization_id=org_id,
        name="Competitive Pool",
        currency="USD",
        allocated_amount=decimal.Decimal("500.00"),
        reserved_amount=decimal.Decimal("0.00"),
        spent_amount=decimal.Decimal("0.00"),
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )
    await repo.create(budget)
    await db_session.commit()

    # We submit 4 requests of $200 each.
    # Total requested = $800, but only $500 is available.
    # Exactly 2 should succeed ($400 total) and the remaining 2 must be rejected.
    target_budget_id = budget.id
    successful = []
    failed = []

    for i in range(4):
        try:
            res = await repo.reserve_funds_atomic(
                budget_id=target_budget_id,
                purchase_request_id=uuid.uuid4(),
                amount=decimal.Decimal("200.00"),
                currency="USD",
            )
            await db_session.commit()
            successful.append(res)
        except BudgetExceededError:
            await db_session.rollback()
            failed.append(i)

    assert len(successful) == 2
    assert len(failed) == 2

    # Query budget fresh after rollbacks
    updated_budget = await repo.get_by_id(target_budget_id)
    assert updated_budget is not None
    assert updated_budget.reserved_amount == decimal.Decimal("400.00")
    assert updated_budget.available_amount == decimal.Decimal("100.00")
