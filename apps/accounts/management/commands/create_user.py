import getpass
import os

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create a staff user: a superuser (--superuser) or a user with a role (--role)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--superuser", action="store_true", help="Superadmin: every right, always.")
        parser.add_argument("--role", help="Internal role name, e.g. Administrator, Finance, Service or Employee.")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        if options["superuser"]:
            from apps.accounts.admin import superadmins_left

            if superadmins_left() <= 0:
                raise CommandError("The maximum number of superadmins has been reached (Settings → Security).")
        password = os.environ.get("PACKDESK_PASSWORD") or getpass.getpass("Password: ")
        user = User(
            email=options["email"],
            first_name=options["first_name"],
            last_name=options["last_name"],
            kind=User.Kind.STAFF,
            is_staff=True,
            is_superuser=options["superuser"],
        )
        user.set_password(password)
        user.save()
        if options["role"]:
            user.groups.add(Group.objects.get(name=options["role"]))
        if user.is_superuser:
            # Installing without the browser: with an administrator the installation counts as finished.
            from apps.siteconfig.models import SiteSettings

            SiteSettings.objects.filter(pk=SiteSettings.load().pk).update(setup_completed=True)
        self.stdout.write(self.style.SUCCESS(f"Created {user.email}"))
