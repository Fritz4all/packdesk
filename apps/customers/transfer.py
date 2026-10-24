"""Export and import of customers with everything that belongs to them.

An export is a ZIP with `packdesk-export.json` and, optionally, the files (invoice PDFs, fault
attachments, logos) under `files/`. Relations inside the export are kept with references
("licences.licence:12"); catalogue items (service packs, brands, countries, ...) and users are
looked up by their name, code or email address, so an export also works in another installation.

An import never overwrites silently. `analyse()` makes a report first: per customer whether it
already exists (same customer number, or same ID from the old system) and what would change.
For every existing customer the user chooses: skip, overwrite, or import as a new customer.

Rules when importing:
- Overwrite: the customer's fields are replaced; its addresses, contacts, orders, licences,
  fault reports and invoices are matched by email address or number and updated or added.
  Items that exist here but are not in the file are kept; nothing is deleted.
- As new: the customer gets a new customer number. Documents whose number already exists here
  (licences, orders, fault reports, invoices) are skipped, because numbers must stay unique.
- Items that belong to another customer here are never touched.
- Passwords are never exported. Imported contacts get a login without a password; they set one
  with "forgot password" or an invitation.

`analyse()` runs the real import inside a transaction that is rolled back, so the report shows
exactly what the import will do.
"""

import datetime
import io
import json
import os
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import Q
from django.utils import formats, timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.models import User
from apps.faults.models import FaultAttachment, FaultReport, RepairOption
from apps.invoices.models import Invoice, InvoiceEmail, InvoiceLine
from apps.licences.models import HardwareSystem, Licence, LicenceOption, OptionType, SupportPack, Vendor
from apps.orders.models import Order, OrderLine

from .models import Contact, Country, Customer, CustomerAddress, CustomerType

FORMAT = "packdesk-customers"
VERSION = 1
DATA_NAME = "packdesk-export.json"
MAX_DATA_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024

SKIP = "skip"
OVERWRITE = "overwrite"
NEW = "new"


class ImportFileError(Exception):
    """The uploaded file is not a PackDesk customer export."""


# --- helpers ---------------------------------------------------------------------------------


class _Encoder(DjangoJSONEncoder):
    """Like Django's, but keeps microseconds so unchanged times compare equal after a round trip."""

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return super().default(o)


def ref(obj):
    return f"{obj._meta.label_lower}:{obj.pk}" if obj is not None else None


def _plain(obj, exclude=()):
    """Own fields of an object (no id, relations or files), as JSON-ready values."""
    data = {}
    for f in obj._meta.concrete_fields:
        if f.primary_key or f.is_relation or isinstance(f, models.FileField) or f.name in exclude:
            continue
        if getattr(f, "auto_now", False):
            continue
        data[f.name] = f.value_from_object(obj)
    return data


def _apply(obj, data, exclude=()):
    """Set own fields from exported data; unknown fields are ignored. Returns the names that changed."""
    changed = []
    for f in obj._meta.concrete_fields:
        if f.name not in data or f.primary_key or f.is_relation or isinstance(f, models.FileField) or f.name in exclude:
            continue
        if obj.pk and getattr(f, "auto_now_add", False):
            continue
        value = f.to_python(data[f.name])
        if value is None and not f.null:
            value = f.get_default()
        if getattr(obj, f.attname) != value:
            setattr(obj, f.attname, value)
            changed.append(f.name)
    return changed


def _links(obj):
    return tuple(getattr(obj, f.attname) for f in obj._meta.concrete_fields if f.is_relation)


def _restore_auto_dates(obj, data):
    """auto_now_add fields get 'now' on create; put the exported date back."""
    values = {f.name: f.to_python(data[f.name]) for f in obj._meta.concrete_fields
              if getattr(f, "auto_now_add", False) and data.get(f.name)}
    if values:
        type(obj).objects.filter(pk=obj.pk).update(**values)


def _names(obj, field_name="name"):
    """All language versions of a translated name, to find the same item in another installation."""
    if obj is None:
        return None
    values = {code: getattr(obj, f"{field_name}_{code}", "") for code, _n in settings.LANGUAGES}
    values = {k: v for k, v in values.items() if v} or {settings.LANGUAGE_CODE: getattr(obj, field_name)}
    return values


def _by_names(model, values, field_name="name"):
    if not values:
        return None
    query = Q()
    for code, value in values.items():
        query |= Q(**{f"{field_name}_{code}": value})
    return model.objects.filter(query).first()


def _email(user):
    return user.email if user else None


def _user(email):
    return User.objects.filter(email__iexact=email).first() if email else None


def _diff_label(model, name):
    return str(model._meta.get_field(name).verbose_name).capitalize()


def _show(value):
    if value in (None, ""):
        return "—"
    if isinstance(value, datetime.datetime):
        return formats.date_format(timezone.localtime(value), "DATETIME_FORMAT")
    if isinstance(value, datetime.date):
        return formats.date_format(value, "DATE_FORMAT")
    if value is True:
        return _("yes")
    if value is False:
        return _("no")
    return str(value)


# --- export ----------------------------------------------------------------------------------


def _pack_key(pack):
    return {"code": pack.code, "legacy_id": pack.legacy_id, "description": _names(pack, "description")}


def _system_key(system):
    return {"vendor": system.vendor.name, "name": system.name} if system else None


class _Files:
    def __init__(self, archive, include):
        self.archive, self.include, self.used = archive, include, set()

    def add(self, folder, name, read):
        """Put a file in the ZIP under files/; returns its path there, or None."""
        if not self.include:
            return None
        try:
            content = read()
        except (OSError, ValueError):
            return None
        base = os.path.basename(name) or "file"
        path = f"files/{folder}/{base}"
        n = 1
        while path in self.used:
            n += 1
            path = f"files/{folder}/{n}-{base}"
        self.used.add(path)
        self.archive.writestr(path, content)
        return path


def _read_field(file_field):
    def read():
        with file_field.open("rb") as f:
            return f.read()
    return read


def _export_customer(customer, files):
    folder = f"customer-{customer.pk}"
    block = {
        "ref": ref(customer),
        "fields": _plain(customer),
        "customer_type": _names(customer.customer_type),
        "approved_by": _email(customer.approved_by),
        "logo": files.add(folder, customer.logo.name, _read_field(customer.logo)) if customer.logo else None,
        "addresses": [
            {"fields": _plain(a), "country": a.country.code if a.country else None}
            for a in customer.addresses.select_related("country")
        ],
        "contacts": [
            {"fields": _plain(c),
             "user": {"email": c.user.email, "first_name": c.user.first_name, "last_name": c.user.last_name,
                      "is_active": c.user.is_active} if c.user else None}
            for c in customer.contacts.select_related("user")
        ],
        "orders": [],
        "licences": [],
        "faults": [],
        "invoices": [],
    }
    for order in customer.orders.select_related("created_by").prefetch_related("lines__pack", "lines__extends"):
        block["orders"].append({
            "ref": ref(order), "fields": _plain(order), "created_by": _email(order.created_by),
            "lines": [{"ref": ref(line), "fields": _plain(line), "pack": _pack_key(line.pack),
                       "extends": ref(line.extends), "extends_number": line.extends.full_number if line.extends else None}
                      for line in order.lines.all()],
        })
    licences = customer.licences.select_related("pack", "vendor", "system__vendor", "prolongation_of", "order_line")
    for lic in licences.prefetch_related("options__option_type", "options__vendor"):
        block["licences"].append({
            "ref": ref(lic), "fields": _plain(lic, exclude={"full_number"}), "pack": _pack_key(lic.pack),
            "order_line": ref(lic.order_line), "prolongation_of": ref(lic.prolongation_of),
            "prolongation_of_number": lic.prolongation_of.full_number if lic.prolongation_of else None,
            "vendor": lic.vendor.name if lic.vendor else None, "system": _system_key(lic.system),
            "options": [{"fields": _plain(o), "option_type": _names(o.option_type),
                         "vendor": o.vendor.name if o.vendor else None} for o in lic.options.all()],
        })
    for fault in customer.fault_reports.select_related("reported_by", "licence", "repair_option").prefetch_related("attachments"):
        block["faults"].append({
            "ref": ref(fault), "fields": _plain(fault), "reported_by": _email(fault.reported_by),
            "licence": ref(fault.licence), "licence_number": fault.licence.full_number if fault.licence else None,
            "repair_option": _names(fault.repair_option),
            "attachments": [{"fields": _plain(a), "file": files.add(f"{folder}/faults/{fault.pk}", a.name, _read_field(a.file))}
                            for a in fault.attachments.all()],
        })
    for invoice in customer.invoices.select_related("order").prefetch_related("lines", "emails__sent_by"):
        pdf = None
        if invoice.has_pdf():
            pdf = files.add(f"{folder}/invoices", invoice.archive_file or invoice.filename, invoice.pdf_bytes)
        block["invoices"].append({
            "ref": ref(invoice), "fields": _plain(invoice), "order": ref(invoice.order),
            "order_number": invoice.order.number if invoice.order else None, "pdf": pdf,
            "lines": [{"fields": _plain(line)} for line in invoice.lines.all()],
            "emails": [{"fields": _plain(e), "sent_by": _email(e.sent_by)} for e in invoice.emails.all()],
        })
    return block


def export_customers(queryset, include_files=True, out=None):
    """Write a ZIP with the customers and everything that belongs to them. Returns the file object."""
    out = out or io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        files = _Files(archive, include_files)
        customers = [_export_customer(c, files) for c in queryset.select_related("customer_type", "approved_by")]
        data = {
            "format": FORMAT, "version": VERSION, "exported_at": timezone.now(),
            "includes_files": include_files, "customers": customers,
        }
        archive.writestr(DATA_NAME, json.dumps(data, cls=_Encoder, ensure_ascii=False, indent=1))
    out.seek(0)
    return out


# --- reading an upload -----------------------------------------------------------------------


class ExportFile:
    """An uploaded export (ZIP, or the bare JSON without files)."""

    def __init__(self, path):
        self.path = path
        self._zip = None
        if zipfile.is_zipfile(path):
            self._zip = zipfile.ZipFile(path)
            infos = self._zip.infolist()
            if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
                raise ImportFileError(_("The file is too large to import."))
            try:
                info = self._zip.getinfo(DATA_NAME)
            except KeyError:
                raise ImportFileError(_("This ZIP file is not a PackDesk customer export.")) from None
            if info.file_size > MAX_DATA_BYTES:
                raise ImportFileError(_("The file is too large to import."))
            raw = self._zip.read(info)
            self.names = {i.filename for i in infos}
        else:
            if os.path.getsize(path) > MAX_DATA_BYTES:
                raise ImportFileError(_("The file is too large to import."))
            with open(path, "rb") as f:
                raw = f.read()
            self.names = set()
        try:
            self.data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise ImportFileError(_("This file is not a PackDesk customer export.")) from None
        if not isinstance(self.data, dict) or self.data.get("format") != FORMAT:
            raise ImportFileError(_("This file is not a PackDesk customer export."))
        if self.data.get("version", 0) > VERSION:
            raise ImportFileError(_("This export was made by a newer PackDesk version."))
        if not isinstance(self.data.get("customers"), list):
            raise ImportFileError(_("This file is not a PackDesk customer export."))

    @property
    def customers(self):
        return self.data["customers"]

    def read(self, name):
        if not name or self._zip is None or name not in self.names:
            return None
        return self._zip.read(name)

    def close(self):
        if self._zip is not None:
            self._zip.close()


def find_existing(block):
    """The customer here that an exported customer is the same as, and on what it matched."""
    fields = block.get("fields", {})
    if fields.get("number"):
        found = Customer.objects.filter(number=fields["number"]).first()
        if found:
            return found, _("customer number")
    if fields.get("legacy_id"):
        found = Customer.objects.filter(legacy_id=fields["legacy_id"]).first()
        if found:
            return found, _("ID in old system")
    return None, ""


# --- import ----------------------------------------------------------------------------------


KINDS = {
    "addresses": gettext_lazy("addresses"), "contacts": gettext_lazy("contacts"), "orders": gettext_lazy("orders"),
    "order_lines": gettext_lazy("order lines"), "licences": gettext_lazy("licences"),
    "faults": gettext_lazy("fault reports"), "invoices": gettext_lazy("invoices"),
}


@dataclass
class Outcome:
    """What happened (or would happen) to one customer."""

    action: str
    number: str = ""
    customer_pk: int | None = None
    counts: dict = field(default_factory=lambda: defaultdict(lambda: {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}))
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def count(self, kind, what):
        self.counts[kind][what] += 1

    def saved(self, kind, is_new, changed):
        self.count(kind, "created" if is_new else "updated" if changed else "unchanged")

    def skip(self, kind, label, reason):
        self.count(kind, "skipped")
        self.skipped.append({"key": kind, "kind": str(KINDS[kind]), "label": label, "reason": reason})

    def as_dict(self):
        return {
            "action": self.action, "number": self.number, "customer_pk": self.customer_pk,
            "counts": [{"key": k, "kind": str(KINDS[k]), **v} for k, v in self.counts.items()],
            "skipped": self.skipped, "warnings": self.warnings,
        }


class _Rollback(Exception):
    pass


class Importer:
    def __init__(self, export, dry_run):
        self.export, self.dry_run = export, dry_run
        self.refs = {}  # export ref -> object here
        self.missing_catalogue = set()

    # catalogue lookups
    def pack(self, key):
        if not key:
            return None
        if key.get("legacy_id"):
            found = SupportPack.objects.filter(legacy_id=key["legacy_id"]).first()
            if found:
                return found
        if key.get("code"):
            found = SupportPack.objects.filter(code=key["code"])
            if found.count() == 1:
                return found.first()
        return _by_names(SupportPack, key.get("description"), "description")

    def vendor(self, name):
        return Vendor.objects.filter(name__iexact=name).first() if name else None

    def system(self, key):
        if not key:
            return None
        return HardwareSystem.objects.filter(vendor__name__iexact=key["vendor"], name__iexact=key["name"]).first()

    def _resolve(self, key, number, model, lookup, customer):
        """An object by export reference, or else by its number when it belongs to this customer here."""
        if key in self.refs:
            return self.refs[key]
        if number:
            return model.objects.filter(**{lookup: number}, customer=customer).first()
        return None

    def _save_file(self, file_field, name, content):
        if content is not None and not self.dry_run:
            file_field.save(os.path.basename(name), ContentFile(content), save=False)

    # one customer
    def run_customer(self, block, decision):
        existing, _matched = find_existing(block)
        if existing is None:
            decision = NEW if decision != SKIP else SKIP
        outcome = Outcome(action=decision)
        if decision == SKIP:
            if existing:
                outcome.number, outcome.customer_pk = existing.number, existing.pk
            return outcome
        overwrite = decision == OVERWRITE and existing is not None
        fields = block.get("fields", {})
        if overwrite:
            customer = existing
            _apply(customer, fields, exclude={"number", "legacy_id"})
        else:
            customer = Customer()
            _apply(customer, fields)
            if existing is not None:
                # Import as an extra customer next to the existing one: it gets its own number.
                customer.number, customer.legacy_id = "", ""
                if customer.status == Customer.Status.ACTIVE:
                    customer.assign_number()
        customer.customer_type = _by_names(CustomerType, block.get("customer_type"))
        if block.get("customer_type") and customer.customer_type is None:
            outcome.warnings.append(_("Customer type not found here; left empty."))
        customer.approved_by = _user(block.get("approved_by"))
        if block.get("logo") and not customer.logo:
            self._save_file(customer.logo, block["logo"], self.export.read(block["logo"]))
        customer.save()
        if not overwrite:
            _restore_auto_dates(customer, fields)
        self.refs[block.get("ref")] = customer
        outcome.number, outcome.customer_pk = customer.number, customer.pk

        self._addresses(customer, block, overwrite, outcome)
        self._contacts(customer, block, overwrite, outcome)
        self._orders(customer, block, overwrite, outcome)
        self._licences(customer, block, overwrite, outcome)
        self._link_extensions(customer, block)
        self._faults(customer, block, overwrite, outcome)
        self._invoices(customer, block, overwrite, outcome)
        return outcome

    def _addresses(self, customer, block, overwrite, outcome):
        current = {a.kind: a for a in customer.addresses.all()} if overwrite else {}
        for item in block.get("addresses", []):
            address = current.get(item["fields"].get("kind")) or CustomerAddress(customer=customer)
            is_new = address.pk is None
            changed = _apply(address, item["fields"])
            country = Country.objects.filter(code__iexact=item.get("country")).first() if item.get("country") else None
            if item.get("country") and country is None:
                outcome.warnings.append(_("Country %(code)s not found here; left empty.") % {"code": item["country"]})
            changed = changed or address.country_id != (country.pk if country else None)
            address.country = country
            if is_new or changed:
                address.save()
            outcome.saved("addresses", is_new, changed)

    def _contacts(self, customer, block, overwrite, outcome):
        for item in block.get("contacts", []):
            data = item["fields"]
            email = (data.get("email") or "").strip()
            contact = customer.contacts.filter(email__iexact=email).first() if overwrite and email else None
            is_new = contact is None
            contact = contact or Contact(customer=customer)
            changed = _apply(contact, data)
            login = item.get("user")
            if login and contact.user_id is None:
                user = _user(login["email"])
                if user is None:
                    user = User(email=login["email"], first_name=login.get("first_name", ""),
                                last_name=login.get("last_name", ""), kind=User.Kind.CUSTOMER,
                                is_active=bool(login.get("is_active")))
                    user.set_unusable_password()
                    user.save()
                    contact.user, changed = user, True
                elif user.kind == User.Kind.CUSTOMER and not Contact.objects.filter(user=user).exists():
                    contact.user, changed = user, True
                else:
                    outcome.warnings.append(_("Login %(email)s is already used by someone else here; "
                                              "the contact was imported without a login.") % {"email": login["email"]})
            if is_new or changed:
                contact.save()
            outcome.saved("contacts", is_new, changed)

    def _orders(self, customer, block, overwrite, outcome):
        for item in block.get("orders", []):
            data = item["fields"]
            number = data.get("number", "")
            existing = Order.objects.filter(number=number).first() if number else None
            if existing is not None and (not overwrite or existing.customer_id != customer.pk):
                self._skip_existing(outcome, "orders", number, existing, customer)
                if existing.customer_id == customer.pk:
                    self.refs[item["ref"]] = existing
                continue
            order = existing or Order(customer=customer)
            before = _links(order)
            changed = _apply(order, data)
            order.created_by = _user(item.get("created_by"))
            changed = changed or before != _links(order)
            if existing is None or changed:
                order.save()
            outcome.saved("orders", existing is None, changed)
            self.refs[item["ref"]] = order
            current = list(order.lines.order_by("id")) if existing else []
            for line_item in item.get("lines", []):
                pack = self.pack(line_item.get("pack"))
                if pack is None:
                    outcome.skip("order_lines", f"{number}: {line_item['fields'].get('description', '')}",
                                 _("service pack not found here"))
                    continue
                line = self._matching_line(current, pack, line_item["fields"]) or OrderLine(order=order, pack=pack)
                is_new = line.pk is None
                changed = _apply(line, line_item["fields"])
                if is_new or changed:
                    line.save()
                outcome.saved("order_lines", is_new, changed)
                self.refs[line_item["ref"]] = line

    @staticmethod
    def _matching_line(lines, pack, data):
        """The existing order line that is the same as an exported one; each line matches once."""
        for line in lines:
            if (line.pack_id == pack.pk and line.description == data.get("description", "")
                    and line.reference == data.get("reference", "") and line.quantity == int(data.get("quantity") or 1)):
                lines.remove(line)
                return line
        return None

    def _skip_existing(self, outcome, kind, number, existing, customer):
        if existing.customer_id == customer.pk:
            outcome.skip(kind, number, _("already exists here"))
        else:
            owner = existing.customer.name if existing.customer else _("no customer")
            outcome.skip(kind, number, _("number already used here by %(owner)s") % {"owner": owner})

    def _licences(self, customer, block, overwrite, outcome):
        for item in block.get("licences", []):
            data = item["fields"]
            full_number = f"{data.get('number', '')}{data.get('suffix', '')}-{data.get('sequence', '')}"
            existing = Licence.objects.filter(full_number=full_number).first()
            if existing is not None and (not overwrite or existing.customer_id != customer.pk):
                self._skip_existing(outcome, "licences", full_number, existing, customer)
                if existing.customer_id == customer.pk:
                    self.refs[item["ref"]] = existing
                continue
            pack = self.pack(item.get("pack"))
            if pack is None:
                outcome.skip("licences", full_number, _("service pack not found here"))
                continue
            licence = existing or Licence(customer=customer)
            before = _links(licence)
            changed = _apply(licence, data, exclude={"full_number"})
            licence.pack = pack
            licence.vendor = self.vendor(item.get("vendor"))
            licence.system = self.system(item.get("system"))
            licence.order_line = self.refs.get(item.get("order_line")) or licence.order_line
            changed = changed or before != _links(licence)
            if existing is None or changed:
                licence.save()
            if existing is None:
                _restore_auto_dates(licence, data)
            outcome.saved("licences", existing is None, changed)
            self.refs[item["ref"]] = licence
            known = {(o.option_type_id, o.serial_nr, o.product_nr) for o in licence.options.all()} if existing else set()
            for option in item.get("options", []):
                option_type = _by_names(OptionType, option.get("option_type"))
                if option_type is None:
                    outcome.warnings.append(_("Option type not found here; option of %(n)s skipped.") % {"n": full_number})
                    continue
                key = (option_type.pk, option["fields"].get("serial_nr", ""), option["fields"].get("product_nr", ""))
                if key in known:
                    continue
                obj = LicenceOption(licence=licence, option_type=option_type, vendor=self.vendor(option.get("vendor")))
                _apply(obj, option["fields"])
                obj.save()

    def _link_extensions(self, customer, block):
        """Second pass: licence → licence it continues, order line → licence it extends."""
        for item in block.get("licences", []):
            licence = self.refs.get(item["ref"])
            if licence is None or licence.customer_id != customer.pk:
                continue
            previous = self._resolve(item.get("prolongation_of"), item.get("prolongation_of_number"), Licence, "full_number", customer)
            if previous is not None and licence.prolongation_of_id != previous.pk:
                Licence.objects.filter(pk=licence.pk).update(prolongation_of=previous)
        for order in block.get("orders", []):
            for line_item in order.get("lines", []):
                line = self.refs.get(line_item["ref"])
                if line is None or not (line_item.get("extends") or line_item.get("extends_number")):
                    continue
                target = self._resolve(line_item.get("extends"), line_item.get("extends_number"), Licence, "full_number", customer)
                if target is not None:
                    OrderLine.objects.filter(pk=line.pk).update(extends=target)

    def _faults(self, customer, block, overwrite, outcome):
        for item in block.get("faults", []):
            data = item["fields"]
            number = data.get("number", "")
            existing = FaultReport.objects.filter(number=number).first() if number else None
            if existing is not None and (not overwrite or existing.customer_id != customer.pk):
                self._skip_existing(outcome, "faults", number, existing, customer)
                continue
            fault = existing or FaultReport(customer=customer)
            before = _links(fault)
            changed = _apply(fault, data)
            fault.reported_by = _user(item.get("reported_by"))
            fault.licence = self._resolve(item.get("licence"), item.get("licence_number"), Licence, "full_number", customer)
            fault.repair_option = _by_names(RepairOption, item.get("repair_option"))
            changed = changed or before != _links(fault)
            if existing is None or changed:
                fault.save()
            outcome.saved("faults", existing is None, changed)
            known = {(a.name, a.size) for a in fault.attachments.all()} if existing else set()
            for attachment in item.get("attachments", []):
                key = (attachment["fields"].get("name", ""), int(attachment["fields"].get("size") or 0))
                content = self.export.read(attachment.get("file"))
                if key in known or content is None:
                    continue
                obj = FaultAttachment(report=fault)
                _apply(obj, attachment["fields"])
                if not self.dry_run:
                    obj.file.save(obj.name or "attachment", ContentFile(content), save=False)
                    obj.save()

    def _invoices(self, customer, block, overwrite, outcome):
        for item in block.get("invoices", []):
            data = item["fields"]
            number = data.get("number", "")
            existing = Invoice.objects.filter(number=number).first()
            if existing is not None and (not overwrite or existing.customer_id not in (customer.pk, None)):
                self._skip_existing(outcome, "invoices", number, existing, customer)
                continue
            invoice = existing or Invoice()
            before = _links(invoice)
            changed = _apply(invoice, data)
            invoice.customer = customer
            order = self._resolve(item.get("order"), item.get("order_number"), Order, "number", customer)
            if order is not None and Invoice.objects.filter(order=order).exclude(pk=invoice.pk).exists():
                order = None
            invoice.order = order
            if not invoice.has_pdf():
                content = self.export.read(item.get("pdf"))
                if content is not None:
                    # An archived invoice whose original file is not in this installation's archive keeps its own copy.
                    self._save_file(invoice.pdf, invoice.filename, content)
                    changed = True
            changed = changed or before != _links(invoice)
            if existing is None or changed:
                invoice.save()
            if existing is None:
                _restore_auto_dates(invoice, data)
                for line in item.get("lines", []):
                    obj = InvoiceLine(invoice=invoice)
                    _apply(obj, line["fields"])
                    obj.save()
                for mail in item.get("emails", []):
                    obj = InvoiceEmail(invoice=invoice, sent_by=_user(mail.get("sent_by")))
                    _apply(obj, mail["fields"])
                    obj.save()
                    _restore_auto_dates(obj, mail["fields"])
            outcome.saved("invoices", existing is None, changed)

    def run(self, decisions):
        outcomes = []
        try:
            with transaction.atomic():
                for index, block in enumerate(self.export.customers):
                    outcomes.append(self.run_customer(block, decisions.get(index, SKIP)))
                if self.dry_run:
                    raise _Rollback
        except _Rollback:
            pass
        return outcomes


def analyse(export):
    """Report per customer: does it exist here, what would change, and what each choice would do."""
    rows = []
    for index, block in enumerate(export.customers):
        fields = block.get("fields", {})
        existing, matched = find_existing(block)
        row = {"index": index, "name": fields.get("name", "?"), "number": fields.get("number", ""),
               "existing": None, "changes": [],
               "totals": {str(KINDS[k]): len(block.get(k, [])) for k in ("addresses", "contacts", "orders", "licences", "faults", "invoices")}}
        if existing is not None:
            row["existing"] = {"pk": existing.pk, "name": existing.name, "number": existing.number, "matched": str(matched)}
            for name, value in fields.items():
                if name in ("number", "legacy_id", "created_at"):
                    continue
                try:
                    f = Customer._meta.get_field(name)
                except Exception:
                    continue
                new = f.to_python(value)
                old = getattr(existing, f.attname)
                if old != new:
                    row["changes"].append({"field": _diff_label(Customer, name), "old": _show(old), "new": _show(new)})
        rows.append(row)
    choices = {OVERWRITE: {}, NEW: {}}
    for row in rows:
        choices[OVERWRITE][row["index"]] = OVERWRITE
        choices[NEW][row["index"]] = NEW
    for mode in (OVERWRITE, NEW):
        outcomes = Importer(export, dry_run=True).run(choices[mode])
        for row, outcome in zip(rows, outcomes):
            if row["existing"] is not None or mode == NEW:
                row[mode] = outcome.as_dict()
    return rows


def run_import(export, decisions):
    """Import with the user's choices: {customer index: skip|overwrite|new}."""
    return [o.as_dict() for o in Importer(export, dry_run=False).run(decisions)]
