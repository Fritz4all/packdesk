"""Encryption of the stored passwords of external databases (see apps.core.crypto)."""

from apps.core import crypto

PURPOSE = "legacy.password"


def encrypt(value):
    return crypto.encrypt(value, PURPOSE)


def decrypt(token):
    return crypto.decrypt(token, PURPOSE)
