import datetime
import decimal
import uuid
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Numeric, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import ReservationStatus
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Budget(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "budgets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    allocated_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    reserved_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), default=decimal.Decimal("0.00"), nullable=False
    )
    spent_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), default=decimal.Decimal("0.00"), nullable=False
    )
    start_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def available_amount(self) -> decimal.Decimal:
        return self.allocated_amount - self.reserved_amount - self.spent_amount

    # Relationships
    organization = relationship("Organization", back_populates="budgets")
    reservations = relationship("BudgetReservation", back_populates="budget", cascade="all, delete-orphan")


class BudgetReservation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "budget_reservations"

    budget_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )
    amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus, name="reservation_status_enum", native_enum=False),
        default=ReservationStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    budget = relationship("Budget", back_populates="reservations")
