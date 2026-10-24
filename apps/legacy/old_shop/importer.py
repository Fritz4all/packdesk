"""Import of the previous webshop's database into PackDesk.

Reads the old database through a read-only connection and writes PackDesk records part by part, in
an order that keeps every link intact: catalogue → customers and addresses → contacts and logins →
orders and order lines → licences, options and extensions → invoices and payments → number counters.

Every old row is remembered in ImportedRecord (old table + old id → PackDesk record), so running the
import again updates what was imported before instead of creating it twice. Nothing in PackDesk is
deleted. Every row ends up in the report (CSV): created, updated, unchanged or skipped, with the reason.

A trial run does exactly the same inside a transaction that is rolled back at the end.
"""

import csv
import logging
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.db import connection, transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.models import User
from apps.customers.models import Contact, Country, Customer, CustomerAddress, CustomerType
from apps.invoices.models import Invoice, InvoicePayment
from apps.licences.models import (Category, HardwareClass, HardwareSystem, Licence, LicenceOption, OptionType,
                                  SupportPack, SupportPeriod, SupportService, Vendor)
from apps.numbering.models import NumberSequence
from apps.orders.models import Order, OrderLine, money

from ..connection import open_reader
from ..models import ImportedRecord, ImportRun
from .passwords import decrypt

log = logging.getLogger(__name__)
BATCH = 1000
HUNDRED = Decimal("100")

# Back-office roles of the previous webshop → PackDesk roles.
STAFF_ROLES = {
    "application_maintainer": "Beheerder",
    "employee_finance": "Financieel",
    "employee_service_imd": "Service",
}
STAFF_ROLE_DEFAULT = "Medewerker"
CUSTOMER_TYPES = {"reseller": "Reseller", "distributeur": "Distributeur"}


class _Rollback(Exception):
    pass


def _text(value):
    return "" if value is None else str(value).strip()


def _parse(value):
    """Dates may come back as text (e.g. from SQLite)."""
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    return value


def _aware(value):
    """Old datetimes are stored as UTC without a time zone (Rails)."""
    value = _parse(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else value.replace(tzinfo=dt_timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=dt_timezone.utc)
    return None


def _date(value):
    value = _parse(value)
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _decimal(value, default="0"):
    return Decimal(str(value)) if value not in (None, "") else Decimal(default)


PARTS = {
    "catalogue": gettext_lazy("Catalogue"), "customers": gettext_lazy("Customers"), "addresses": gettext_lazy("Addresses"),
    "contacts": gettext_lazy("Contacts"), "logins": gettext_lazy("Logins"), "staff roles": gettext_lazy("Staff roles"),
    "orders": gettext_lazy("Orders"), "order lines": gettext_lazy("Order lines"), "licences": gettext_lazy("Licences"),
    "licence extensions": gettext_lazy("Licence extensions"), "licence options": gettext_lazy("Licence options"),
    "invoices": gettext_lazy("Invoices"), "payments": gettext_lazy("Payments"),
    "number counters": gettext_lazy("Number counters"),
}
ACTIONS = {
    "created": gettext_lazy("created"), "updated": gettext_lazy("updated"), "unchanged": gettext_lazy("unchanged"),
    "skipped": gettext_lazy("skipped"), "linked": gettext_lazy("linked"),
}


class Report:
    """The full report: one CSV line per old row, plus counts per part."""

    COLUMNS = [gettext_lazy("Part"), gettext_lazy("Old table"), gettext_lazy("Old id"), gettext_lazy("Action"),
               "PackDesk", gettext_lazy("PackDesk id"), gettext_lazy("Name"), gettext_lazy("Note")]

    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, "w", newline="", encoding="utf-8")
        self.writer = csv.writer(self.file, delimiter=";")
        self.writer.writerow([str(c) for c in self.COLUMNS])
        self.counts = defaultdict(Counter)
        self.notes = []

    def add(self, part, table, old_id, action, model="", pk="", name="", note=""):
        self.counts[part][action] += 1
        self.writer.writerow([PARTS.get(part, part), table, old_id, ACTIONS.get(action, action), model, pk, name, note])

    def note(self, text):
        self.notes.append(text)

    def close(self):
        self.file.close()


class OldShopImport:
    def __init__(self, run):
        self.run = run
        self.db = run.database
        self.dry = run.dry_run
        self.map = defaultdict(dict)  # old table -> {old id: PackDesk pk}
        for rec in ImportedRecord.objects.filter(database=self.db).values_list("source_table", "source_id", "target_pk"):
            self.map[rec[0]][rec[1]] = rec[2]
        self.new_records = []
        self.objects = defaultdict(dict)  # old table -> {old id: PackDesk object} for this run

    # --- helpers -------------------------------------------------------------------------------

    def progress(self, text):
        """Written to a file next to the report: during a trial run the database transaction is not visible."""
        log.info("Import %s: %s", self.run.pk, text)
        progress_path(self.run).write_text(text)

    def rows(self, sql):
        return self.reader.rows(sql)

    def pk(self, table, old_id):
        return self.map[table].get(_text(old_id)) if old_id not in (None, "") else None

    def remember(self, table, old_id, obj):
        old_id = _text(old_id)
        self.objects[table][old_id] = obj
        if self.map[table].get(old_id) != obj.pk:
            self.map[table][old_id] = obj.pk
            self.new_records.append(ImportedRecord(database=self.db, source_table=table, source_id=old_id,
                                                   target_model=obj._meta.label_lower, target_pk=obj.pk))

    def sync(self, part, table, model, rows, build, name=lambda row, values: "", match=None, keep_on_update=()):
        """Create or update one PackDesk record per old row.

        build(row) returns (values, note): values is a dict of model attnames, or None to skip the row.
        match(values) may return an existing PackDesk object for rows that were never imported before.
        keep_on_update: fields that are only set when a record is created.
        """
        known = model.objects.in_bulk([pk for pk in self.map[table].values()])
        limits = {f.attname: f.max_length for f in model._meta.concrete_fields if getattr(f, "max_length", None)}
        to_create, to_update, update_fields = [], [], set()
        for row in rows:
            old_id = _text(row["id"])
            values, note = build(row)
            label = name(row, values or {})
            if values is not None:
                clipped = [f for f, v in values.items() if isinstance(v, str) and f in limits and len(v) > limits[f]]
                for f in clipped:
                    values[f] = values[f][:limits[f]]
                if clipped:
                    note = "; ".join(filter(None, [note, "shortened: " + ", ".join(clipped)]))
            if values is None:
                self.report.add(part, table, old_id, "skipped", model._meta.verbose_name, "", label, note)
                continue
            obj = known.get(self.map[table].get(old_id))
            if obj is None and match is not None:
                obj = match(values)
            if obj is None:
                to_create.append((old_id, model(**values), label, note))
                continue
            changed = [f for f, v in values.items() if f not in keep_on_update and getattr(obj, f) != v]
            for f in changed:
                setattr(obj, f, values[f])
            if changed:
                to_update.append(obj)
                update_fields.update(changed)
            self.remember(table, old_id, obj)
            self.report.add(part, table, old_id, "updated" if changed else "unchanged", model._meta.verbose_name,
                            obj.pk, label, note or (", ".join(changed) if changed else ""))
        for start in range(0, len(to_create), BATCH):
            chunk = to_create[start:start + BATCH]
            model.objects.bulk_create([obj for _old, obj, _l, _n in chunk])
            for old_id, obj, label, note in chunk:
                self.remember(table, old_id, obj)
                self.report.add(part, table, old_id, "created", model._meta.verbose_name, obj.pk, label, note)
        if to_update:
            model.objects.bulk_update(to_update, sorted(update_fields), batch_size=BATCH)
        self.flush_records()

    def flush_records(self):
        """Store the old → new links; a link that pointed elsewhere before is overwritten."""
        if not self.new_records:
            return
        options = {"update_conflicts": True, "update_fields": ["target_model", "target_pk"]}
        if connection.features.supports_update_conflicts_with_target:
            options["unique_fields"] = ["database", "source_table", "source_id"]
        ImportedRecord.objects.bulk_create(self.new_records, batch_size=BATCH, **options)
        self.new_records = []

    # --- the run -------------------------------------------------------------------------------

    def run_all(self):
        path = Path(settings.DATA_ROOT) / "imports" / "reports" / f"import-{self.run.pk}.csv"
        self.report = Report(path)
        try:
            with open_reader(self.db) as reader:
                self.reader = reader
                try:
                    with transaction.atomic():
                        self.catalogue()
                        self.customers()
                        self.contacts()
                        self.staff()
                        self.orders()
                        self.licences()
                        self.options()
                        self.invoices()
                        self.counters()
                        if self.dry:
                            raise _Rollback
                except _Rollback:
                    pass
        finally:
            self.report.close()
        return self.report

    # --- catalogue -----------------------------------------------------------------------------

    UNKNOWN = "Onbekend (vorige webshop)"

    def placeholder(self, model, **extra):
        """A recognisable stand-in for a catalogue item the old data refers to but no longer has."""
        fields = {f.name for f in model._meta.fields}
        names = {f: self.UNKNOWN for f in ("name", "name_nl") if f in fields}
        find = {"name_nl": self.UNKNOWN} if "name_nl" in fields else names or extra
        obj = model.objects.filter(**find).first()
        if obj is None:
            obj = model.objects.create(**names, **extra)
            self.report.note(_("Created '%(name)s' for %(kind)s: old rows refer to one that no longer exists. "
                               "Check these items after the import.") % {"name": self.UNKNOWN, "kind": model._meta.verbose_name})
        return obj.pk

    def catalogue(self):
        self.progress("catalogue")
        part = "catalogue"

        def by_name(model, field="name"):
            existing = {_text(getattr(o, f"{field}_nl", getattr(o, field))).lower(): o for o in model.objects.all()}
            return lambda values: existing.get(_text(values.get(f"{field}_nl", values.get(field))).lower())

        def translated(field, value):
            return {field: value, f"{field}_nl": value}

        self.sync(part, "hw_support_category", Category, self.rows("SELECT * FROM `hw_support_category`"),
                  lambda r: ({**translated("name", _text(r["description"])),
                              **translated("explanation", _text(r["explanation"]))}, ""),
                  name=lambda r, v: _text(r["description"]), match=by_name(Category))
        self.sync(part, "hw_class", HardwareClass, self.rows("SELECT * FROM `hw_class`"),
                  lambda r: ({**translated("name", _text(r["name"])), **translated("explanation", _text(r["explanation"])),
                              "position": r["position"] or 0}, ""),
                  name=lambda r, v: _text(r["name"]), match=by_name(HardwareClass))
        vendors = {o.name.lower(): o for o in Vendor.objects.all()}
        self.sync(part, "vendor", Vendor, self.rows("SELECT * FROM `vendor`"),
                  lambda r: ({"name": _text(r["name"]), "product_nr_regex": _text(r["product_nr_check"]),
                              **translated("product_nr_help", _text(r["product_nr_description"])),
                              "is_real_vendor": bool(r["real_vendor"]), "at_top": bool(r["at_top"]),
                              "legacy_id": _text(r["id"])}, ""),
                  name=lambda r, v: _text(r["name"]), match=lambda v: vendors.get(v["name"].lower()))
        self.sync(part, "hw_type", OptionType, self.rows("SELECT * FROM `hw_type`"),
                  lambda r: ({**translated("name", _text(r["name"])), "internal": bool(r["internal"]),
                              "is_monitor": _text(r["name"]).lower() in ("monitor", "beeldscherm")}, ""),
                  name=lambda r, v: _text(r["name"]), match=by_name(OptionType))
        # Which option types each category offers.
        for row in self.rows("SELECT * FROM `hw_support_category_hw_type`"):
            category, option = self.pk("hw_support_category", row["hw_support_category_id"]), self.pk("hw_type", row["hw_type_id"])
            if category and option:
                Category.option_types.through.objects.get_or_create(category_id=category, optiontype_id=option)
        self.report.note(_("hw_type_vendor (which brands supply which option types) is not used by PackDesk; not imported."))

        def system(r):
            vendor, hw_class = self.pk("vendor", r["vendor_id"]), self.pk("hw_class", r["hw_class_id"])
            note = "" if vendor and hw_class else f"brand or hardware class missing in the old data: '{self.UNKNOWN}'"
            vendor = vendor or self.placeholder(Vendor)
            hw_class = hw_class or self.placeholder(HardwareClass)
            return {"vendor_id": vendor, "hardware_class_id": hw_class, "name": _text(r["name"]),
                    "warranty_years": r["warranty"] or 0, "visible": bool(r["visible"]), "legacy_id": _text(r["id"])}, note

        self.sync(part, "hw_system", HardwareSystem, self.rows("SELECT * FROM `hw_system`"), system,
                  name=lambda r, v: _text(r["name"]))
        periods = {(p.years, p.post_warranty): p for p in SupportPeriod.objects.all()}
        self.sync(part, "hw_support_period", SupportPeriod, self.rows("SELECT * FROM `hw_support_period`"),
                  lambda r: ({"years": r["duration"] or 1, "post_warranty": bool(r["post_warranty"])}, ""),
                  name=lambda r, v: f"{r['duration']} {'post warranty' if r['post_warranty'] else ''}".strip(),
                  match=lambda v: periods.get((v["years"], v["post_warranty"])))
        services = {s.abbreviation.lower(): s for s in SupportService.objects.all()}
        self.sync(part, "hw_support_service", SupportService, self.rows("SELECT * FROM `hw_support_service`"),
                  lambda r: ({"abbreviation": _text(r["abbreviation"]), **translated("name", _text(r["service"])),
                              **translated("response", _text(r["response"])), "office_hours": bool(r["officehours"])}, ""),
                  name=lambda r, v: _text(r["service"]), match=lambda v: services.get(v["abbreviation"].lower()))

        def pack(r):
            needed = {"category_id": self.pk("hw_support_category", r["hw_support_category_id"]),
                      "hardware_class_id": self.pk("hw_class", r["hw_class_id"]),
                      "service_id": self.pk("hw_support_service", r["hw_support_service_id"]),
                      "period_id": self.pk("hw_support_period", r["hw_support_period_id"])}
            note = "" if all(needed.values()) else \
                f"category, class, service level or period missing in the old data: '{self.UNKNOWN}'"
            needed["category_id"] = needed["category_id"] or self.placeholder(Category)
            needed["hardware_class_id"] = needed["hardware_class_id"] or self.placeholder(HardwareClass)
            needed["service_id"] = needed["service_id"] or self.placeholder(SupportService, abbreviation="?")
            needed["period_id"] = needed["period_id"] or self.placeholder(SupportPeriod, years=0, post_warranty=False)
            text = _text(r["abbreviation"]) or _text(r["code"])
            return {**needed, "code": _text(r["code"]), **translated("description", text),
                    "price": _decimal(r["price"]), "enabled": bool(r["enabled"]), "remark": _text(r["remark"]),
                    "registration_required": bool(r["registration_required"]), "requires_monitor": bool(r["monitor"]),
                    "max_internal_options": r["n_internal_options"] or 0, "max_external_options": r["n_external_options"] or 0,
                    "legacy_id": _text(r["id"])}, note

        self.sync(part, "hw_support_pack", SupportPack, self.rows("SELECT * FROM `hw_support_pack`"), pack,
                  name=lambda r, v: _text(r["code"]) or _text(r["abbreviation"]), keep_on_update=("cost_price",))
        self.report.note(_("hw_pack_prolongation (which pack extends which) is not imported: PackDesk chooses extension "
                         "packs itself (same category and hardware class)."))

    # --- customers -----------------------------------------------------------------------------

    def customers(self):
        self.progress("customers")
        types = {t.name.lower(): t for t in CustomerType.objects.all()}
        for kind, name in CUSTOMER_TYPES.items():
            if name.lower() not in types:
                types[name.lower()] = CustomerType.objects.create(name=name, name_nl=name, is_reseller=kind == "reseller")
        countries = {}
        for c in Country.objects.all():
            for value in (c.code, c.name, getattr(c, "name_nl", ""), getattr(c, "name_en", ""), getattr(c, "name_de", "")):
                if value:
                    countries[value.lower()] = c.pk
        addresses = {_text(a["id"]): a for a in self.rows("SELECT * FROM `address`")}
        self.addresses = addresses
        self.countries = countries
        rows = self.rows("SELECT * FROM `customer`")
        self.customer_rows = {_text(r["id"]): r for r in rows}

        def customer(r):
            extra = []
            if _text(r["fax"]):
                extra.append(f"Fax: {_text(r['fax'])}")
            if r["credit_parts"] not in (None, ""):
                extra.append(f"Krediet onderdelen: {r['credit_parts']}")
            for field in ("text_failure_24", "text_failure_office"):
                if _text(r[field]):
                    extra.append(f"{field}: {_text(r[field])}")
            for field in ("margin_ps_hardware", "margin_ps_support", "margin_ps_supplies", "margin_ps_prints"):
                if r[field] not in (None, ""):
                    extra.append(f"{field}: {r[field]}")
            remark = "\n".join(filter(None, [_text(r["remark"]), "\n".join(extra) and "Uit de vorige webshop:\n" + "\n".join(extra)]))
            status = (Customer.Status.BLOCKED if r["deleted"] else
                      Customer.Status.ACTIVE if r["activated"] else Customer.Status.PENDING)
            customer_type = types.get(CUSTOMER_TYPES.get(_text(r["kind"]).lower(), _text(r["kind"])).lower())
            return {
                "legacy_id": _text(r["id"]), "number": _text(r["number_deb"]) or None, "name": _text(r["name"]),
                "customer_type_id": customer_type.pk if customer_type else None, "status": status,
                "vat_number": _text(r["number_tax"]), "phone": _text(r["telephone"]),
                "email": _text(r["email_packs"]) or _text(r["email_invoice"]), "email_orders": _text(r["email_packs"]),
                "email_parts": _text(r["email_parts"]), "email_invoices": _text(r["email_invoice"]),
                "margin_packs": _decimal(r["margin_packs"]), "margin_parts": _decimal(r["margin_parts"]),
                "no_pack_invoice": bool(r["skip_hw_support_pack_invoice"]), "remark": remark,
            }, ""

        existing = {c.number: c for c in Customer.objects.exclude(number__isnull=True)}
        self.sync("customers", "customer", Customer, rows, customer, name=lambda r, v: _text(r["name"]),
                  match=lambda v: existing.get(v["number"]) if v["number"] else None)
        # created_at is set automatically on create; put the old date back.
        for old_id, obj in self.objects["customer"].items():
            created = _aware(self.customer_rows[old_id]["created_at"])
            if created and obj.created_at != created:
                Customer.objects.filter(pk=obj.pk).update(created_at=created)

        address_rows = []
        for old_id, r in self.customer_rows.items():
            for kind, column in ((CustomerAddress.Kind.MAIN, "address"), (CustomerAddress.Kind.INVOICE, "address_invoice"),
                                 (CustomerAddress.Kind.DELIVERY, "address_delivery")):
                address_id = _text(r[column])
                if not address_id or (kind != CustomerAddress.Kind.MAIN and address_id == _text(r["address"])):
                    continue
                address_rows.append({"id": f"{old_id}:{kind}", "customer": old_id, "kind": kind,
                                     "address": addresses.get(address_id)})

        def address(row):
            a, customer_pk = row["address"], self.pk("customer", row["customer"])
            if a is None or customer_pk is None:
                return None, "address or customer not found"
            note = "" if not _text(a["country"]) or countries.get(_text(a["country"]).lower()) else f"country '{_text(a['country'])}' not known"
            return {"customer_id": customer_pk, "kind": row["kind"], "line1": _text(a["line1"]),
                    "postal_code": _text(a["zipcode"]), "city": _text(a["city"]),
                    "country_id": countries.get(_text(a["country"]).lower())}, note

        existing = {(a.customer_id, a.kind): a for a in CustomerAddress.objects.all()}
        self.sync("addresses", "customer_address", CustomerAddress, address_rows, address,
                  name=lambda r, v: f"{v.get('line1', '')} {v.get('city', '')}".strip(),
                  match=lambda v: existing.get((v["customer_id"], v["kind"])))

    # --- contacts and logins -------------------------------------------------------------------

    def _password_hashes(self, users):
        """PackDesk hashes for the old passwords (hashing is slow by design, so it runs in parallel)."""
        if self.dry:
            return {u["id"]: make_password(None) for u in users}  # trial: no need to hash

        def one(user):
            plain = decrypt(user["crypted_password"], user["salt"])
            return user["id"], make_password(plain) if plain else make_password(None)

        with ThreadPoolExecutor(max_workers=8) as pool:
            return dict(pool.map(one, users))

    def _logins(self, user_rows, kind, active):
        """Create PackDesk logins for old users that have none yet; returns {old user id: pk}."""
        emails = {u.lower(): pk for u, pk in User.objects.values_list("email", "pk")}
        mapped = {old: pk for old, pk in self.map["user"].items()}
        new = []
        seen = set()
        for u in user_rows:
            old_id, email = _text(u["id"]), _text(u["email"]).lower()
            if old_id in mapped:
                self.report.add("logins", "user", old_id, "unchanged", "user", mapped[old_id], email,
                                "already imported; password not changed")
                continue
            if not email:
                self.report.add("logins", "user", old_id, "skipped", "user", "", "", "no email address")
                continue
            if email in emails or email in seen:
                self.report.add("logins", "user", old_id, "skipped", "user", emails.get(email, ""), email,
                                "email address already used by another login (PackDesk allows one login per address)")
                continue
            seen.add(email)
            new.append(u)
        hashes = self._password_hashes(new)
        objs = []
        for u in new:
            objs.append((_text(u["id"]), User(
                email=_text(u["email"]).lower(), username=f"old-{_text(u['id'])}"[:150],
                first_name=_text(u["name_first"])[:150], last_name=_text(u["name_last"])[:150], kind=kind,
                is_staff=kind == User.Kind.STAFF, is_active=active(u), password=hashes[u["id"]],
                last_login=_aware(u["last_login"]), date_joined=_aware(u["created_at"]) or timezone.now())))
        for start in range(0, len(objs), BATCH):
            chunk = objs[start:start + BATCH]
            User.objects.bulk_create([o for _id, o in chunk])
            for old_id, obj in chunk:
                self.remember("user", old_id, obj)
                self.report.add("logins", "user", old_id, "created", "user", obj.pk, obj.email,
                                "own password from the previous webshop" if not self.dry else "")
        self.flush_records()

    def contacts(self):
        self.progress("contacts and logins")
        users = {_text(u["id"]): u for u in self.rows("SELECT * FROM `user`")}
        self.user_rows = users
        employees = self.rows("SELECT * FROM `employee`")
        live = [e for e in employees if not e["deleted"]]
        for e in employees:
            if e["deleted"]:
                self.report.add("contacts", "employee", _text(e["id"]), "skipped", "contact", "",
                                "", "deleted in the previous webshop")
        customer_users = [users[_text(e["user_id"])] for e in live if _text(e["user_id"]) in users]
        self._logins(customer_users, User.Kind.CUSTOMER,
                     active=lambda u: not u["deleted"])
        primary = {_text(r["contact"]) for r in self.customer_rows.values() if _text(r["contact"])}
        linked = set(Contact.objects.exclude(user__isnull=True).values_list("user_id", flat=True))

        def contact(e):
            u = users.get(_text(e["user_id"]))
            customer_pk = self.pk("customer", e["customer_id"])
            if u is None or customer_pk is None:
                return None, "login or customer not found"
            user_pk = self.pk("user", u["id"])
            note = ""
            if user_pk is None:
                note = "no login (see logins)"
            elif user_pk in linked and self.pk("employee", e["id"]) is None:
                user_pk, note = None, "login already belongs to another contact"
            if user_pk:
                linked.add(user_pk)
            gender = _text(e["gender"]).lower()
            return {"customer_id": customer_pk, "user_id": user_pk, "legacy_id": _text(e["id"]),
                    "salutation": Contact.Salutation.MR if gender == "male" else Contact.Salutation.MRS if gender == "female" else "",
                    "initials": _text(u["initials"])[:20], "first_name": _text(u["name_first"]),
                    "last_name": _text(u["name_last"]) or _text(u["login"]), "email": _text(u["email"]),
                    "phone": _text(e["telephone"]), "function": _text(e["function"]),
                    "department": _text(e["department"]), "remark": _text(e["remark"]),
                    "is_primary": _text(e["id"]) in primary}, note

        self.sync("contacts", "employee", Contact, live, contact,
                  name=lambda e, v: f"{v.get('first_name', '')} {v.get('last_name', '')}".strip())

    def staff(self):
        self.progress("staff logins")
        roles = defaultdict(list)
        role_names = {_text(r["id"]): _text(r["name"]) for r in self.rows("SELECT * FROM `role`")}
        for row in self.rows("SELECT * FROM `user_role`"):
            roles[_text(row["user_id"])].append(role_names.get(_text(row["role_id"]), ""))
        employee_users = {_text(e["user_id"]) for e in self.rows("SELECT `user_id` FROM `employee`")}
        staff_rows = [u for old_id, u in self.user_rows.items() if old_id not in employee_users]
        self._logins(staff_rows, User.Kind.STAFF, active=lambda u: not u["deleted"])
        groups = {g.name: g for g in Group.objects.all()}
        for u in staff_rows:
            pk = self.pk("user", u["id"])
            if not pk or self.dry and pk is None:
                continue
            names = [STAFF_ROLES.get(r) for r in roles[_text(u["id"])] if STAFF_ROLES.get(r)]
            group = groups.get(names[0] if names else STAFF_ROLE_DEFAULT)
            user = User.objects.get(pk=pk)
            if group and not user.groups.exists():
                user.groups.add(group)
                self.report.add("staff roles", "user_role", _text(u["id"]), "created", "role", group.pk, group.name,
                                "old roles: " + ", ".join(roles[_text(u["id"])]))

    # --- orders and licences -------------------------------------------------------------------

    def orders(self):
        self.progress("orders")
        employees = {_text(e["id"]): e for e in self.rows("SELECT `id`, `customer_id`, `user_id` FROM `employee`")}
        self.employees = employees
        entries = defaultdict(list)
        entry_rows = self.rows("SELECT * FROM `hw_support_order_entry`")
        for e in entry_rows:
            entries[_text(e["hw_support_order_id"])].append(e)
        orders = self.rows("SELECT * FROM `hw_support_order`")

        def order(o):
            employee = employees.get(_text(o["employee_id"]))
            customer_pk = self.pk("customer", employee["customer_id"]) if employee else None
            if customer_pk is None:
                return None, "customer not found"
            gross = money(sum((_decimal(e["price_each"]) * (e["n_packs"] or 0) for e in entries[_text(o["id"])]), Decimal("0")))
            pct, vat_rate = _decimal(o["discount"]), _decimal(o["tax"])
            discount = money(gross * pct / HUNDRED)
            vat = money((gross - discount) * vat_rate / HUNDRED)
            return {"legacy_id": _text(o["id"]), "number": _text(o["id"]), "customer_id": customer_pk,
                    "created_by_id": self.pk("user", employee["user_id"]) if employee else None,
                    "reference": _text(o["reference"]), "gross": gross, "discount_pct": pct, "discount": discount,
                    "net": gross - discount, "vat_rate": vat_rate, "vat": vat, "total": gross - discount + vat,
                    "send_boxes": bool(o["boxes"]), "boxes_sent": bool(o["boxes_printed"]),
                    "delivery_name": _text(o["company_name"]), "delivery_contact": _text(o["company_contact"]),
                    "delivery_address": _text(o["company_address"]), "delivery_postal_code": _text(o["company_zipcode"]),
                    "delivery_city": _text(o["company_city"])}, ""

        self.sync("orders", "hw_support_order", Order, orders, order, name=lambda o, v: f"#{o['id']}")
        created = {_text(o["id"]): _aware(o["created_at"]) for o in orders}
        for old_id, obj in self.objects["hw_support_order"].items():
            if created.get(old_id) and obj.created_at != created[old_id]:
                Order.objects.filter(pk=obj.pk).update(created_at=created[old_id])
        packs = {p.pk: p for p in SupportPack.objects.all()}

        def line(e):
            order_pk, pack_pk = self.pk("hw_support_order", e["hw_support_order_id"]), self.pk("hw_support_pack", e["hw_support_pack_id"])
            if order_pk is None or pack_pk is None:
                return None, "order or service pack not found"
            quantity, price = e["n_packs"] or 0, _decimal(e["price_each"])
            return {"order_id": order_pk, "pack_id": pack_pk, "description": str(packs[pack_pk])[:250],
                    "quantity": quantity, "unit_price": price, "line_total": money(price * quantity),
                    "reference": _text(e["reference"])}, ""

        self.sync("order lines", "hw_support_order_entry", OrderLine, entry_rows, line,
                  name=lambda e, v: _text(e["reference"]))
        self.entry_rows = {_text(e["id"]): e for e in entry_rows}

    def licences(self):
        self.progress("licences")
        resellers = {_text(r["id"]): r for r in self.rows("SELECT * FROM `hw_support_pack_license_reseller`")}
        systems = dict(HardwareSystem.objects.values_list("pk", "vendor_id"))
        rows = self.rows("SELECT * FROM `hw_support_pack_license`")
        taken = set(Licence.objects.values_list("full_number", flat=True))
        own = set(Licence.objects.filter(pk__in=self.map["hw_support_pack_license"].values())
                  .values_list("full_number", flat=True))
        order_customers = dict(Order.objects.filter(pk__in=self.map["hw_support_order"].values())
                               .values_list("pk", "customer_id"))
        seen = set()

        def licence(r):
            entry = self.entry_rows.get(_text(r["hw_support_order_entry_id"]))
            order_pk = self.pk("hw_support_order", entry["hw_support_order_id"]) if entry else None
            pack_pk = self.pk("hw_support_pack", entry["hw_support_pack_id"]) if entry else None
            customer_pk = order_customers.get(order_pk)
            if not (pack_pk and customer_pk):
                return None, "order, service pack or customer not found"
            full = f"{_text(r['license_nr'])}{_text(r['license_nr_suffix'])}-{r['license_sequence_nr']}"
            if full in seen or (full in taken and full not in own and self.pk("hw_support_pack_license", r["id"]) is None):
                return None, f"licence number {full} occurs more than once"
            seen.add(full)
            system_pk = self.pk("hw_system", r["hw_system_id"])
            reseller = resellers.get(_text(r["hw_support_pack_license_reseller_id"]))
            address = self.addresses.get(_text(reseller["address_id"])) if reseller else None
            return {"legacy_id": _text(r["id"]), "number": _text(r["license_nr"]), "suffix": _text(r["license_nr_suffix"]),
                    "sequence": r["license_sequence_nr"] or 1, "full_number": full, "pack_id": pack_pk,
                    "customer_id": customer_pk, "order_line_id": self.pk("hw_support_order_entry", r["hw_support_order_entry_id"]),
                    "registered_on": _aware(r["registered_on"]), "start_date": _date(r["start_date"]),
                    "end_date": _date(r["end_date"]), "purchase_date": _date(r["purchase_date"]),
                    "system_id": system_pk, "vendor_id": systems.get(system_pk) if system_pk else None,
                    "description": _text(r["description"]), "product_nr": _text(r["product_nr"]),
                    "serial_nr": _text(r["serial_nr"]), "end_customer_email": _text(r["email"]),
                    "end_customer_reference": _text(r["reference"]), "memo": _text(r["memo"]),
                    "reseller_name": _text(reseller["name"]) if reseller else "",
                    "reseller_phone": _text(reseller["phone"]) if reseller else "",
                    "reseller_address": _text(address["line1"]) if address else "",
                    "reseller_postal_code": _text(address["zipcode"]) if address else "",
                    "reseller_city": _text(address["city"]) if address else ""}, ""

        self.sync("licences", "hw_support_pack_license", Licence, rows, licence, name=lambda r, v: v.get("full_number", ""))
        # Extensions: licence → licence it continues, and the order line that extended it.
        self.progress("licence extensions")
        links, line_links = [], []
        for r in rows:
            this, previous = self.pk("hw_support_pack_license", r["id"]), self.pk("hw_support_pack_license", r["prolongation_of"])
            if this and previous:
                links.append(Licence(pk=this, prolongation_of_id=previous))
                entry = self.pk("hw_support_order_entry", r["hw_support_order_entry_id"])
                if entry:
                    line_links.append(OrderLine(pk=entry, extends_id=previous))
            elif _text(r["prolongation_of"]):
                self.report.add("licence extensions", "hw_support_pack_license", _text(r["id"]), "skipped",
                                "licence", this or "", "", "previous licence not found")
        Licence.objects.bulk_update(links, ["prolongation_of"], batch_size=BATCH)
        OrderLine.objects.bulk_update(line_links, ["extends"], batch_size=BATCH)
        self.report.counts["licence extensions"]["linked"] += len(links)

    def options(self):
        self.progress("licence options")
        rows = self.rows("SELECT * FROM `hw_support_pack_license_option`")
        vendors = set(Vendor.objects.values_list("pk", flat=True))

        def option(r):
            if r["is_deleted"]:
                return None, "deleted in the previous webshop"
            licence_pk, type_pk = self.pk("hw_support_pack_license", r["hw_support_pack_license_id"]), self.pk("hw_type", r["hw_type_id"])
            if licence_pk is None or type_pk is None:
                return None, "licence or option type not found"
            vendor_pk = self.pk("vendor", r["vendor_id"])
            return {"licence_id": licence_pk, "option_type_id": type_pk,
                    "vendor_id": vendor_pk if vendor_pk in vendors else None, "description": _text(r["description"]),
                    "product_nr": _text(r["product_nr"]), "serial_nr": _text(r["serial_nr"])}, ""

        self.sync("licence options", "hw_support_pack_license_option", LicenceOption, rows, option,
                  name=lambda r, v: _text(r["serial_nr"]))

    # --- invoices --------------------------------------------------------------------------------

    def invoices(self):
        self.progress("invoices")
        part_order_customers = {
            _text(r["id"]): r["customer_id"] for r in self.rows(
                "SELECT p.`id`, e.`customer_id` FROM `part_order` p LEFT JOIN `employee` e ON e.`id` = p.`employee_id`")}
        rows = self.rows("SELECT * FROM `invoice`")
        archive = {i.number: i for i in Invoice.objects.all()}
        orders = Order.objects.in_bulk(list(self.map["hw_support_order"].values()))
        customers = Customer.objects.in_bulk(list(self.map["customer"].values()))
        invoiced_orders = dict(Invoice.objects.exclude(order__isnull=True).values_list("order_id", "pk"))

        def invoice(r):
            order_pk = self.pk("hw_support_order", r["hw_support_order_id"])
            order = orders.get(order_pk)
            customer_pk = order.customer_id if order else self.pk("customer", part_order_customers.get(_text(r["part_order_id"])))
            customer = customers.get(customer_pk)
            values = {"number": _text(r["invoice_id"]), "order_id": order_pk, "customer_id": customer_pk,
                      "paid_on": _date(r["payed_at"])}
            note = "spare parts order: linked to the order in phase 2" if _text(r["part_order_id"]) else ""
            existing = archive.get(values["number"])
            if existing is None:
                values.update({"issued_on": _date(r["created_at"]) or date(1970, 1, 1),
                               "customer_name": customer.name if customer else "",
                               "customer_number": (customer.number or "") if customer else ""})
                if order:
                    values.update({"gross": order.gross, "discount_pct": order.discount_pct, "discount": order.discount,
                                   "net": order.net, "vat_rate": order.vat_rate, "vat": order.vat, "total": order.total})
                note = note or "no PDF in the archive"
            # An order has at most one invoice in PackDesk.
            this_invoice = existing.pk if existing else f"new:{values['number']}"
            if order_pk and invoiced_orders.setdefault(order_pk, this_invoice) != this_invoice:
                values["order_id"] = None
                note = "order already has another invoice"
            return values, note

        self.sync("invoices", "invoice", Invoice, rows, invoice, name=lambda r, v: _text(r["invoice_id"]),
                  match=lambda v: archive.get(v["number"]))
        self.progress("payments")
        payments = self.rows("SELECT * FROM `invoice_payment`")
        self.sync("payments", "invoice_payment", InvoicePayment, payments,
                  lambda p: ({"invoice_id": self.pk("invoice", p["invoice_id"]), "amount": _decimal(p["amount"]),
                              "paid_at": _aware(p["created_at"]) or timezone.now(),
                              "recorded_by_id": self.pk("user", p["user_id"])}, "")
                  if self.pk("invoice", p["invoice_id"]) else (None, "invoice not found"),
                  name=lambda p, v: str(p["amount"]))

    # --- counters --------------------------------------------------------------------------------

    def counters(self):
        self.progress("number counters")
        tops = {
            "invoice": [int(n) for n in Invoice.objects.values_list("number", flat=True) if str(n).isdigit()],
            "order": [int(n) for n in Order.objects.values_list("number", flat=True) if str(n).isdigit()],
            "customer": [int(n) for n in Customer.objects.exclude(number__isnull=True).values_list("number", flat=True)
                         if str(n).isdigit()],
        }
        for key, numbers in tops.items():
            seq = NumberSequence.objects.filter(key=key).first()
            if not seq or not numbers or not re.fullmatch(r"\{nr(:\d+)?\}", seq.pattern):
                self.report.note(_("Counter %(key)s: not changed (pattern %(pattern)s); check it yourself.")
                                 % {"key": key, "pattern": seq.pattern if seq else "-"})
                continue
            highest = max(numbers)
            if seq.next_number <= highest:
                if not self.dry:
                    seq.correct(highest + 1, self.run.started_by, "Import vorige webshop: hoogste nummer + 1", highest)
                self.report.add("number counters", "number_sequence", key, "updated", "number sequence", seq.pk,
                                key, f"next number {seq.next_number} → {highest + 1}")
            else:
                self.report.add("number counters", "number_sequence", key, "unchanged", "number sequence", seq.pk, key,
                                f"next number {seq.next_number} is already above {highest}")
        self.report.note(_("Licence numbers of the previous webshop have different formats; the licence counter is not changed. "
                         "Check it under Number sequences."))


def progress_path(run):
    return Path(settings.DATA_ROOT) / "imports" / "reports" / f"import-{run.pk}.progress"


def run_import(run):
    """Run an ImportRun and store its outcome."""
    try:
        report = OldShopImport(run).run_all()
    except Exception as exc:  # the run is marked failed with the reason; details in the log
        log.exception("Import %s failed", run.pk)
        ImportRun.objects.filter(pk=run.pk).update(status=ImportRun.Status.FAILED, notes=str(exc)[:5000],
                                                   finished_at=timezone.now(), progress="")
        return
    progress_path(run).unlink(missing_ok=True)
    counts = {part: dict(c) for part, c in report.counts.items()}
    ImportRun.objects.filter(pk=run.pk).update(
        status=ImportRun.Status.DONE, finished_at=timezone.now(), counts=counts, notes="\n".join(report.notes),
        report_file=str(report.path.relative_to(settings.DATA_ROOT)), progress="")
