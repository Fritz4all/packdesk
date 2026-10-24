"""The PackDesk parts that can be linked to tables in an external database, with their fields.

Each part says which fields exist, how its PackDesk rows are read, and which fields identify a
row when there is no old ID (the natural key). `OLD_SHOP_PRESET` is the ready-made mapping for
the database of the previous webshop; any other database is mapped by hand in the admin.
"""

import os
import re
from dataclasses import dataclass, field

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.customers.models import Contact, Customer, CustomerAddress
from apps.invoices.models import Invoice
from apps.licences.models import Licence, LicenceOption
from apps.orders.models import Order


@dataclass
class Field:
    name: str
    label: str
    kind: str = "text"  # text | email | number | upper | decimal | date | bool


@dataclass
class Part:
    key: str
    label: str
    fields: list
    natural: list  # field names that identify a row without old ID
    rows: callable  # PackDesk rows as dicts with these field names, plus pk / legacy_id
    title: list  # fields that make a readable label
    has_legacy_id: bool = True
    sequence: str = ""  # number sequence to compare the highest number with
    number_field: str = ""
    admin_url: str = ""
    admin_pk: str = "pk"
    note: str = ""
    by_name: dict = field(init=False)

    def __post_init__(self):
        self.by_name = {f.name: f for f in self.fields}


def _customers():
    main = {a.customer_id: a for a in CustomerAddress.objects.filter(kind=CustomerAddress.Kind.MAIN)}
    for c in Customer.objects.values("pk", "legacy_id", "number", "name", "vat_number", "coc_number", "phone", "email",
                                      "email_orders", "email_parts", "email_invoices", "margin_packs", "margin_parts",
                                      "no_pack_invoice", "status"):
        address = main.get(c["pk"])
        c["active"] = c.pop("status") == Customer.Status.ACTIVE
        c.update(line1=getattr(address, "line1", ""), postal_code=getattr(address, "postal_code", ""),
                 city=getattr(address, "city", ""))
        yield c


def _contacts():
    for c in Contact.objects.values("pk", "legacy_id", "email", "first_name", "last_name", "phone", "function",
                                     "department", "customer_id", "customer__legacy_id", "customer__number"):
        c["customer_ref"] = c.pop("customer__legacy_id")
        c["customer_number"] = c.pop("customer__number")
        yield c


def _users():
    yield from User.objects.values("pk", "email", "first_name", "last_name")


def _orders():
    for o in Order.objects.values("pk", "legacy_id", "number", "reference", "discount_pct", "total",
                                  "customer__legacy_id"):
        o["customer_ref"] = o.pop("customer__legacy_id")
        yield o


def _licences():
    for lic in Licence.objects.values("pk", "legacy_id", "number", "full_number", "start_date", "end_date",
                                      "registered_on", "serial_nr", "product_nr", "description", "purchase_date",
                                      "end_customer_email", "end_customer_reference", "memo", "customer__legacy_id",
                                      "prolongation_of__legacy_id"):
        lic["customer_ref"] = lic.pop("customer__legacy_id")
        lic["prolongation_ref"] = lic.pop("prolongation_of__legacy_id")
        yield lic


def _options():
    for o in LicenceOption.objects.values("pk", "licence__legacy_id", "licence__full_number", "serial_nr",
                                          "product_nr", "description"):
        o["licence_ref"] = o.pop("licence__legacy_id")
        o["licence_number"] = o.pop("licence__full_number")
        yield o


def _invoices():
    for i in Invoice.objects.values("pk", "number", "issued_on", "paid_on", "total", "customer_name",
                                    "customer_number", "order__legacy_id"):
        i["order_ref"] = i.pop("order__legacy_id")
        yield i


PARTS = [
    Part(
        key="customers", label=_("Customers"), natural=["number"], title=["name", "number"],
        sequence="customer", number_field="number", admin_url="admin:customers_customer_change", rows=_customers,
        fields=[
            Field("number", _("Customer number"), "number"), Field("name", _("Name")),
            Field("vat_number", _("VAT number")), Field("coc_number", _("Chamber of Commerce number")),
            Field("phone", _("Phone")), Field("email", _("Email"), "email"),
            Field("email_orders", _("Email for orders"), "email"), Field("email_parts", _("Email for spare parts"), "email"),
            Field("email_invoices", _("Email for invoices"), "email"),
            Field("margin_packs", _("Margin service packs"), "decimal"),
            Field("margin_parts", _("Margin spare parts"), "decimal"),
            Field("no_pack_invoice", _("No invoice for service packs"), "bool"), Field("active", _("Active"), "bool"),
            Field("line1", _("Address")), Field("postal_code", _("Postal code")), Field("city", _("City")),
        ],
    ),
    Part(
        key="contacts", label=_("Contacts"), natural=["email"], title=["first_name", "last_name", "email"],
        admin_url="admin:customers_customer_change", admin_pk="customer_id", rows=_contacts,
        fields=[
            Field("email", _("Email"), "email"), Field("first_name", _("First name")), Field("last_name", _("Last name")),
            Field("phone", _("Phone")), Field("function", _("Function")), Field("department", _("Department")),
            Field("customer_ref", _("Customer (old ID)")), Field("customer_number", _("Customer number"), "number"),
        ],
    ),
    Part(
        key="users", label=_("Logins"), natural=["email"], title=["email"], has_legacy_id=False,
        admin_url="admin:accounts_user_change", rows=_users,
        note=_("Matched on email address. Both sides include staff logins."),
        fields=[Field("email", _("Email"), "email"), Field("first_name", _("First name")), Field("last_name", _("Last name"))],
    ),
    Part(
        key="orders", label=_("Orders"), natural=["number"], title=["number", "reference"], sequence="order",
        number_field="number", admin_url="admin:orders_order_change", rows=_orders,
        fields=[
            Field("number", _("Order number"), "number"), Field("reference", _("Reference")),
            Field("discount_pct", _("Discount (%)"), "decimal"), Field("total", _("Total"), "decimal"),
            Field("customer_ref", _("Customer (old ID)")),
        ],
    ),
    Part(
        key="licences", label=_("Licences"), natural=["full_number"], title=["full_number"], sequence="licence",
        number_field="number", admin_url="admin:licences_licence_change", rows=_licences,
        fields=[
            Field("full_number", _("Licence number"), "upper"), Field("number", _("Licence number without letters"), "upper"),
            Field("start_date", _("Start date"), "date"), Field("end_date", _("End date"), "date"),
            Field("registered_on", _("Registered on"), "date"), Field("serial_nr", _("Serial number"), "upper"),
            Field("product_nr", _("Article number"), "upper"), Field("description", _("Description")),
            Field("purchase_date", _("Purchase date"), "date"),
            Field("end_customer_email", _("Email end customer"), "email"),
            Field("end_customer_reference", _("Reference")), Field("memo", _("Memo")),
            Field("prolongation_ref", _("Extension of (old ID)")), Field("customer_ref", _("Customer (old ID)")),
        ],
    ),
    Part(
        key="options", label=_("Licence options"), natural=["licence_ref", "serial_nr", "product_nr"],
        title=["licence_number", "product_nr", "serial_nr"], has_legacy_id=False, rows=_options,
        note=_("Matched on licence, serial number and article number."),
        fields=[
            Field("licence_ref", _("Licence (old ID)")), Field("licence_number", _("Licence number"), "upper"),
            Field("serial_nr", _("Serial number"), "upper"), Field("product_nr", _("Article number"), "upper"),
            Field("description", _("Description")),
        ],
    ),
    Part(
        key="invoices", label=_("Invoices"), natural=["number"], title=["number", "customer_name"], has_legacy_id=False,
        sequence="invoice", number_field="number", admin_url="admin:invoices_invoice_change", rows=_invoices,
        note=_("Matched on invoice number."),
        fields=[
            Field("number", _("Invoice number"), "number"), Field("issued_on", _("Invoice date"), "date"),
            Field("paid_on", _("Paid on"), "date"), Field("total", _("Total"), "decimal"),
            Field("customer_name", _("Customer name")), Field("customer_number", _("Customer number"), "number"),
            Field("order_ref", _("Order (old ID)")),
        ],
    ),
]
PARTS_BY_KEY = {p.key: p for p in PARTS}


ARCHIVE_NUMBER = re.compile(r"(\d+)")


def archive_numbers():
    """Invoice numbers of the PDF files in the archive folder: {number: file name}."""
    folder = settings.DOCUMENT_ARCHIVE_DIR
    if not folder or not os.path.isdir(folder):
        return {}
    found = {}
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf") and (m := ARCHIVE_NUMBER.search(name)):
            found[m.group(1).lstrip("0") or "0"] = name
    return found


# --- ready-made mapping for the previous webshop's database ---------------------------------------------

OLD_SHOP_PRESET = {
    "customers": {
        "query": ("SELECT c.`id`, c.`name`, c.`number_deb`, c.`number_tax`, c.`telephone`, c.`email_packs`, "
                  "c.`email_parts`, c.`email_invoice`, c.`margin_packs`, c.`margin_parts`, "
                  "c.`skip_hw_support_pack_invoice`, c.`activated`, c.`deleted`, a.`line1`, a.`zipcode`, a.`city` "
                  "FROM `customer` c LEFT JOIN `address` a ON a.`id` = c.`address`"),
        "id": "id", "skip": ("deleted", "1"),
        "fields": {"number": "number_deb", "name": "name", "vat_number": "number_tax", "phone": "telephone",
                   "email_orders": "email_packs", "email_parts": "email_parts", "email_invoices": "email_invoice",
                   "margin_packs": "margin_packs", "margin_parts": "margin_parts",
                   "no_pack_invoice": "skip_hw_support_pack_invoice", "active": "activated",
                   "line1": "line1", "postal_code": "zipcode", "city": "city"},
    },
    "contacts": {
        "query": ("SELECT e.`id`, e.`customer_id`, e.`telephone`, e.`function`, e.`department`, e.`deleted`, "
                  "u.`email`, u.`name_first`, u.`name_last` "
                  "FROM `employee` e LEFT JOIN `user` u ON u.`id` = e.`user_id`"),
        "id": "id", "skip": ("deleted", "1"),
        "fields": {"email": "email", "first_name": "name_first", "last_name": "name_last", "phone": "telephone",
                   "function": "function", "department": "department", "customer_ref": "customer_id"},
    },
    "users": {
        "table": "user", "id": "", "skip": ("deleted", "1"),
        "fields": {"email": "email", "first_name": "name_first", "last_name": "name_last"},
    },
    "orders": {
        "query": ("SELECT o.`id`, o.`reference`, o.`discount`, e.`customer_id` FROM `hw_support_order` o "
                  "LEFT JOIN `employee` e ON e.`id` = o.`employee_id`"),
        "id": "id",
        "fields": {"number": "id", "reference": "reference", "discount_pct": "discount", "customer_ref": "customer_id"},
    },
    "licences": {
        "query": ("SELECT l.`id`, CONCAT(l.`license_nr`, l.`license_nr_suffix`, '-', l.`license_sequence_nr`) AS full_number, "
                  "l.`license_nr`, l.`start_date`, l.`end_date`, l.`registered_on`, l.`serial_nr`, l.`product_nr`, "
                  "l.`description`, l.`purchase_date`, l.`email`, l.`reference`, l.`memo`, l.`prolongation_of`, "
                  "e.`customer_id` FROM `hw_support_pack_license` l "
                  "LEFT JOIN `hw_support_order_entry` oe ON oe.`id` = l.`hw_support_order_entry_id` "
                  "LEFT JOIN `hw_support_order` o ON o.`id` = oe.`hw_support_order_id` "
                  "LEFT JOIN `employee` e ON e.`id` = o.`employee_id`"),
        "id": "id",
        "fields": {"full_number": "full_number", "number": "license_nr", "start_date": "start_date",
                   "end_date": "end_date", "registered_on": "registered_on", "serial_nr": "serial_nr",
                   "product_nr": "product_nr", "description": "description", "purchase_date": "purchase_date",
                   "end_customer_email": "email", "end_customer_reference": "reference", "memo": "memo",
                   "prolongation_ref": "prolongation_of", "customer_ref": "customer_id"},
    },
    "options": {
        "table": "hw_support_pack_license_option", "id": "", "skip": ("is_deleted", "1"),
        "fields": {"licence_ref": "hw_support_pack_license_id", "serial_nr": "serial_nr", "product_nr": "product_nr",
                   "description": "description"},
    },
    "invoices": {
        "table": "invoice", "id": "",
        "fields": {"number": "invoice_id", "paid_on": "payed_at", "order_ref": "hw_support_order_id"},
    },
}


def apply_preset(db, preset=OLD_SHOP_PRESET):
    """Create the mappings of a preset that do not exist yet. Returns the number created."""
    from .models import FieldMapping, TableMapping

    created = 0
    for key, spec in preset.items():
        if TableMapping.objects.filter(database=db, part=key).exists():
            continue
        skip_column, skip_value = spec.get("skip", ("", ""))
        mapping = TableMapping.objects.create(
            database=db, part=key, source_table=spec.get("table", ""), source_query=spec.get("query", ""),
            id_column=spec.get("id", ""), skip_column=skip_column, skip_value=skip_value,
        )
        FieldMapping.objects.bulk_create([FieldMapping(mapping=mapping, field=f, column=c) for f, c in spec["fields"].items()])
        created += 1
    return created
