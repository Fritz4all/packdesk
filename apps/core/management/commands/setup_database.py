"""Run at every start (docker entrypoint and docker-compose).

- No usable database yet: say so; the database is then set up in the browser.
- Empty database (new installation): create the tables right away; nothing can be lost.
- Existing database with changes of a new version: change nothing, but say so. The changes are
  applied with the button in the browser (or `migrate`, or RUN_MIGRATIONS=1), after a backup.
- Installation not finished: show where the wizard is and the installation code.
"""

import os

from django.core.management.base import BaseCommand

from apps.core import database_state, server_setup, setup_code


class Command(BaseCommand):
    help = "Create the tables of a new installation and report what still needs to be done."

    def handle(self, *args, **options):
        state, detail = server_setup.diagnose()
        if state != server_setup.OK:
            self.stdout.write(self.style.WARNING(
                f"{server_setup.message(state)} Open PackDesk in the browser to set up the database."
            ))
            if detail:
                self.stdout.write(f"  ({detail})")
            self._show_code()
            return
        if database_state.is_empty():
            self.stdout.write("New installation: creating the database tables ...")
            database_state.apply_changes()
            self.stdout.write(self.style.SUCCESS("Database tables created."))
        elif os.environ.get("RUN_MIGRATIONS") == "1" and database_state.pending():
            self.stdout.write("RUN_MIGRATIONS=1: applying database changes ...")
            database_state.apply_changes()
            self.stdout.write(self.style.SUCCESS("Database up to date."))

        waiting = database_state.pending()
        if waiting:
            self.stdout.write(self.style.WARNING(
                f"{len(waiting)} database change(s) of this version are waiting. Make a backup, then open "
                "PackDesk in the browser and choose 'Update database'."
            ))
            self._show_code()
            return

        from apps.siteconfig.models import SiteSettings

        if not SiteSettings.load().setup_completed:
            self.stdout.write(self.style.WARNING(
                "Installation not finished: open PackDesk in the browser to start the installation wizard."
            ))
            self._show_code()

    def _show_code(self):
        if setup_code.from_env():
            self.stdout.write("Installation code: the SETUP_CODE from .env.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Installation code: {setup_code.get_code()}"))
