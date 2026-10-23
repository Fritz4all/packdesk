import getpass
import os

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.tenants.models import Tenant


class Command(BaseCommand):
    help = "Create a platform admin (no --tenant) or a staff user of a tenant."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--tenant", help="Tenant code (slug). Omit for a platform admin.")
        parser.add_argument("--role", help="Role (group) name for tenant staff, e.g. Beheerder.")
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        tenant = None
        if options["tenant"]:
            tenant = Tenant.objects.filter(slug=options["tenant"]).first()
            if tenant is None:
                raise CommandError(f"Unknown tenant {options['tenant']}.")

        password = os.environ.get("PACKDESK_PASSWORD") or getpass.getpass("Password: ")
        user = User(
            email=options["email"],
            tenant=tenant,
            first_name=options["first_name"],
            last_name=options["last_name"],
            kind=User.Kind.STAFF,
            is_staff=True,
            is_superuser=tenant is None,
        )
        user.set_password(password)
        user.save()
        if options["role"]:
            user.groups.add(Group.objects.get(name=options["role"]))
        self.stdout.write(self.style.SUCCESS(f"Created {user.email} ({tenant or 'platform admin'})"))
