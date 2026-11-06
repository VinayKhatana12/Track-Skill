"""VAPID key management for Web Push (Phase 10).

Keys come from settings (VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY) when present;
otherwise a P-256 pair is generated once and persisted to a local JSON file so
the demo works out of the box without committed secrets. Both representations
are the base64url "raw" forms understood by py_vapid and by the browser's
PushManager (applicationServerKey).

Run `python -m app.core.vapid` to print a fresh pair for .env files.
"""

import base64
import json
import logging
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def generate_keypair() -> tuple[str, str]:
    """Return (private_key, public_key) as base64url raw strings.

    The private key is the 32-byte big-endian private value (the "raw" form
    py_vapid expects); the public key is the 65-byte uncompressed EC point
    the browser's PushManager understands.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value
    private_raw = private_value.to_bytes(32, byteorder="big")
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url(private_raw), _b64url(public_raw)


def load_or_create_keypair() -> tuple[str, str]:
    """Resolve VAPID keys: settings first, then the keys file, else generate."""
    settings = get_settings()
    if settings.vapid_private_key and settings.vapid_public_key:
        return settings.vapid_private_key, settings.vapid_public_key

    keys_file = Path(settings.vapid_keys_file)
    if keys_file.exists():
        try:
            data = json.loads(keys_file.read_text(encoding="utf-8"))
            if data.get("private_key") and data.get("public_key"):
                return data["private_key"], data["public_key"]
        except (OSError, json.JSONDecodeError):
            logger.warning("Could not read VAPID keys file %s; regenerating.", keys_file)

    private_key, public_key = generate_keypair()
    try:
        keys_file.write_text(
            json.dumps({"private_key": private_key, "public_key": public_key}, indent=2),
            encoding="utf-8",
        )
        logger.info("Generated new VAPID keypair at %s", keys_file)
    except OSError:
        logger.warning("Could not persist VAPID keys to %s", keys_file)
    return private_key, public_key


def public_key_for_browser() -> str:
    """The base64url P-256 public key handed to PushManager.subscribe()."""
    return load_or_create_keypair()[1]


if __name__ == "__main__":
    private_key, public_key = generate_keypair()
    print(f"VAPID_PRIVATE_KEY={private_key}")
    print(f"VAPID_PUBLIC_KEY={public_key}")
