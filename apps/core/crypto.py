"""Encryption of stored passwords (external databases, mail server).

The key is derived from SECRET_KEY and a purpose, so a copy of the database alone does not reveal the
passwords. If SECRET_KEY changes, stored passwords can no longer be read and must be entered again.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet(purpose):
    key = hashlib.sha256(f"packdesk.{purpose}:".encode() + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value, purpose):
    return _fernet(purpose).encrypt(value.encode()).decode() if value else ""


def decrypt(token, purpose):
    """The password, or None when it cannot be read (e.g. SECRET_KEY changed)."""
    if not token:
        return ""
    try:
        return _fernet(purpose).decrypt(token.encode()).decode()
    except InvalidToken:
        return None
