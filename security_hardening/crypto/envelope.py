"""Envelope Encryption Implementation using AES-256-GCM.

Provides:
- AES-256-GCM authenticated data encryption.
- Multi-tier envelope encryption (Data Encryption Key encrypted by Key Encryption Key).
- Secure random nonces (96-bit).
- Authenticated Additional Data (AAD) support.
"""

import base64
import json
import os
import secrets
from typing import Any, Dict, Optional, Tuple
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from security_hardening.core.errors import CryptographicOperationError


class EnvelopeEncryptionEngine:
    """Enterprise envelope encryption engine supporting AES-256-GCM with Key IDs."""

    def __init__(self, master_key: Optional[bytes] = None, default_key_id: str = "aeon-kek-v1"):
        if master_key is None:
            # Generate a 256-bit fallback key if none provided
            self.master_key = secrets.token_bytes(32)
        else:
            if len(master_key) != 32:
                raise ValueError("Master key must be exactly 32 bytes (256 bits) for AES-256.")
            self.master_key = master_key
        self.default_key_id = default_key_id

    def encrypt_data(
        self,
        plaintext: bytes,
        associated_data: Optional[bytes] = None,
        key_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Encrypt plaintext using envelope encryption with AES-256-GCM.

        1. Generate fresh 256-bit ephemeral Data Encryption Key (DEK).
        2. Encrypt plaintext with DEK and fresh 96-bit IV.
        3. Encrypt DEK with Master Key (KEK) and fresh 96-bit IV.
        4. Package into structured, portable envelope.
        """
        try:
            active_key_id = key_id or self.default_key_id

            # 1. Generate fresh ephemeral DEK
            dek = secrets.token_bytes(32)

            # 2. Encrypt plaintext with DEK
            dek_aesgcm = AESGCM(dek)
            data_iv = secrets.token_bytes(12)  # 96-bit recommended nonce
            ciphertext_with_tag = dek_aesgcm.encrypt(data_iv, plaintext, associated_data)

            # 3. Encrypt DEK with KEK (Master Key)
            kek_aesgcm = AESGCM(self.master_key)
            dek_iv = secrets.token_bytes(12)
            encrypted_dek = kek_aesgcm.encrypt(dek_iv, dek, active_key_id.encode("utf-8"))

            return {
                "version": "1.0",
                "cipher": "AES-256-GCM",
                "key_id": active_key_id,
                "encrypted_dek": base64.b64encode(encrypted_dek).decode("ascii"),
                "dek_iv": base64.b64encode(dek_iv).decode("ascii"),
                "data_iv": base64.b64encode(data_iv).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext_with_tag).decode("ascii"),
            }
        except Exception as exc:
            raise CryptographicOperationError(f"Envelope encryption failed: {exc}") from exc

    def decrypt_data(
        self,
        envelope: Dict[str, str],
        associated_data: Optional[bytes] = None,
    ) -> bytes:
        """Decrypt data envelope using the Master Key (KEK).

        1. Validate envelope structure.
        2. Decrypt DEK using KEK.
        3. Decrypt ciphertext using decrypted DEK and verify GCM authentication tag.
        """
        try:
            key_id = envelope["key_id"]
            encrypted_dek = base64.b64decode(envelope["encrypted_dek"])
            dek_iv = base64.b64decode(envelope["dek_iv"])
            data_iv = base64.b64decode(envelope["data_iv"])
            ciphertext = base64.b64decode(envelope["ciphertext"])

            # 1. Decrypt DEK with KEK
            kek_aesgcm = AESGCM(self.master_key)
            dek = kek_aesgcm.decrypt(dek_iv, encrypted_dek, key_id.encode("utf-8"))

            # 2. Decrypt payload with DEK
            dek_aesgcm = AESGCM(dek)
            plaintext = dek_aesgcm.decrypt(data_iv, ciphertext, associated_data)

            return plaintext
        except Exception as exc:
            raise CryptographicOperationError(f"Envelope decryption failed: {exc}") from exc

    def encrypt_string(self, text: str, associated_data: Optional[str] = None) -> str:
        """Convenience method to encrypt string and return JSON string envelope."""
        aad = associated_data.encode("utf-8") if associated_data else None
        envelope = self.encrypt_data(text.encode("utf-8"), associated_data=aad)
        return json.dumps(envelope)

    def decrypt_string(self, json_envelope_str: str, associated_data: Optional[str] = None) -> str:
        """Convenience method to decrypt JSON string envelope back to string."""
        envelope = json.loads(json_envelope_str)
        aad = associated_data.encode("utf-8") if associated_data else None
        decrypted_bytes = self.decrypt_data(envelope, associated_data=aad)
        return decrypted_bytes.decode("utf-8")

