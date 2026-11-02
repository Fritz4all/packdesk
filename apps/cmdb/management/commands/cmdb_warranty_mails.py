from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.utils import timezone, translation

from apps.cmdb import warranty
from apps.cmdb.models import CmdbSettings
from apps.siteconfig.models import SiteSettings


class Command(BaseCommand):
    help = "Send the warranty reminders that are due. Does nothing while the CMDB or the reminders are switched off."

    def add_arguments(self, parser):
        parser.add_argument("--now", action="store_true", help="Also before 08:00.")

    def handle(self, *args, **options):
        try:
            settings_ = CmdbSettings.load()
        except DatabaseError:  # a new version whose database update is still waiting; try again next time
            return
        if not (settings_.enabled and settings_.warranty_mail_enabled):
            return
        if not options["now"] and timezone.localtime().hour < warranty.FIRST_HOUR:
            return
        with translation.override(SiteSettings.load().language):
            result = warranty.send_due()
        self.stdout.write(f"Warranty reminders: {result['overview']} item(s) in the overview, "
                          f"{result['customers']} customer mail(s), {result['errors']} failed.")
