"""Is the database empty, up to date, or waiting for changes of a new PackDesk version?"""

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

_pending_cache = None


def is_empty():
    return "django_migrations" not in connection.introspection.table_names()


def pending():
    """Database changes (migrations) of this version that have not been applied yet."""
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def has_pending():
    """Cached per process: checked once, and again after an update."""
    global _pending_cache
    if _pending_cache is None:
        _pending_cache = bool(pending())
    return _pending_cache


def apply_changes():
    global _pending_cache
    call_command("migrate", interactive=False, verbosity=0)
    _pending_cache = None
