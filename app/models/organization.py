import uuid
from sqlalchemy import String, Boolean, Enum, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.constants import UserRole
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)

    # Relationships
    memberships = relationship("Membership", back_populates="organization", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="organization", cascade="all, delete-orphan")
    policies = relationship("Policy", back_populates="organization", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="organization", cascade="all, delete-orphan")


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    memberships = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


class Membership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False),
        default=UserRole.MEMBER,
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="memberships")
    organization = relationship("Organization", back_populates="memberships")
