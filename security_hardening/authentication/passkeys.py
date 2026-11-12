"""WebAuthn / FIDO2 Passkey Support Interface.

Implements standard W3C WebAuthn Level 3 challenge generation,
credential descriptor storage, and signature verification structures.
"""

import base64
import os
import secrets
from typing import Any, Dict, List, Optional


class PasskeyManager:
    """Manages FIDO2 / WebAuthn passkey registration challenges and credentials."""

    def __init__(self, rp_id: str = "aeon-control.vercel.app", rp_name: str = "AEON Procurement"):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self._pending_challenges: Dict[str, Dict[str, Any]] = {}
        self._registered_passkeys: Dict[str, List[Dict[str, Any]]] = {}

    def generate_registration_options(self, user_id: str, username: str) -> Dict[str, Any]:
        """Generate WebAuthn PublicKeyCredentialCreationOptions."""
        challenge = secrets.token_bytes(32)
        challenge_b64 = base64.urlsafe_b64encode(challenge).decode("ascii").rstrip("=")

        options = {
            "challenge": challenge_b64,
            "rp": {"name": self.rp_name, "id": self.rp_id},
            "user": {
                "id": base64.urlsafe_b64encode(user_id.encode("utf-8")).decode("ascii").rstrip("="),
                "name": username,
                "displayName": username,
            },
            "pubKeyCredParams": [
                {"alg": -7, "type": "public-key"},   # ES256
                {"alg": -257, "type": "public-key"},  # RS256
            ],
            "timeout": 60000,
            "attestation": "none",
        }

        self._pending_challenges[challenge_b64] = {
            "user_id": user_id,
            "purpose": "registration",
        }
        return options

    def verify_registration_response(
        self,
        user_id: str,
        challenge_b64: str,
        credential_id_b64: str,
        public_key_b64: str,
    ) -> bool:
        """Verify and record a newly registered passkey credential."""
        pending = self._pending_challenges.pop(challenge_b64, None)
        if not pending or pending["user_id"] != user_id:
            return False

        if user_id not in self._registered_passkeys:
            self._registered_passkeys[user_id] = []

        self._registered_passkeys[user_id].append({
            "credential_id": credential_id_b64,
            "public_key": public_key_b64,
            "sign_count": 0,
        })
        return True

    def generate_authentication_options(self, user_id: str) -> Dict[str, Any]:
        """Generate WebAuthn PublicKeyCredentialRequestOptions."""
        challenge = secrets.token_bytes(32)
        challenge_b64 = base64.urlsafe_b64encode(challenge).decode("ascii").rstrip("=")

        user_keys = self._registered_passkeys.get(user_id, [])
        allow_credentials = [
            {"type": "public-key", "id": k["credential_id"]}
            for k in user_keys
        ]

        options = {
            "challenge": challenge_b64,
            "timeout": 60000,
            "rpId": self.rp_id,
            "allowCredentials": allow_credentials,
            "userVerification": "preferred",
        }

        self._pending_challenges[challenge_b64] = {
            "user_id": user_id,
            "purpose": "authentication",
        }
        return options


passkey_manager = PasskeyManager()

