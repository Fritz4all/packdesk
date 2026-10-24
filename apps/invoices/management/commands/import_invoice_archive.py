import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.customers.models import Customer
from apps.invoices.archive import file_date, parse, pdf_text, to_invoice_fields
from apps.invoices.models import Invoice
from apps.numbering.models import NumberSequence


class Command(BaseCommand):
    help = (
        "Register the previous webshop's invoice PDFs (DOCUMENT_ARCHIVE_DIR) as invoices and link them to customers by "
        "customer number. Safe to run again: existing ones are skipped. The PDFs themselves are not changed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Stop after this many new invoices (for testing).")
        parser.add_argument("--relink", action="store_true",
                            help="Only link already imported invoices to customers again (e.g. after importing customers).")
        parser.add_argument("--fix-dates", action="store_true",
                            help="Fill in missing dates of imported invoices from the text or the file date.")

    def handle(self, *args, **options):
        if options["relink"]:
            return self.relink()
        if options["fix_dates"]:
            return self.fix_dates()
        folder = settings.DOCUMENT_ARCHIVE_DIR
        if not folder or not os.path.isdir(folder):
            raise CommandError("DOCUMENT_ARCHIVE_DIR is not set or does not exist.")
        sequence = NumberSequence.objects.get(key="invoice")
        if not sequence.archive_regex:
            raise CommandError("The 'invoice' number sequence has no file name pattern for the archive.")
        regex = re.compile(sequence.archive_regex)
        existing = set(Invoice.objects.filter(is_archive=True).values_list("archive_file", flat=True))
        customers = dict(Customer.objects.exclude(number="").values_list("number", "pk"))
        files = sorted(f for f in os.listdir(folder) if regex.fullmatch(f) and f not in existing)
        if options["limit"]:
            files = files[: options["limit"]]
        created = linked = problems = 0
        batch = []
        for i, name in enumerate(files, 1):
            number = str(int(regex.fullmatch(name).group(1)))
            path = os.path.join(folder, name)
            data = parse(pdf_text(path))
            if data.get("number") and data["number"].lstrip("0") != number:
                problems += 1
                self.stderr.write(f"{name}: number in PDF ({data['number']}) differs from file name; using file name.")
            fields = to_invoice_fields(data, file_date(path))
            customer_id = customers.get(fields.get("customer_number", ""))
            linked += customer_id is not None
            batch.append(Invoice(number=number, is_archive=True, archive_file=name, customer_id=customer_id, **fields))
            if len(batch) >= 500:
                created += self._save(batch)
                batch = []
                self.stdout.write(f"  {i}/{len(files)} …")
        created += self._save(batch)
        self.stdout.write(self.style.SUCCESS(
            f"Imported {created} archived invoices; {linked} linked to a customer; {problems} with a warning."
        ))

    @transaction.atomic
    def _save(self, batch):
        Invoice.objects.bulk_create(batch, ignore_conflicts=True)
        return len(batch)

    def relink(self):
        customers = dict(Customer.objects.exclude(number="").values_list("number", "pk"))
        changed = 0
        for invoice in Invoice.objects.filter(is_archive=True).only("pk", "customer_number", "customer_id"):
            customer_id = customers.get(invoice.customer_number)
            if customer_id != invoice.customer_id:
                Invoice.objects.filter(pk=invoice.pk).update(customer_id=customer_id)
                changed += 1
        self.stdout.write(self.style.SUCCESS(f"Relinked {changed} archived invoices."))

    def fix_dates(self):
        folder = settings.DOCUMENT_ARCHIVE_DIR
        fixed = 0
        for invoice in Invoice.objects.filter(is_archive=True, issued_on="1970-01-01"):
            path = os.path.join(folder, invoice.archive_file)
            if not os.path.isfile(path):
                continue
            fields = to_invoice_fields(parse(pdf_text(path)), file_date(path))
            Invoice.objects.filter(pk=invoice.pk).update(issued_on=fields["issued_on"])
            fixed += 1
        self.stdout.write(self.style.SUCCESS(f"Fixed the date of {fixed} archived invoices."))
