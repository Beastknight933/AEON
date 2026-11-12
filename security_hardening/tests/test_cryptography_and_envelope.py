"""Tests for Envelope Encryption, AES-256-GCM, and Key Management."""

import secrets
import pytest
from security_hardening.core.constants import KeyPurpose
from security_hardening.core.errors import CryptographicOperationError
from security_hardening.crypto.envelope import EnvelopeEncryptionEngine
from security_hardening.crypto.hashing import (
    compute_hmac_sha256,
    compute_sha256_hash,
    generate_secure_token,
    hash_with_salt,
    verify_hmac_sha256,
)
from security_hardening.crypto.key_management import KeyRegistry, LocalSoftwareKMSAdapter


def test_envelope_encryption_roundtrip():
    engine = EnvelopeEncryptionEngine()
    secret_payload = b"CONFIDENTIAL_AGENT_FINANCIAL_TRANSACTION_PAYLOAD"
    aad = b"tenant-org-uuid-1234"

    envelope = engine.encrypt_data(secret_payload, associated_data=aad)
    assert envelope["cipher"] == "AES-256-GCM"
    assert "ciphertext" in envelope
    assert "encrypted_dek" in envelope

    # Decrypt
    decrypted = engine.decrypt_data(envelope, associated_data=aad)
    assert decrypted == secret_payload


def test_envelope_encryption_tampered_ciphertext_fails():
    engine = EnvelopeEncryptionEngine()
    secret_payload = b"CONFIDENTIAL_PAYLOAD"
    envelope = engine.encrypt_data(secret_payload)

    # Tamper with base64 ciphertext
    envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"

    with pytest.raises(CryptographicOperationError):
        engine.decrypt_data(envelope)


def test_envelope_encryption_mismatched_aad_fails():
    engine = EnvelopeEncryptionEngine()
    secret_payload = b"CONFIDENTIAL_PAYLOAD"
    envelope = engine.encrypt_data(secret_payload, associated_data=b"org-1")

    # Decrypt with wrong AAD (simulating cross-tenant attack)
    with pytest.raises(CryptographicOperationError):
        engine.decrypt_data(envelope, associated_data=b"org-2-attacker")


def test_envelope_string_helpers():
    engine = EnvelopeEncryptionEngine()
    data_str = "Agent API Credential String: aeon_live_test_secret"
    json_envelope = engine.encrypt_string(data_str, associated_data="context_v1")
    assert isinstance(json_envelope, str)

    restored = engine.decrypt_string(json_envelope, associated_data="context_v1")
    assert restored == data_str


def test_hmac_sha256_verification():
    key = b"master-integrity-key-32-bytes!!"
    msg = b"purchase_id=123&amount=450.00"

    sig = compute_hmac_sha256(key, msg)
    assert verify_hmac_sha256(key, msg, sig) is True

    # Tampered message
    tampered_msg = b"purchase_id=123&amount=950.00"
    assert verify_hmac_sha256(key, tampered_msg, sig) is False


def test_key_rotation_and_kms():
    registry = KeyRegistry()
    kid_1, key_1 = registry.get_active_key(KeyPurpose.DATA_ENCRYPTION)
    assert kid_1 is not None

    # Rotate key
    kid_2 = registry.rotate_key(KeyPurpose.DATA_ENCRYPTION)
    assert kid_2 != kid_1

    # Verify old key remains retrievable for decryption
    assert registry.get_key_by_id(kid_1) == key_1

    # Test KMS Adapter
    kms = LocalSoftwareKMSAdapter()
    dek = secrets.token_bytes(32)
    enc_dek = kms.encrypt_dek(dek, "default")
    dec_dek = kms.decrypt_dek(enc_dek, "default")
    assert dec_dek == dek
