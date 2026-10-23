from django.core.management.base import BaseCommand, CommandError

from apps.tenants.models import Domain, Tenant


class Command(BaseCommand):
    help = "Create a tenant with its primary domain."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--domain", required=True)
        parser.add_argument("--primary-color", default="#1f6feb")
        parser.add_argument("--accent-color", default="#0ea5e9")

    def handle(self, *args, **options):
        if Tenant.objects.filter(slug=options["slug"]).exists():
            raise CommandError(f"Tenant {options['slug']} already exists.")
        tenant = Tenant.objects.create(
            name=options["name"],
            slug=options["slug"],
            primary_color=options["primary_color"],
            accent_color=options["accent_color"],
        )
        Domain.objects.create(tenant=tenant, domain=options["domain"], is_primary=True)
        self.stdout.write(self.style.SUCCESS(f"Created tenant {tenant.slug} on {options['domain']}"))
