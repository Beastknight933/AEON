import datetime
import re
import uuid
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.core.constants import UserRole

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Administrator email address")
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: str = Field(..., min_length=1, max_length=128)
    organization_name: str = Field(..., min_length=2, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("value is not a valid email address")
        return clean


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="Administrator email address")
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class CurrentUserWithOrgResponse(BaseModel):
    user: UserResponse
    organization: OrganizationResponse
    role: UserRole
