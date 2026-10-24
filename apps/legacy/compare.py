"""Compare the previous webshop's database with PackDesk: what is where.

Per part (customers, contacts, licences, ...) the rows of both sides are matched:
first on the ID from the old system (stored in PackDesk as `legacy_id`), then on a natural
key such as the customer number, licence number or invoice number. The result shows rows
only in the old database, only in PackDesk, and matched rows whose values differ.

Rows marked as deleted in the previous webshop are left out. Nothing is ever written to the old database.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.customers.models import Contact, Customer, CustomerAddress
from apps.invoices.models import Invoice
from apps.licences.models import Licence, LicenceOption
from apps.numbering.models import NumberSequence
from apps.orders.models import Order

MAX_LISTED = 500


# --- normalising values -------------------------------------------------------------------------


def _text(value):
    return "" if value is None else str(value).strip()


def _email(value):
    return _text(value).lower()


def _decimal(value):
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return Decimal("0.00")


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _bool(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "t", "yes")
    return bool(value)


NORMALISE = {"text": _text, "email": _email, "decimal": _decimal, "date": _date, "bool": _bool}


def show(value):
    if value is None or value == "":
        return "—"
    if value is True:
        return str(_("yes"))
    if value is False:
        return str(_("no"))
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return str(value)


# --- what is compared ---------------------------------------------------------------------------


@dataclass
class Field:
    label: str
    old: str
    new: str
    kind: str = "text"


@dataclass
class Part:
    key: str
    label: str
    old_sql: str
    new_rows: callable
    natural_old: callable
    fields: list
    label_old: callable
    label_new: callable
    admin_url: str = ""
    admin_pk: str = "pk"  # which value of a PackDesk row the admin link uses
    note: str = ""
    uses_legacy_id: bool = True


def _customers():
    main = {a.customer_id: a for a in CustomerAddress.objects.filter(kind=CustomerAddress.Kind.MAIN)}
    for c in Customer.objects.values("pk", "legacy_id", "number", "name", "vat_number", "phone", "email_orders",
                                      "email_parts", "email_invoices", "margin_packs", "margin_parts",
                                      "no_pack_invoice", "status"):
        address = main.get(c["pk"])
        c.update(natural=_text(c["number"]), active=c["status"] == Customer.Status.ACTIVE,
                 line1=address.line1 if address else "", postal_code=address.postal_code if address else "",
                 city=address.city if address else "")
        yield c


def _contacts():
    for c in Contact.objects.values("pk", "legacy_id", "email", "first_name", "last_name", "phone", "function",
                                     "department", "customer_id", "customer__legacy_id"):
        c["natural"] = _email(c["email"])
        yield c


def _users():
    for u in User.objects.values("pk", "email", "first_name", "last_name", "kind"):
        u.update(legacy_id="", natural=_email(u["email"]))
        yield u


def _orders():
    for o in Order.objects.values("pk", "legacy_id", "number", "reference", "discount_pct", "customer__legacy_id"):
        o["natural"] = ""
        yield o


def _licences():
    for lic in Licence.objects.values("pk", "legacy_id", "full_number", "start_date", "end_date", "registered_on",
                                      "serial_nr", "product_nr", "description", "purchase_date", "end_customer_email",
                                      "end_customer_reference", "memo", "customer__legacy_id",
                                      "prolongation_of__legacy_id"):
        lic["natural"] = _text(lic["full_number"]).upper()
        yield lic


def _options():
    for o in LicenceOption.objects.values("pk", "licence__legacy_id", "licence__full_number", "serial_nr",
                                          "product_nr", "description"):
        o.update(legacy_id="", natural=_option_key(o["licence__legacy_id"], o["serial_nr"], o["product_nr"]))
        yield o


def _option_key(licence, serial, product):
    return "|".join([_text(licence), _text(serial).upper(), _text(product).upper()])


def _invoices():
    for i in Invoice.objects.values("pk", "number", "paid_on", "order__legacy_id", "customer_name"):
        i.update(legacy_id="", natural=_number(i["number"]))
        yield i


def _number(value):
    """Invoice numbers: digits without leading zeros, so 0001017494 and 1017494 match."""
    text = _text(value)
    return text.lstrip("0") or text if text.isdigit() else text


ARCHIVE_NUMBER = re.compile(r"(\d+)")


def _archive_files():
    folder = settings.DOCUMENT_ARCHIVE_DIR
    if not folder or not os.path.isdir(folder):
        return
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf") and (m := ARCHIVE_NUMBER.search(name)):
            yield {"pk": None, "legacy_id": "", "natural": _number(m.group(1)), "file": name}


def _full_number(row):
    return f"{_text(row['license_nr'])}{_text(row['license_nr_suffix'])}-{_text(row['license_sequence_nr'])}".upper()


PARTS = [
    Part(
        key="customers", label=_("Customers"),
        old_sql=("SELECT c.`id`, c.`name`, c.`number_deb`, c.`number_tax`, c.`telephone`, c.`email_packs`, "
                 "c.`email_parts`, c.`email_invoice`, c.`margin_packs`, c.`margin_parts`, "
                 "c.`skip_hw_support_pack_invoice`, c.`activated`, a.`line1`, a.`zipcode`, a.`city` "
                 "FROM `customer` c LEFT JOIN `address` a ON a.`id` = c.`address` WHERE c.`deleted` = 0"),
        new_rows=_customers, natural_old=lambda r: _text(r["number_deb"]),
        fields=[
            Field(_("Name"), "name", "name"), Field(_("Customer number"), "number_deb", "number"),
            Field(_("VAT number"), "number_tax", "vat_number"), Field(_("Phone"), "telephone", "phone"),
            Field(_("Email for orders"), "email_packs", "email_orders", "email"),
            Field(_("Email for spare parts"), "email_parts", "email_parts", "email"),
            Field(_("Email for invoices"), "email_invoice", "email_invoices", "email"),
            Field(_("Margin service packs"), "margin_packs", "margin_packs", "decimal"),
            Field(_("Margin spare parts"), "margin_parts", "margin_parts", "decimal"),
            Field(_("No invoice for service packs"), "skip_hw_support_pack_invoice", "no_pack_invoice", "bool"),
            Field(_("Active"), "activated", "active", "bool"),
            Field(_("Address"), "line1", "line1"), Field(_("Postal code"), "zipcode", "postal_code"),
            Field(_("City"), "city", "city"),
        ],
        label_old=lambda r: f"{_text(r['name'])} ({_text(r['number_deb']) or '—'})",
        label_new=lambda r: f"{r['name']} ({r['number'] or '—'})",
        admin_url="admin:customers_customer_change",
    ),
    Part(
        key="contacts", label=_("Contacts"),
        old_sql=("SELECT e.`id`, e.`customer_id`, e.`telephone`, e.`function`, e.`department`, "
                 "u.`email`, u.`name_first`, u.`name_last` "
                 "FROM `employee` e LEFT JOIN `user` u ON u.`id` = e.`user_id` WHERE e.`deleted` = 0"),
        new_rows=_contacts, natural_old=lambda r: _email(r["email"]),
        fields=[
            Field(_("Email"), "email", "email", "email"), Field(_("First name"), "name_first", "first_name"),
            Field(_("Last name"), "name_last", "last_name"), Field(_("Phone"), "telephone", "phone"),
            Field(_("Function"), "function", "function"), Field(_("Department"), "department", "department"),
            Field(_("Customer (old ID)"), "customer_id", "customer__legacy_id"),
        ],
        label_old=lambda r: f"{_text(r['name_first'])} {_text(r['name_last'])} <{_text(r['email'])}>".strip(),
        label_new=lambda r: f"{r['first_name']} {r['last_name']} <{r['email']}>".strip(),
        admin_url="admin:customers_customer_change", admin_pk="customer_id",
    ),
    Part(
        key="users", label=_("Logins"),
        old_sql="SELECT u.`id`, u.`email`, u.`name_first`, u.`name_last` FROM `user` u WHERE u.`deleted` = 0",
        new_rows=_users, natural_old=lambda r: _email(r["email"]), uses_legacy_id=False,
        fields=[Field(_("First name"), "name_first", "first_name"), Field(_("Last name"), "name_last", "last_name")],
        label_old=lambda r: _text(r["email"]) or "—", label_new=lambda r: r["email"],
        admin_url="admin:accounts_user_change",
        note=_("Matched on email address. Both sides include staff logins."),
    ),
    Part(
        key="orders", label=_("Orders"),
        old_sql=("SELECT o.`id`, o.`reference`, o.`discount`, e.`customer_id` FROM `hw_support_order` o "
                 "LEFT JOIN `employee` e ON e.`id` = o.`employee_id`"),
        new_rows=_orders, natural_old=lambda r: "",
        fields=[
            Field(_("Reference"), "reference", "reference"),
            Field(_("Discount (%)"), "discount", "discount_pct", "decimal"),
            Field(_("Customer (old ID)"), "customer_id", "customer__legacy_id"),
        ],
        label_old=lambda r: f"#{r['id']} {_text(r['reference'])}".strip(),
        label_new=lambda r: f"{r['number']} {r['reference']}".strip(),
        admin_url="admin:orders_order_change",
    ),
    Part(
        key="licences", label=_("Licences"),
        old_sql=("SELECT l.`id`, l.`license_nr`, l.`license_nr_suffix`, l.`license_sequence_nr`, l.`start_date`, "
                 "l.`end_date`, l.`registered_on`, l.`serial_nr`, l.`product_nr`, l.`description`, l.`purchase_date`, "
                 "l.`email`, l.`reference`, l.`memo`, l.`prolongation_of`, e.`customer_id` "
                 "FROM `hw_support_pack_license` l "
                 "LEFT JOIN `hw_support_order_entry` oe ON oe.`id` = l.`hw_support_order_entry_id` "
                 "LEFT JOIN `hw_support_order` o ON o.`id` = oe.`hw_support_order_id` "
                 "LEFT JOIN `employee` e ON e.`id` = o.`employee_id`"),
        new_rows=_licences, natural_old=_full_number,
        fields=[
            Field(_("Licence number"), "full_number", "full_number"),
            Field(_("Start date"), "start_date", "start_date", "date"),
            Field(_("End date"), "end_date", "end_date", "date"),
            Field(_("Registered on"), "registered_on", "registered_on", "date"),
            Field(_("Serial number"), "serial_nr", "serial_nr"), Field(_("Article number"), "product_nr", "product_nr"),
            Field(_("Description"), "description", "description"),
            Field(_("Purchase date"), "purchase_date", "purchase_date", "date"),
            Field(_("Email end customer"), "email", "end_customer_email", "email"),
            Field(_("Reference"), "reference", "end_customer_reference"), Field(_("Memo"), "memo", "memo"),
            Field(_("Extension of (old ID)"), "prolongation_of", "prolongation_of__legacy_id"),
            Field(_("Customer (old ID)"), "customer_id", "customer__legacy_id"),
        ],
        label_old=_full_number, label_new=lambda r: r["full_number"],
        admin_url="admin:licences_licence_change",
    ),
    Part(
        key="options", label=_("Licence options"),
        old_sql=("SELECT o.`id`, o.`hw_support_pack_license_id`, o.`serial_nr`, o.`product_nr`, o.`description` "
                 "FROM `hw_support_pack_license_option` o WHERE o.`is_deleted` = 0"),
        new_rows=_options, uses_legacy_id=False,
        natural_old=lambda r: _option_key(r["hw_support_pack_license_id"], r["serial_nr"], r["product_nr"]),
        fields=[Field(_("Description"), "description", "description")],
        label_old=lambda r: f"{_text(r['product_nr'])} {_text(r['serial_nr'])}".strip() or "—",
        label_new=lambda r: f"{r['licence__full_number']}: {r['product_nr']} {r['serial_nr']}".strip(),
        note=_("Matched on licence, serial number and article number."),
    ),
    Part(
        key="invoices", label=_("Invoices"),
        old_sql="SELECT i.`id`, i.`invoice_id`, i.`payed_at`, i.`hw_support_order_id` FROM `invoice` i",
        new_rows=_invoices, natural_old=lambda r: _number(r["invoice_id"]), uses_legacy_id=False,
        fields=[
            Field(_("Paid on"), "payed_at", "paid_on", "date"),
            Field(_("Order (old ID)"), "hw_support_order_id", "order__legacy_id"),
        ],
        label_old=lambda r: _text(r["invoice_id"]), label_new=lambda r: f"{r['number']} · {r['customer_name']}",
        admin_url="admin:invoices_invoice_change",
        note=_("Matched on invoice number."),
    ),
    Part(
        key="invoice_pdfs", label=_("Invoice PDFs in archive"),
        old_sql="SELECT i.`id`, i.`invoice_id` FROM `invoice` i",
        new_rows=_archive_files, natural_old=lambda r: _number(r["invoice_id"]), uses_legacy_id=False, fields=[],
        label_old=lambda r: _text(r["invoice_id"]), label_new=lambda r: r["file"],
        note=_("Invoices in the old database against the PDF files in the archive folder."),
    ),
]
PARTS_BY_KEY = {p.key: p for p in PARTS}


# --- comparing ----------------------------------------------------------------------------------


@dataclass
class Result:
    part: Part
    old_count: int = 0
    new_count: int = 0
    matched: list = field(default_factory=list)  # (old, new)
    only_old: list = field(default_factory=list)
    only_new: list = field(default_factory=list)
    different: list = field(default_factory=list)  # (old, new, [(label, old value, new value)])
    error: str = ""

    def summary(self):
        return {"key": self.part.key, "label": self.part.label, "note": self.part.note, "old": self.old_count,
                "new": self.new_count, "only_old": len(self.only_old), "only_new": len(self.only_new),
                "different": len(self.different), "same": len(self.matched) - len(self.different),
                "error": self.error}


def _differences(part, old, new):
    diffs = []
    for f in part.fields:
        normalise = NORMALISE[f.kind]
        a, b = normalise(old.get(f.old)), normalise(new.get(f.new))
        if a != b:
            diffs.append((str(f.label), show(a), show(b)))
    return diffs


def compare_part(part, reader):
    from .connection import ExternalDatabaseError

    result = Result(part)
    try:
        old_rows = reader.rows(part.old_sql)
    except ExternalDatabaseError as exc:
        result.error = str(exc)
        return result
    for row in old_rows:
        if part.key == "licences":
            row["full_number"] = _full_number(row)
    new_rows = list(part.new_rows())
    result.old_count, result.new_count = len(old_rows), len(new_rows)

    by_legacy = {_text(n["legacy_id"]): n for n in new_rows if part.uses_legacy_id and _text(n.get("legacy_id"))}
    used, unmatched_old = set(), []
    for old in old_rows:
        new = by_legacy.get(_text(old.get("id"))) if part.uses_legacy_id else None
        if new is not None:
            used.add(id(new))
            result.matched.append((old, new))
        else:
            unmatched_old.append(old)
    by_natural = {}
    for n in new_rows:
        if id(n) not in used and n.get("natural"):
            by_natural.setdefault(n["natural"], []).append(n)
    for old in unmatched_old:
        key = part.natural_old(old)
        candidates = by_natural.get(key) if key else None
        if candidates:
            new = candidates.pop(0)
            used.add(id(new))
            result.matched.append((old, new))
        else:
            result.only_old.append(old)
    result.only_new = [n for n in new_rows if id(n) not in used]
    for old, new in result.matched:
        diffs = _differences(part, old, new)
        if diffs:
            result.different.append((old, new, diffs))
    return result


def compare_all(reader):
    return [compare_part(part, reader) for part in PARTS]


def _highest(values):
    """Highest number: numerically when all are digits, otherwise longest-then-alphabetical (26A0099 > 26A0001)."""
    values = [v for v in values if v]
    if not values:
        return None
    if all(v.isdigit() for v in values):
        return str(max(int(v) for v in values))
    return max(values, key=lambda v: (len(v), v.upper()))


def _is_above(next_number, highest):
    """True/False when comparable, None when the formats differ (then the user judges)."""
    if not next_number or not highest:
        return None
    if next_number.isdigit() and highest.isdigit():
        return int(next_number) > int(highest)
    if len(next_number) == len(highest):
        return next_number.upper() > highest.upper()
    return None


def number_tops(reader):
    """Highest numbers in the old database against the next number in PackDesk."""
    from .connection import ExternalDatabaseError

    sequences = {s.key: s for s in NumberSequence.objects.all()}
    rows = []
    for key, label, sql, column in [
        ("invoice", _("Invoice number"), "SELECT i.`invoice_id` FROM `invoice` i", "invoice_id"),
        ("order", _("Order number"), "SELECT o.`id` FROM `hw_support_order` o", "id"),
        ("licence", _("Licence number"), "SELECT l.`license_nr` FROM `hw_support_pack_license` l", "license_nr"),
        ("customer", _("Customer number"), "SELECT c.`number_deb` FROM `customer` c", "number_deb"),
    ]:
        try:
            highest = _highest([_text(r[column]) for r in reader.rows(sql)])
        except ExternalDatabaseError:
            highest = None
        seq = sequences.get(key)
        next_number = seq.preview() if seq else None
        above = _is_above(next_number, highest)
        rows.append({
            "label": label, "old": highest, "next": next_number, "ok": above, "url":
            reverse("admin:numbering_numbersequence_change", args=[seq.pk]) if seq else "",
        })
    return rows


def admin_link(part, row):
    pk = row.get(part.admin_pk)
    return reverse(part.admin_url, args=[pk]) if part.admin_url and pk else ""


# --- searching ----------------------------------------------------------------------------------


SEARCH_OLD = [
    ("customers", "SELECT c.`id`, c.`name`, c.`number_deb` FROM `customer` c "
                  "WHERE c.`name` LIKE %s OR c.`number_deb` LIKE %s OR c.`number_tax` LIKE %s", 3),
    ("contacts", "SELECT e.`id`, e.`customer_id`, e.`telephone`, e.`function`, e.`department`, u.`email`, "
                 "u.`name_first`, u.`name_last` FROM `employee` e LEFT JOIN `user` u ON u.`id` = e.`user_id` "
                 "WHERE u.`email` LIKE %s OR u.`name_last` LIKE %s", 2),
    ("licences", "SELECT l.`id`, l.`license_nr`, l.`license_nr_suffix`, l.`license_sequence_nr`, l.`serial_nr` "
                 "FROM `hw_support_pack_license` l WHERE l.`license_nr` LIKE %s OR l.`serial_nr` LIKE %s", 2),
    ("options", "SELECT o.`id`, o.`hw_support_pack_license_id`, o.`serial_nr`, o.`product_nr`, o.`description` "
                "FROM `hw_support_pack_license_option` o WHERE o.`serial_nr` LIKE %s", 1),
    ("invoices", "SELECT i.`id`, i.`invoice_id` FROM `invoice` i WHERE i.`invoice_id` LIKE %s", 1),
]


def _search_new(key, q):
    if key == "customers":
        rows = Customer.objects.filter(name__icontains=q) | Customer.objects.filter(number__icontains=q) \
            | Customer.objects.filter(vat_number__icontains=q)
        return list(rows.values("pk", "name", "number")[:50])
    if key == "contacts":
        rows = Contact.objects.filter(email__icontains=q) | Contact.objects.filter(last_name__icontains=q)
        return list(rows.values("pk", "email", "first_name", "last_name", "customer_id")[:50])
    if key == "licences":
        rows = Licence.objects.filter(full_number__icontains=q) | Licence.objects.filter(serial_nr__icontains=q)
        return list(rows.values("pk", "full_number")[:50])
    if key == "options":
        return list(LicenceOption.objects.filter(serial_nr__icontains=q)
                    .values("pk", "licence__full_number", "product_nr", "serial_nr")[:50])
    if key == "invoices":
        return list(Invoice.objects.filter(number__icontains=q).values("pk", "number", "customer_name")[:50])
    return []


def search(reader, q):
    """Where a number, name, serial number or email address occurs: old database, PackDesk, or both."""
    from .connection import ExternalDatabaseError

    q = q.strip()
    results = []
    for key, sql, n in SEARCH_OLD:
        part = PARTS_BY_KEY[key]
        # A full licence number (26A0001ABC-1) is not one column in the old database: search on its
        # first characters and filter on the complete number afterwards.
        term = f"%{q[:6]}%" if key == "licences" else f"%{q}%"
        error = ""
        try:
            old = reader.rows(sql + " LIMIT 500", (term,) * n)
        except ExternalDatabaseError as exc:
            old, error = [], str(exc)
        if key == "licences":
            old = [r for r in old if q.upper() in _full_number(r) or q.upper() in _text(r["serial_nr"]).upper()]
        results.append({
            "label": part.label, "error": error,
            "old": [part.label_old(r) for r in old[:50]],
            "new": [(part.label_new(r), admin_link(part, r)) for r in _search_new(key, q)],
        })
    return results
