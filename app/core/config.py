from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    APP_NAME: str = "AEON - Agent Procurement Control Plane"
    APP_ENV: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Security & Auth
    SECRET_KEY: str = "aeon-dev-insecure-secret-key-change-in-production-min32chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    PASSWORD_HASH_SCHEME: str = "argon2"  # "argon2" or "bcrypt"

    # Agent API Key configuration
    AGENT_KEY_PREFIX: str = "aeon_live_"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://aeon-control.vercel.app",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./aeon_dev.db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # PayPal Sandbox Configuration
    PAYPAL_CLIENT_ID: str = "mock_paypal_client_id"
    PAYPAL_CLIENT_SECRET: str = "mock_paypal_client_secret"
    PAYPAL_API_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_WEBHOOK_ID: str = "mock_paypal_webhook_id"
    PAYPAL_MODE: str = "sandbox"  # "sandbox" or "live"
    PAYPAL_RETURN_URL: str = "http://localhost:3000/payments/success"
    PAYPAL_CANCEL_URL: str = "http://localhost:3000/payments/cancel"

    # ML Recommendation Configuration
    ML_PROVIDER_TYPE: str = "mock"  # "mock" or "module"
    ML_MODULE_PATH: str = "app.integrations.ml.mock_provider"
    ML_TIMEOUT_SECONDS: float = 5.0

    # Procurement Policy Defaults
    DEFAULT_CURRENCY: str = "USD"


settings = Settings()
