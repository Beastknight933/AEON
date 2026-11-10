import decimal
import uuid
from typing import Any, List, Optional
from sqlalchemy import String, Boolean, Integer, Numeric, JSON, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Policy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    organization = relationship("Organization", back_populates="policies")
    versions = relationship("PolicyVersion", back_populates="policy", cascade="all, delete-orphan")
    agent_assignments = relationship("AgentPolicyAssignment", back_populates="policy", cascade="all, delete-orphan")


class PolicyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_policy_version"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    max_amount_per_transaction: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    max_amount_per_day: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    approval_threshold_amount: Mapped[decimal.Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )
    allowed_suppliers: Mapped[List[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    allowed_currencies: Mapped[List[str]] = mapped_column(
        JSON, default=lambda: ["USD"], nullable=False
    )

    # Relationships
    policy = relationship("Policy", back_populates="versions")


class AgentPolicyAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_policy_assignments"
    __table_args__ = (
        UniqueConstraint("agent_id", "policy_id", name="uq_agent_policy_assignment"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    agent = relationship("Agent", back_populates="policy_assignments")
    policy = relationship("Policy", back_populates="agent_assignments")
