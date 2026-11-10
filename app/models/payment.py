import decimal
import uuid
from typing import Optional
from sqlalchemy import String, Numeric, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import PaymentStatus
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class PaymentAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_attempts"

    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), default="paypal", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum", native_enum=False),
        default=PaymentStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )
    amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    provider_capture_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    approval_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    # Relationships
    purchase_request = relationship("PurchaseRequest", back_populates="payment_attempts")
