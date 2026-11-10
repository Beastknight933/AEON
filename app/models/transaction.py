import decimal
import uuid
from typing import Optional
from sqlalchemy import String, Numeric, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import TransactionType, TransactionStatus
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    budget_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("budgets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, name="transaction_type_enum", native_enum=False),
        default=TransactionType.PURCHASE,
        nullable=False,
    )
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status_enum", native_enum=False),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True,
    )
    amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True, nullable=True)

    # Relationships
    purchase_request = relationship("PurchaseRequest", back_populates="transactions")
