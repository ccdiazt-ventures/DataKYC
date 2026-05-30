"""API key generation and hashing."""

import hashlib
import secrets
import uuid

SECRET_PEPPER = "dkc-pepper-v1"


def generate_api_key(prefix: str = "dkc", live: bool = True) -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_hash, prefix_display)
        raw_key: dkc_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  (50 chars total)
        key_hash: sha256 hex digest for storage
        prefix_display: first 12 chars of raw key for display
    """
    env = "live" if live else "test"
    raw_hash = secrets.token_hex(20)  # 40 hex chars
    raw_key = f"{prefix}_{env}_{raw_hash}"

    # Hash with pepper for storage
    key_hash = hashlib.sha256(f"{raw_key}{SECRET_PEPPER}".encode()).hexdigest()
    prefix_display = raw_key[:12]

    return raw_key, key_hash, prefix_display


def hash_key(raw_key: str) -> str:
    """Hash a raw API key for lookup."""
    return hashlib.sha256(f"{raw_key}{SECRET_PEPPER}".encode()).hexdigest()
