"""The previous webshop's passwords.

The previous webshop stored passwords reversibly: 3DES-CBC with a key derived from the user's salt by Ruby's
deprecated OpenSSL `Cipher#encrypt(salt)`, i.e. OpenSSL's EVP_BytesToKey with MD5, one round, salt
"OpenSSL " and IV "OpenSSL ". This module reads them back once, during the import, so customers can
keep logging in with their own password; PackDesk then stores only its own one-way hash.
"""

import base64
import hashlib

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, modes

RUBY_SALT = b"OpenSSL "  # first 8 bytes of "OpenSSL for Ruby rulez!", as used by Ruby
KEY_LENGTH = 24


def _evp_bytes_to_key(password, salt, length):
    data, block = b"", b""
    while len(data) < length:
        block = hashlib.md5(block + password + salt).digest()
        data += block
    return data[:length]


def decrypt(crypted_password, salt):
    """The plain password, or None when it cannot be read."""
    if not crypted_password or not salt:
        return None
    try:
        key = _evp_bytes_to_key(salt.encode(), RUBY_SALT, KEY_LENGTH)
        decryptor = Cipher(TripleDES(key), modes.CBC(RUBY_SALT)).decryptor()
        padded = decryptor.update(base64.b64decode(crypted_password)) + decryptor.finalize()
        unpadder = padding.PKCS7(64).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
