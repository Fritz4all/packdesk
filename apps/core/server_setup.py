"""Database connection for a new installation, set up in the browser.

When PackDesk has no database settings yet, or cannot use the database it was given, every page
shows the database step instead of the site (see ServerSetupMiddleware). There you enter the
database server and, when the database does not exist yet, a login of a server administrator to
create it. That login is used once and never stored. The settings are saved in DATA_ROOT/packdesk.env
and PackDesk restarts itself to use them.
"""

import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass

from django.conf import settings
from django.db import connection
from django.utils.translation import gettext as _

log = logging.getLogger(__name__)

OK, NOT_CONFIGURED, NO_DATABASE, BAD_LOGIN, UNREACHABLE, ERROR = (
    "ok", "not_configured", "no_database", "bad_login", "unreachable", "error")


@dataclass
class Target:
    engine: str  # mariadb | postgres
    host: str
    port: int | None
    name: str
    user: str
    password: str

    @property
    def default_port(self):
        return 3306 if self.engine == "mariadb" else 5432


def current_target():
    db = settings.DATABASES["default"]
    engine = "mariadb" if "mysql" in db.get("ENGINE", "") else "postgres"
    port = db.get("PORT")
    return Target(engine, db.get("HOST", ""), int(port) if str(port or "").isdigit() else None,
                  db.get("NAME", "packdesk") or "packdesk", db.get("USER", "packdesk") or "packdesk",
                  db.get("PASSWORD", ""))


def classify(exc):
    """What went wrong, from the driver's error (MariaDB error codes, PostgreSQL messages)."""
    code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    text = str(exc).lower()
    if code in (1049, 1044) or ("database" in text and "does not exist" in text) or (
            "role" in text and "does not exist" in text):
        return NO_DATABASE
    if code == 1045 or "password authentication failed" in text or "authentication failed" in text:
        return BAD_LOGIN
    if code in (2002, 2003, 2005) or any(t in text for t in (
            "could not connect", "connection refused", "could not translate host", "timeout", "timed out",
            "name or service not known", "no route to host", "failed to resolve host", "name resolution",
            "unknown mysql server host")):
        return UNREACHABLE
    return ERROR


def diagnose():
    """(state, technical message) for the database PackDesk is configured with."""
    if not settings.DATABASE_CONFIGURED:
        return NOT_CONFIGURED, ""
    try:
        connection.ensure_connection()
    except Exception as exc:
        connection.close()
        cause = exc.__cause__ or exc
        return classify(cause), str(cause)
    return OK, ""


def _connect(target, user, password, database):
    if target.engine == "mariadb":
        import MySQLdb

        return MySQLdb.connect(host=target.host, port=target.port or 3306, user=user, password=password,
                               database=database or "", charset="utf8mb4", connect_timeout=8)
    import psycopg

    return psycopg.connect(host=target.host, port=target.port or 5432, user=user, password=password,
                           dbname=database or "postgres", connect_timeout=8, autocommit=True)


def test(target):
    """None when PackDesk's own login works, otherwise (state, message)."""
    try:
        _connect(target, target.user, target.password, target.name).close()
    except Exception as exc:
        return classify(exc), str(exc)
    return None


def create(target, admin_user, admin_password):
    """Create the database and PackDesk's own user with an administrator login (used once).

    An existing user is not changed; an existing database is left as it is.
    """
    conn = _connect(target, admin_user, admin_password, None)
    try:
        cur = conn.cursor()
        if target.engine == "mariadb":
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{target.name}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cur.execute("SELECT COUNT(*) FROM mysql.user WHERE user = %s", [target.user])
            if not cur.fetchone()[0]:
                cur.execute("CREATE USER %s@'%%' IDENTIFIED BY %s", [target.user, target.password])
            cur.execute(f"GRANT ALL PRIVILEGES ON `{target.name}`.* TO %s@'%%'", [target.user])
            conn.commit()
        else:
            from psycopg import sql

            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [target.user])
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(target.user), sql.Literal(target.password)))
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [target.name])
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
                    sql.Identifier(target.name), sql.Identifier(target.user)))
    finally:
        conn.close()


def message(state):
    return {
        NOT_CONFIGURED: _("PackDesk does not know its database yet."),
        NO_DATABASE: _("The database server answers, but the database or its user does not exist yet."),
        BAD_LOGIN: _("The database server refuses the user name or password."),
        UNREACHABLE: _("The database server cannot be reached. Check the server name or IP address and the port, "
                       "and whether the server accepts connections from this computer."),
        ERROR: _("The database cannot be used."),
    }.get(state, "")


def save(target):
    """Store the database settings that do not come from the environment or .env."""
    values = {"DB_ENGINE": target.engine, "DB_HOST": target.host, "DB_PORT": target.port or "",
              "DB_NAME": target.name, "DB_USER": target.user, "DB_PASSWORD": target.password}
    from . import server_config

    server_config.write(settings.DATA_ROOT, {k: v for k, v in values.items() if k not in settings.FIXED_SETTINGS})


def restart_soon():
    """Restart PackDesk shortly after this response, so it reads the new settings."""

    def restart():
        if "gunicorn" in sys.modules:
            os.kill(os.getppid(), signal.SIGHUP)  # gunicorn reloads its workers with the new settings
        else:
            os._exit(3)  # the development server restarts on exit code 3

    threading.Timer(1.0, restart).start()
