import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr, Field
from app.core.constants import UserRole


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")
    full_name: str = Field(..., min_length=1, max_length=128)
    organization_name: str = Field(..., min_length=2, max_length=128)


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


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
