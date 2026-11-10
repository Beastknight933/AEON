import datetime
import uuid
from typing import Any, Dict
from sqlalchemy import String, Boolean, JSON, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow


class Recommendation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "recommendations"

    purchase_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("purchase_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recommended_quote_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("supplier_quotes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reasoning: Mapped[str] = mapped_column(String(1024), nullable=False)
    comparison_scores: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    # Relationships
    purchase_request = relationship("PurchaseRequest", back_populates="recommendations")
    recommended_quote = relationship("SupplierQuote")
