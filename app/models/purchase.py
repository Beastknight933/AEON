import decimal
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import String, Numeric, Enum, JSON, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import FulfillmentStatus, PurchaseStatus
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class PurchaseRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "purchase_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    item_description: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    max_budget: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    requirements: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[PurchaseStatus] = mapped_column(
        Enum(PurchaseStatus, name="purchase_status_enum", native_enum=False),
        default=PurchaseStatus.REQUESTED,
        nullable=False,
        index=True,
    )
    fulfillment_status: Mapped[FulfillmentStatus] = mapped_column(
        Enum(FulfillmentStatus, name="fulfillment_status_enum", native_enum=False),
        default=FulfillmentStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )
    selected_quote_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("supplier_quotes.id", ondelete="SET NULL", use_alter=True, name="fk_pr_selected_quote"),
        nullable=True,
    )

    # Relationships
    organization = relationship("Organization")
    agent = relationship("Agent", back_populates="purchase_requests")
    quotes = relationship(
        "SupplierQuote",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
        foreign_keys="[SupplierQuote.purchase_request_id]"
    )
    selected_quote = relationship(
        "SupplierQuote",
        foreign_keys=[selected_quote_id],
        post_update=True,
    )
    recommendations = relationship("Recommendation", back_populates="purchase_request", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="purchase_request", cascade="all, delete-orphan")
    payment_attempts = relationship("PaymentAttempt", back_populates="purchase_request", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="purchase_request")
