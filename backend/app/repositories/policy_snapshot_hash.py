"""Deterministic content-hash helper for policy snapshots."""

from __future__ import annotations

import hashlib


def build_policy_snapshot_content_hash(normalized_text_body: str) -> str:
    """Return a stable content hash for normalized snapshot text."""

    return hashlib.sha256(normalized_text_body.encode("utf-8")).hexdigest()
