"""Encryption of stored database passwords.

The key is derived from SECRET_KEY, so a copy of the database alone does not reveal the passwords.
If SECRET_KEY changes, the stored passwords can no longer be read and must be entered again.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = hashlib.sha256(b"packdesk.legacy.password:" + settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token):
    """The password, or None when it cannot be read (e.g. SECRET_KEY changed)."""
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
