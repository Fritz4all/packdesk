"""Server settings written by the installation wizard: DATA_ROOT/packdesk.env.

Used by packdesk/settings.py before Django starts, so no Django imports here.
Order of precedence: real environment variables, then .env in the project folder, then this file.
So what the docker-compose file or .env sets is never overruled by the wizard.
"""

import os
import secrets
from pathlib import Path

FILE_NAME = "packdesk.env"


def path(data_root):
    return Path(data_root) / FILE_NAME


def read(data_root):
    values = {}
    file = path(data_root)
    if file.is_file():
        for line in file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
    return values


def load(data_root):
    """Put the file's values in the environment where nothing else set them (an empty value, such as
    "SECRET_KEY=" in .env, counts as not set)."""
    for key, value in read(data_root).items():
        if not os.environ.get(key):
            os.environ[key] = value


def write(data_root, updates):
    """Merge `updates` into the file (only readable by PackDesk). Values are single lines."""
    values = read(data_root)
    values.update({k: str(v).replace("\n", " ") for k, v in updates.items()})
    file = path(data_root)
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_suffix(".tmp")
    tmp.write_text(
        "# Written by the PackDesk installation wizard. Values in the environment or in .env win.\n"
        + "".join(f"{k}={v}\n" for k, v in sorted(values.items()))
    )
    tmp.chmod(0o600)
    tmp.replace(file)


def ensure_secret_key(data_root):
    """A secret key is needed to start at all; make and keep one when none is given."""
    if os.environ.get("SECRET_KEY"):
        return
    key = secrets.token_urlsafe(50)
    try:
        write(data_root, {"SECRET_KEY": key})
    except OSError:
        pass  # read-only data folder: the key then lasts until the next start
    os.environ["SECRET_KEY"] = key
