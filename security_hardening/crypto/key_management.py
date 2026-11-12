"""Key Management, Versioning, and KMS/HSM Integration Interface."""

from __future__ import annotations

import abc
import datetime
import secrets
from typing import Dict, List, Optional, Tuple
from security_hardening.core.constants import KeyPurpose


class BaseKMSAdapter(abc.ABC):
    """Abstract interface for external Key Management Systems (KMS/HSM)."""

    @abc.abstractmethod
    def encrypt_dek(self, dek: bytes, key_alias: str) -> bytes:
        """Encrypt Data Encryption Key via KMS/HSM."""
        pass

    @abc.abstractmethod
    def decrypt_dek(self, encrypted_dek: bytes, key_alias: str) -> bytes:
        """Decrypt Data Encryption Key via KMS/HSM."""
        pass


class LocalSoftwareKMSAdapter(BaseKMSAdapter):
    """Local software fallback KMS adapter for environments without Cloud KMS/HSM."""

    def __init__(self, master_keys: Optional[Dict[str, bytes]] = None):
        self._keys = master_keys or {"default": secrets.token_bytes(32)}

    def encrypt_dek(self, dek: bytes, key_alias: str) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = self._keys.get(key_alias, self._keys.get("default"))
        aesgcm = AESGCM(key)
        iv = secrets.token_bytes(12)
        ct = aesgcm.encrypt(iv, dek, None)
        return iv + ct

    def decrypt_dek(self, encrypted_dek: bytes, key_alias: str) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = self._keys.get(key_alias, self._keys.get("default"))
        aesgcm = AESGCM(key)
        iv = encrypted_dek[:12]
        ct = encrypted_dek[12:]
        return aesgcm.decrypt(iv, ct, None)


class KeyRegistry:
    """Manages active and retired cryptographic keys with versioning and rotation."""

    def __init__(self):
        self._keys: Dict[str, Dict[str, Any]] = {}
        self._active_key_ids: Dict[KeyPurpose, str] = {}

    def register_key(
        self,
        key_id: str,
        purpose: KeyPurpose,
        key_bytes: bytes,
        is_active: bool = True,
    ) -> None:
        self._keys[key_id] = {
            "key_id": key_id,
            "purpose": purpose,
            "key": key_bytes,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "is_active": is_active,
        }
        if is_active:
            self._active_key_ids[purpose] = key_id

    def get_active_key(self, purpose: KeyPurpose) -> Tuple[str, bytes]:
        key_id = self._active_key_ids.get(purpose)
        if not key_id or key_id not in self._keys:
            # Generate on-demand key if not provisioned
            new_id = f"auto-{purpose.value}-v1"
            key_bytes = secrets.token_bytes(32)
            self.register_key(new_id, purpose, key_bytes, is_active=True)
            return new_id, key_bytes
        return key_id, self._keys[key_id]["key"]

    def get_key_by_id(self, key_id: str) -> Optional[bytes]:
        entry = self._keys.get(key_id)
        return entry["key"] if entry else None

    def rotate_key(self, purpose: KeyPurpose) -> str:
        """Create a new version for this purpose and retire the old one as inactive."""
        old_id = self._active_key_ids.get(purpose)
        if old_id and old_id in self._keys:
            self._keys[old_id]["is_active"] = False

        new_version = len([k for k in self._keys.values() if k["purpose"] == purpose]) + 1
        new_id = f"{purpose.value}-v{new_version}"
        self.register_key(new_id, purpose, secrets.token_bytes(32), is_active=True)
        return new_id


key_registry = KeyRegistry()

