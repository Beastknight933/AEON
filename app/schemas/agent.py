import datetime
import uuid
from typing import Optional
from pydantic import BaseModel, Field


class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: Optional[str] = Field(None, max_length=512)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    is_active: Optional[bool] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: Optional[str]
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class AgentCredentialResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    key_prefix: str
    is_revoked: bool
    revoked_at: Optional[datetime.datetime]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class AgentKeyGenerateResponse(BaseModel):
    credential_id: uuid.UUID
    agent_id: uuid.UUID
    raw_api_key: str = Field(..., description="The raw API key. Shown ONLY ONCE. Store it securely.")
    key_prefix: str
    created_at: datetime.datetime


class AgentCreatedWithKeyResponse(BaseModel):
    agent: AgentResponse
    credentials: AgentKeyGenerateResponse
