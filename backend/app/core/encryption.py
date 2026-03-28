"""Symmetric encryption for PATs and auth configs.

Uses Fernet (AES-128-CBC with HMAC-SHA256). The encryption key is derived
from ENCRYPTION_KEY in settings (or auto-generated for dev).

AD-14: PATs stored encrypted, never logged or returned in API responses.
"""

import base64
import hashlib
import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from an arbitrary-length secret string.

    Uses SHA-256 to produce a deterministic 32-byte digest, then base64-encodes
    it to meet Fernet's url-safe-base64 key format requirement.
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    """Return a Fernet instance using the configured encryption key."""
    key = _derive_key(settings.ENCRYPTION_KEY)
    return Fernet(key)


# ---------------------------------------------------------------------------
# String encryption (PATs)
# ---------------------------------------------------------------------------


def encrypt_string(plaintext: str) -> str:
    """Encrypt a plaintext string and return a base64-encoded ciphertext."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_string(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext back to plaintext.

    Raises:
        ValueError: If the ciphertext is invalid or the key has changed.
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt: invalid token or wrong key") from exc


# ---------------------------------------------------------------------------
# JSON encryption (MCP auth configs)
# ---------------------------------------------------------------------------


def encrypt_json(data: dict[str, Any]) -> str:
    """Encrypt a JSON-serializable dict and return a base64-encoded ciphertext."""
    plaintext = json.dumps(data, separators=(",", ":"))
    return encrypt_string(plaintext)


def decrypt_json(ciphertext: str) -> dict[str, Any]:
    """Decrypt a base64-encoded ciphertext back to a dict.

    Raises:
        ValueError: If the ciphertext is invalid or the key has changed.
    """
    plaintext = decrypt_string(ciphertext)
    return json.loads(plaintext)
