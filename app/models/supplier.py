import datetime
import decimal
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import String, Boolean, Integer, Numeric, JSON, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin, utcnow


class Supplier(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "suppliers"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reliability_score: Mapped[decimal.Decimal] = mapped_column(
        Numeric(3, 2), default=decimal.Decimal("1.00"), nullable=False
    )

    # Relationships
    quotes = relationship("SupplierQuote", back_populates="supplier")


class SupplierQuote(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "supplier_quotes"

    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    supplier_name: Mapped[str] = mapped_column(String(128), nullable=False)
    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_price: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    total_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    estimated_delivery_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_quote_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Relationships
    supplier = relationship("Supplier", back_populates="quotes")
    purchase_request = relationship(
        "PurchaseRequest",
        back_populates="quotes",
        foreign_keys=[purchase_request_id]
    )
