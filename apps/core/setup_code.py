"""The installation code that protects the first-run wizard and the database update page.

Without it, whoever reaches a fresh installation first could make themselves administrator.
The code is SETUP_CODE from .env when set; otherwise a random code is kept in DATA_ROOT and
shown in the container log (`docker compose logs web`) when PackDesk starts.
"""

import hmac
import secrets
from pathlib import Path

from django.conf import settings

FILE_NAME = "setup-code.txt"


def _file():
    return Path(settings.DATA_ROOT) / FILE_NAME


def from_env():
    return bool(getattr(settings, "SETUP_CODE", ""))


def get_code():
    if from_env():
        return settings.SETUP_CODE
    path = _file()
    if path.is_file():
        return path.read_text().strip()
    code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)
    path.chmod(0o600)
    return code


def check(value):
    expected = get_code().replace("-", "").upper()
    given = (value or "").strip().replace("-", "").replace(" ", "").upper()
    return bool(given) and hmac.compare_digest(given, expected)


def forget():
    """After first use the random code is no longer needed; a new one is made when required."""
    if not from_env():
        _file().unlink(missing_ok=True)
