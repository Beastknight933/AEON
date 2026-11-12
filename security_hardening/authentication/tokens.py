"""Secure Refresh Token Rotation with Token Family Reuse Detection and Revocation."""

import datetime
import hashlib
import hmac
import secrets
import uuid
from typing import Dict, Optional, Set, Tuple

from security_hardening.core.config import security_settings


class RefreshTokenFamily:
    """Tracks a family of rotated refresh tokens for reuse detection."""

    def __init__(self, family_id: str, user_id: str, organization_id: str):
        self.family_id = family_id
        self.user_id = user_id
        self.organization_id = organization_id
        self.active_token_hash: Optional[str] = None
        self.retired_token_hashes: Set[str] = set()
        self.is_revoked: bool = False
        self.created_at = datetime.datetime.now(datetime.timezone.utc)


class TokenSecurityManager:
    """Manages refresh token lifecycles, family tracking, and access token revocation."""

    def __init__(self):
        # In-memory storage with interface for Redis/Database persistence
        self._families: Dict[str, RefreshTokenFamily] = {}
        self._revoked_jti: Set[str] = set()
        self._user_revocation_timestamps: Dict[str, datetime.datetime] = {}

    def issue_refresh_token(self, user_id: str, organization_id: str, family_id: Optional[str] = None) -> Tuple[str, str]:
        """Issue a new refresh token under a token family.

        Returns:
            (raw_refresh_token, family_id)
        """
        fam_id = family_id or f"fam_{uuid.uuid4().hex}"
        if fam_id not in self._families:
            self._families[fam_id] = RefreshTokenFamily(fam_id, user_id, organization_id)

        raw_token = f"aeon_rt_{secrets.token_urlsafe(48)}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        fam = self._families[fam_id]
        if fam.active_token_hash:
            fam.retired_token_hashes.add(fam.active_token_hash)
        fam.active_token_hash = token_hash

        return raw_token, fam_id

    def rotate_refresh_token(self, presented_raw_token: str, family_id: str) -> Tuple[str, str, str]:
        """Rotate a refresh token with strict reuse detection.

        If a previously retired token is presented (indicating token theft),
        immediately revoke the entire family!

        Returns:
            (new_raw_token, user_id, organization_id)
        """
        fam = self._families.get(family_id)
        if not fam:
            raise ValueError("Invalid refresh token family")

        if fam.is_revoked:
            raise ValueError("Refresh token family has been revoked")

        presented_hash = hashlib.sha256(presented_raw_token.encode("utf-8")).hexdigest()

        # Check for token reuse attack
        if presented_hash in fam.retired_token_hashes:
            fam.is_revoked = True
            raise ValueError("SECURITY ALERT: Refresh token reuse detected! Family has been revoked.")

        if not fam.active_token_hash or not hmac.compare_digest(presented_hash, fam.active_token_hash):
            raise ValueError("Invalid refresh token")

        # Rotate: issue new token
        new_token, _ = self.issue_refresh_token(fam.user_id, fam.organization_id, family_id=fam.family_id)
        return new_token, fam.user_id, fam.organization_id

    def revoke_family(self, family_id: str) -> None:
        """Revoke a token family immediately."""
        fam = self._families.get(family_id)
        if fam:
            fam.is_revoked = True

    def revoke_user_sessions(self, user_id: str) -> None:
        """Revoke all sessions and refresh token families for a user."""
        self._user_revocation_timestamps[user_id] = datetime.datetime.now(datetime.timezone.utc)
        for fam in self._families.values():
            if fam.user_id == user_id:
                fam.is_revoked = True

    def blacklist_access_token(self, jti: str) -> None:
        """Add a specific JWT ID (jti) to revocation blacklist."""
        self._revoked_jti.add(jti)

    def is_token_revoked(self, jti: Optional[str], user_id: str, issued_at: Optional[datetime.datetime]) -> bool:
        """Check if access token has been revoked by jti or user-wide logout."""
        if jti and jti in self._revoked_jti:
            return True
        revoked_at = self._user_revocation_timestamps.get(user_id)
        if revoked_at and issued_at:
            if issued_at < revoked_at:
                return True
        return False


token_security_manager = TokenSecurityManager()

