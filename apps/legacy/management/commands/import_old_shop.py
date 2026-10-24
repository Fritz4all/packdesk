"""Import the previous webshop's database (an external database in PackDesk). A trial run unless --apply is given.

    python manage.py import_old_shop --database <id>            # trial: nothing is saved
    python manage.py import_old_shop --database <id> --apply    # import for real
"""

from django.core.management.base import BaseCommand, CommandError

from apps.legacy.models import ExternalDatabase, ImportRun
from apps.legacy.old_shop.importer import run_import


class Command(BaseCommand):
    help = "Import the previous webshop's database into PackDesk (trial run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--database", type=int, required=True, help="Id of the external database in PackDesk.")
        parser.add_argument("--apply", action="store_true", help="Save the import (default: trial run).")

    def handle(self, *args, **options):
        db = ExternalDatabase.objects.filter(pk=options["database"]).first()
        if db is None:
            raise CommandError("External database not found.")
        run = ImportRun.objects.create(database=db, dry_run=not options["apply"])
        run_import(run)
        run.refresh_from_db()
        self.stdout.write(f"{run}: {run.get_status_display()}")
        for part, counts in run.counts.items():
            self.stdout.write(f"  {part:<20} " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        if run.notes:
            self.stdout.write(run.notes)
        if run.report_file:
            self.stdout.write(f"Report: DATA_ROOT/{run.report_file}")
