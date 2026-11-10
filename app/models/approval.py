import datetime
import decimal
import uuid
from typing import Optional
from sqlalchemy import String, Integer, Numeric, Enum, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import ApprovalStatus
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Approval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "approvals"

    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    selected_quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("supplier_quotes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), default=decimal.Decimal("0.00"), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", nullable=False
    )
    policy_version: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    approver_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status_enum", native_enum=False),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    decided_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    purchase_request = relationship("PurchaseRequest", back_populates="approvals")
    selected_quote = relationship("SupplierQuote")
    approver = relationship("User")
