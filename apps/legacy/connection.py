"""Read-only connections to external databases.

Three locks keep the other database safe:
1. the session is set to read-only on the server (MariaDB: READ ONLY transaction,
   PostgreSQL: default_transaction_read_only);
2. `Reader.rows()` only runs statements that start with SELECT;
3. the stored user should itself only have read rights (said in the admin).

Queries are written with backticks around names and %s for values; they are adapted per engine.
"""

import re
import sqlite3

from django.utils.translation import gettext as _

CONNECT_TIMEOUT = 5
READ_TIMEOUT = 120


class ExternalDatabaseError(Exception):
    """The external database cannot be reached or read."""


class Reader:
    def __init__(self, connection, engine):
        self.connection, self.engine = connection, engine

    def _sql(self, sql):
        if not re.match(r"\s*select\b", sql, re.I):
            raise ExternalDatabaseError("Only SELECT statements are allowed.")
        if self.engine == "postgres":
            sql = sql.replace("`", '"')
        elif self.engine == "sqlite":
            sql = sql.replace("%s", "?")
        return sql

    def rows(self, sql, params=()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(self._sql(sql), params)
            names = [c[0] for c in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
        except ExternalDatabaseError:
            raise
        except Exception as exc:  # driver errors differ per engine
            raise ExternalDatabaseError(str(exc)) from exc
        finally:
            cursor.close()

    def columns(self, sql):
        """Column names of a query's result."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(self._sql(sql))
            return [c[0] for c in cursor.description]
        except Exception as exc:
            raise ExternalDatabaseError(str(exc)) from exc
        finally:
            cursor.close()

    def value(self, sql, params=()):
        rows = self.rows(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def tables(self):
        if self.engine == "mariadb":
            sql = "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE()"
        elif self.engine == "postgres":
            sql = "SELECT table_name AS name FROM information_schema.tables WHERE table_schema = 'public'"
        else:
            sql = "SELECT name FROM sqlite_master WHERE type = 'table'"
        return {str(r["name"]).lower() for r in self.rows(sql)}

    def version(self):
        if self.engine == "sqlite":
            return "SQLite " + sqlite3.sqlite_version
        return str(self.value("SELECT VERSION()"))

    def close(self):
        try:
            self.connection.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_reader(db):
    """A read-only Reader for an ExternalDatabase (or anything with the same attributes)."""
    password = db.get_password()
    if password is None:
        raise ExternalDatabaseError(_("The stored password can no longer be read (the secret key changed). Enter it again."))
    try:
        if db.engine == "mariadb":
            import MySQLdb

            conn = MySQLdb.connect(
                host=db.host, port=db.port or 3306, user=db.user, password=password, database=db.database,
                charset="utf8mb4", connect_timeout=CONNECT_TIMEOUT, read_timeout=READ_TIMEOUT,
            )
            cursor = conn.cursor()
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.close()
        elif db.engine == "postgres":
            import psycopg

            conn = psycopg.connect(
                host=db.host, port=db.port or 5432, user=db.user, password=password, dbname=db.database,
                connect_timeout=CONNECT_TIMEOUT, options="-c default_transaction_read_only=on",
            )
        elif db.engine == "sqlite":
            # Only for tests: `database` is a file path, opened read-only.
            conn = sqlite3.connect(f"file:{db.database}?mode=ro", uri=True)
        else:
            raise ExternalDatabaseError(_("Unknown database type."))
    except ExternalDatabaseError:
        raise
    except Exception as exc:
        raise ExternalDatabaseError(str(exc)) from exc
    return Reader(conn, db.engine)


OLD_SHOP_TABLES = {"customer", "employee", "hw_support_pack_license", "hw_support_order", "invoice"}


def check_connection(db):
    """(ok, message) after connecting: server version and whether it looks like the previous webshop."""
    try:
        with open_reader(db) as reader:
            version, tables = reader.version(), reader.tables()
    except ExternalDatabaseError as exc:
        return False, _("No connection: %(error)s") % {"error": exc}
    if OLD_SHOP_TABLES <= tables:
        kind = _("This is a database of the previous webshop.")
    else:
        kind = _("No previous webshop tables found; comparing is not possible with this database.")
    return True, _("Connected to %(version)s, %(n)s tables. %(kind)s") % {"version": version, "n": len(tables), "kind": kind}
