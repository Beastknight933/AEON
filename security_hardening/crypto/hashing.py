"""Cryptographic hashing and HMAC utilities with constant-time verification."""

import hashlib
import hmac
import secrets
from typing import Optional, Tuple


def generate_secure_token(length_bytes: int = 32, prefix: str = "") -> str:
    """Generate a high-entropy cryptographically secure URL-safe token."""
    raw = secrets.token_urlsafe(length_bytes)
    return f"{prefix}{raw}"


def compute_hmac_sha256(key: bytes, message: bytes) -> str:
    """Compute HMAC-SHA256 hex digest."""
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify_hmac_sha256(key: bytes, message: bytes, expected_signature_hex: str) -> bool:
    """Constant-time verification of HMAC-SHA256 signature."""
    computed_hex = compute_hmac_sha256(key, message)
    return hmac.compare_digest(computed_hex, expected_signature_hex)


def compute_sha256_hash(data: bytes) -> str:
    """Compute SHA-256 digest in hex."""
    return hashlib.sha256(data).hexdigest()


def hash_with_salt(value: str, salt: Optional[bytes] = None) -> Tuple[str, str]:
    """Generate SHA-256 hash with cryptographic salt.

    Returns:
        (hash_hex, salt_hex)
    """
    actual_salt = salt or secrets.token_bytes(16)
    hasher = hashlib.sha256()
    hasher.update(actual_salt)
    hasher.update(value.encode("utf-8"))
    return hasher.hexdigest(), actual_salt.hex()

