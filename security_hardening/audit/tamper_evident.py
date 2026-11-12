"""Tamper-Evident Audit Verification and Cryptographic Hash-Chaining."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple


class AuditChainBlock:
    def __init__(
        self,
        sequence: int,
        prev_hash: str,
        timestamp_iso: str,
        action: str,
        actor_id: str,
        entity_id: str,
        payload: Dict[str, Any],
        block_hash: Optional[str] = None,
    ):
        self.sequence = sequence
        self.prev_hash = prev_hash
        self.timestamp_iso = timestamp_iso
        self.action = action
        self.actor_id = actor_id
        self.entity_id = entity_id
        self.payload = payload
        self.block_hash = block_hash or self.calculate_hash()

    def calculate_hash(self) -> str:
        """Compute SHA-256 hash over canonical serialized block components."""
        canonical_payload = json.dumps(self.payload, sort_keys=True)
        raw = f"{self.sequence}|{self.prev_hash}|{self.timestamp_iso}|{self.action}|{self.actor_id}|{self.entity_id}|{canonical_payload}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TamperEvidentAuditLedger:
    """Maintains and verifies an immutable, append-only cryptographic hash chain."""

    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.blocks: List[AuditChainBlock] = []

    def append_event(
        self,
        action: str,
        actor_id: str,
        entity_id: str,
        payload: Dict[str, Any],
        timestamp_iso: str,
    ) -> AuditChainBlock:
        """Append a new event and seal it into the cryptographic hash chain."""
        sequence = len(self.blocks) + 1
        prev_hash = self.blocks[-1].block_hash if self.blocks else self.GENESIS_HASH

        block = AuditChainBlock(
            sequence=sequence,
            prev_hash=prev_hash,
            timestamp_iso=timestamp_iso,
            action=action,
            actor_id=actor_id,
            entity_id=entity_id,
            payload=payload,
        )
        self.blocks.append(block)
        return block

    def verify_integrity(self) -> Tuple[bool, Optional[str], Optional[int]]:
        """Verify the integrity of the entire chain.

        Returns:
            (is_valid, error_reason, failed_block_sequence)
        """
        if not self.blocks:
            return True, None, None

        for idx, block in enumerate(self.blocks):
            # 1. Verify sequence
            expected_seq = idx + 1
            if block.sequence != expected_seq:
                return False, f"Sequence broken: expected {expected_seq}, got {block.sequence}", block.sequence

            # 2. Verify previous hash linkage
            expected_prev = self.blocks[idx - 1].block_hash if idx > 0 else self.GENESIS_HASH
            if block.prev_hash != expected_prev:
                return False, f"Hash chain linkage broken at sequence {block.sequence}", block.sequence

            # 3. Recompute and verify block hash
            recomputed = block.calculate_hash()
            if block.block_hash != recomputed:
                return False, f"Tampered block data detected at sequence {block.sequence}", block.sequence

        return True, None, None


audit_chain = TamperEvidentAuditLedger()

