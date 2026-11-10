import datetime
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional, Tuple
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(
    subject: str,
    claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[datetime.timedelta] = None,
) -> str:
    """Create a signed JWT access token for dashboard users."""
    if expires_delta:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "type": "access_token",
    }
    if claims:
        to_encode.update(claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Access token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid access token")


def generate_agent_api_key() -> Tuple[str, str, str]:
    """
    Generates a cryptographically secure individual agent API key.
    Returns:
        (raw_key, key_prefix, key_hash)
    The raw_key MUST only be returned once to the caller.
    The database only stores key_prefix and key_hash.
    """
    random_bytes = secrets.token_urlsafe(32)
    raw_key = f"{settings.AGENT_KEY_PREFIX}{random_bytes}"
    # Prefix is first 16 characters for fast indexed lookup
    key_prefix = raw_key[:16]
    key_hash = hash_agent_key(raw_key)
    return raw_key, key_prefix, key_hash


def hash_agent_key(raw_key: str) -> str:
    """
    Computes a cryptographic SHA-256 HMAC or hash of the agent raw key.
    Using SHA-256 over 256-bit cryptographically random key provides
    both collision resistance and irreversibility.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_agent_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time verification of an agent API key."""
    computed_hash = hash_agent_key(raw_key)
    return hmac.compare_digest(computed_hash, stored_hash)
