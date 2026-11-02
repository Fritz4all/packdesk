"""Import and export of configuration items as an Excel sheet (.xlsx) or a CSV file.

One row per item; the columns are the fixed fields (COLUMNS) and one column per property, named after its code.
Rules when importing:

- Nothing is saved before the user has seen the check (`analyse`) and confirmed it.
- An item is recognised by its number; without a number by the same name at the same customer. The number of a new
  item comes from PackDesk, so a file can be imported twice without making anything double.
- A column that is not in the file leaves that field alone; an empty cell in a column that is there empties the field.
- Only customers that use the CMDB can be imported into. An import never moves an item to another customer and
  never deletes an item. Items that are not in the file stay as they are.
- `relations` holds the relations of the item itself, e.g. "runs_on:CI-00012 | depends_on:Mail server", with the
  number or name of another item of the same customer, also one further on in the file.
- A row with an error is skipped; the other rows are imported.
- Text that a spreadsheet would run as a formula gets a leading ' when written, which is removed again when read.
"""

import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.customers.models import Contact, Customer

from . import fields, history
from .models import ConfigurationItem, ItemChange, ItemField, ItemStatus, ItemType, Relation, RelationKind, default_status

COLUMNS = [
    ("number", gettext_lazy("Number (filled in by PackDesk; empty for a new item)")),
    ("customer", gettext_lazy("Customer number or exact company name; the customer must use the CMDB (required)")),
    ("type", gettext_lazy("Item type, as under CMDB settings → Item types (required)")),
    ("name", gettext_lazy("Name (required)")),
    ("status", gettext_lazy("Status, as under CMDB settings → Statuses (empty = In use)")),
    ("manufacturer", gettext_lazy("Manufacturer")),
    ("model", gettext_lazy("Model")),
    ("serial_nr", gettext_lazy("Serial number")),
    ("asset_tag", gettext_lazy("Asset tag")),
    ("location", gettext_lazy("Location")),
    ("contact", gettext_lazy("Email address of a contact of this customer")),
    ("purchase_date", gettext_lazy("Purchase date, e.g. 2026-10-28")),
    ("warranty_until", gettext_lazy("Warranty until, e.g. 2029-10-28")),
    ("end_of_life", gettext_lazy("End of life, e.g. 2031-10-28")),
    ("description", gettext_lazy("Internal description; customers do not see this")),
    ("relations", gettext_lazy("Relations, e.g. runs_on:CI-00012 | depends_on:Mail server")),
]
TEXT_FIELDS = ["name", "manufacturer", "model", "serial_nr", "asset_tag", "location", "description"]
DATE_FIELDS = ["purchase_date", "warranty_until", "end_of_life"]
MAX_ROWS = 5000
MAX_BYTES = 10 * 1024 * 1024
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
RELATION_SPLIT = "|"

NEW, UPDATE, SAME, ERROR = "new", "update", "same", "error"
YES = {"1", "yes", "ja", "y", "j", "true", "waar", "x", "wahr"}
NO = {"0", "no", "nee", "n", "false", "onwaar", "nein", "falsch"}


class ImportFileError(Exception):
    pass


def properties():
    return list(ItemField.own().prefetch_related("item_types"))


# --- reading a file ----------------------------------------------------------------------------------------

def read_rows(name, data):
    """The rows of an uploaded file as dicts {column: value}; Excel cells keep their type (number, date)."""
    if len(data) > MAX_BYTES:
        raise ImportFileError(_("This file is too large; at most 10 MB."))
    if name.lower().endswith(".xlsx"):
        return _read_xlsx(data)
    if name.lower().endswith((".csv", ".txt")):
        return _read_csv(data)
    raise ImportFileError(_("Choose an Excel file (.xlsx) or a CSV file (.csv)."))


def _read_xlsx(data):
    from openpyxl import load_workbook

    try:
        sheet = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    except Exception as exc:
        raise ImportFileError(_("This is not a readable Excel file.")) from exc
    rows = sheet.iter_rows(values_only=True)
    head = [str(h).strip() if h is not None else "" for h in next(rows, [])]
    return _with_header(head, rows)


def _read_csv(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows = csv.reader(io.StringIO(text), dialect)
    head = [h.strip() for h in next(rows, [])]
    return _with_header(head, rows)


def _with_header(head, rows):
    if "name" not in head and "number" not in head:
        raise ImportFileError(_("The first row must hold the column names. Download the example file to see the columns."))
    result = []
    for values in rows:
        values = list(values or [])
        if not any(v not in (None, "") for v in values):
            continue  # empty row
        result.append({h: (values[i] if i < len(values) else None) for i, h in enumerate(head) if h})
        if len(result) > MAX_ROWS:
            raise ImportFileError(_("At most %(n)s items per file.") % {"n": MAX_ROWS})
    return result


# --- understanding the values ------------------------------------------------------------------------------

def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if text[:1] == "'" and text[1:2] in FORMULA_START and text[1:2]:
        return text[1:]
    return text


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(_("“%(value)s” is not a date (use e.g. 2026-10-28)") % {"value": value})


def _number(value):
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
    else:
        text = re.sub(r"\s", "", str(value))
        if "," in text and "." in text:  # 1.234,50 or 1,234.50: the last one is the decimal sign
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        else:
            text = text.replace(",", ".")
        try:
            number = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(_("“%(value)s” is not a number") % {"value": value}) from exc
    if not number.is_finite():
        raise ValueError(_("“%(value)s” is not a number") % {"value": value})
    return int(number) if number == number.to_integral_value() else float(number)


def _property_value(prop, value):
    if value in (None, ""):
        return None
    if prop.kind == ItemField.Kind.NUMBER:
        return _number(value)
    if prop.kind == ItemField.Kind.YES_NO:
        text = _text(value).lower()
        if text in YES:
            return True
        if text in NO:
            return False
        raise ValueError(_("“%(value)s” is not yes or no") % {"value": value})
    text = _text(value)
    if prop.kind == ItemField.Kind.CHOICE:
        match = next((o for o in prop.options() if o.lower() == text.lower()), None)
        if match is None:
            raise ValueError(_("“%(value)s” is not one of the choices (%(choices)s)")
                             % {"value": value, "choices": ", ".join(prop.options())})
        return match
    return text


def _named(model, name):
    """The row of a translated list with this name in any language."""
    query = Q()
    for lang, _name in settings.LANGUAGES:
        query |= Q(**{f"name_{lang}__iexact": name})
    return model.objects.filter(query).first()


def _status(value):
    text = _text(value)
    status = ItemStatus.objects.filter(key=text.lower()).first() or _named(ItemStatus, text)
    if status is None:
        raise ValueError(_("unknown status “%(value)s”") % {"value": value})
    return status


def _item_type(name):
    return _named(ItemType, name)


def _customer(text):
    """(customer, error): by number, otherwise by a company name that only one customer has."""
    customer = Customer.objects.filter(number=text).select_related("cmdb").first()
    if customer is None:
        found = list(Customer.objects.filter(name__iexact=text).select_related("cmdb")[:2])
        if len(found) > 1:
            return None, _("customer: several customers are called “%(value)s”; use the customer number") % {"value": text}
        customer = found[0] if found else None
    if customer is None:
        return None, _("customer: unknown customer “%(value)s”") % {"value": text}
    if not (hasattr(customer, "cmdb") and customer.cmdb.enabled):
        return None, _("customer: “%(value)s” does not use the CMDB") % {"value": text}
    return customer, None


def _relations(text):
    """[(kind, reference)] from a relations cell; raises ValueError on a part that cannot be understood."""
    result = []
    for part in text.split(RELATION_SPLIT):
        part = part.strip()
        if not part:
            continue
        kind, separator, reference = part.partition(":")
        kind, reference = kind.strip(), reference.strip()
        if not separator or not reference:
            raise ValueError(_("“%(value)s” must look like runs_on:CI-00012") % {"value": part})
        known = list(RelationKind.objects.values_list("key", flat=True))
        if kind not in known:
            raise ValueError(_("unknown relation “%(value)s” (%(choices)s)")
                             % {"value": kind, "choices": ", ".join(known)})
        result.append((kind, reference))
    return result


def clean_row(row, props, required):
    """(values, errors) for one row: the fields present in the file, understood."""
    values, errors = {}, []

    def take(key, convert):
        if key not in row:
            return
        try:
            values[key] = convert(row[key])
        except ValueError as exc:
            errors.append(f"{key}: {exc}")

    take("number", _text)
    for key in TEXT_FIELDS:
        take(key, _text)
    for key in DATE_FIELDS:
        take(key, _date)
    if "status" in row and _text(row["status"]):
        take("status", _status)
    if "type" in row:
        name = _text(row["type"])
        values["type"] = _item_type(name) if name else None
        if name and values["type"] is None:
            errors.append(_("type: unknown item type “%(value)s”") % {"value": name})
    if "customer" in row:
        text = _text(row["customer"])
        values["customer"] = None
        if text:
            values["customer"], error = _customer(text)
            if error:
                errors.append(error)
    if "contact" in row:
        values["contact"] = _text(row["contact"])
    if "relations" in row:
        take("relations", lambda v: _relations(_text(v)))
        values["relations_text"] = _text(row["relations"])
    prop_values = {}
    for prop in props:
        if prop.key in row:
            try:
                prop_values[prop.key] = _property_value(prop, row[prop.key])
            except ValueError as exc:
                errors.append(f"{prop.key}: {exc}")
    values["properties"] = prop_values
    for key in required:
        if key in row and not _text(row[key]):
            errors.append(_("%(column)s: required") % {"column": key})
    for key in TEXT_FIELDS:
        limit = ConfigurationItem._meta.get_field(key).max_length
        if limit and len(values.get(key) or "") > limit:
            errors.append(_("%(column)s: longer than %(n)s characters") % {"column": key, "n": limit})
    return values, errors


# --- check and import --------------------------------------------------------------------------------------

def _find_item(values, errors):
    """The existing item this row is about, or None for a new one."""
    number, customer = values.get("number"), values.get("customer")
    if number:
        item = ConfigurationItem.objects.filter(number=number).select_related("customer", "contact", "item_type").first()
        if item is None:
            errors.append(_("number: unknown number “%(value)s”; leave it empty for a new item") % {"value": number})
        elif not ConfigurationItem.objects.filter(pk=item.pk, customer__cmdb__enabled=True).exists():
            errors.append(_("number: this item belongs to a customer that does not use the CMDB"))
            return None
        elif customer and customer.pk != item.customer_id:
            errors.append(_("customer: this item belongs to another customer; an import does not move items"))
        return item
    if customer and values.get("name"):
        found = list(ConfigurationItem.objects.filter(customer=customer, name__iexact=values["name"])
                     .select_related("customer", "contact", "item_type")[:2])
        if len(found) > 1:
            errors.append(_("name: several items of this customer have this name; use the number"))
            return None
        return found[0] if found else None
    return None


def _check_properties(item, values, props, is_new, errors):
    item_type = values.get("type") or (item.item_type if item is not None else None)
    keys = {p.key for p in props if item_type and any(t.pk == item_type.pk for t in p.item_types.all())}
    for key, value in values["properties"].items():
        if value is not None and key not in keys:
            errors.append(_("%(column)s: not a property of %(type)s") % {"column": key, "type": item_type})
    for prop in props:
        if prop.is_required and prop.key in keys and (
                (prop.key in values["properties"] and values["properties"][prop.key] is None)
                or (is_new and prop.key not in values["properties"])):
            errors.append(_("%(column)s: required for %(type)s") % {"column": prop.key, "type": item_type})


def _apply(item, values, contact):
    """Put the values on the item, without saving."""
    for key in [*TEXT_FIELDS, *DATE_FIELDS]:
        if key in values:
            setattr(item, key, values[key])
    if values.get("status"):
        item.status = values["status"]
    if values.get("type"):
        item.item_type = values["type"]
    if values.get("customer") and item.pk is None:
        item.customer = values["customer"]
    if "contact" in values:
        item.contact = contact
    if values["properties"]:
        current = dict(item.properties or {})
        for key, value in values["properties"].items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = value
        item.properties = current
    return item


def _resolve_target(customer_id, reference, in_file):
    """The item or the (still new) row a relation points at: number first, then name of this customer."""
    item = ConfigurationItem.objects.filter(customer_id=customer_id, number=reference).first()
    if item is None:
        found = list(ConfigurationItem.objects.filter(customer_id=customer_id, name__iexact=reference)[:2])
        if len(found) > 1:
            return None, True
        item = found[0] if found else None
    if item is not None:
        return item, False
    return in_file.get((customer_id, reference.lower())), False


def analyse(rows):
    """What the import would do, per row: {line, number, name, customer, action, errors, changes, item}."""
    props = properties()
    required = fields.required_columns()
    outcome, keys = [], set()
    for line, row in enumerate(rows, start=2):
        values, errors = clean_row(row, props, required)
        item = _find_item(values, errors)
        is_new = item is None
        key = item.pk if item is not None else ((values["customer"].pk, values.get("name", "").lower())
                                                if values.get("customer") else None)
        if key is not None and key in keys:
            errors.append(_("this item is already in an earlier row"))
        keys.add(key)
        if is_new:
            for column in required:
                if column not in row:
                    errors.append(_("%(column)s: required for a new item") % {"column": column})
        customer_id = item.customer_id if item is not None else (values["customer"].pk if values.get("customer") else None)
        contact = None
        if values.get("contact") and customer_id:
            contact = Contact.objects.filter(customer_id=customer_id, email__iexact=values["contact"]).first()
            if contact is None:
                errors.append(_("contact: this customer has no contact with the email address “%(value)s”")
                              % {"value": values["contact"]})
        _check_properties(item, values, props, is_new, errors)
        outcome.append({"line": line, "number": values.get("number") or (item.number if item else ""),
                        "name": values.get("name") or (item.name if item else ""),
                        "customer": (item.customer if item else values.get("customer")) or "",
                        "action": ERROR if errors else None, "errors": errors, "changes": [], "item": item,
                        "values": values, "contact": contact, "customer_id": customer_id})
    # A relation may point at a new item further on in the file, unless that row itself cannot be imported;
    # a row that drops out can take away the target of another one, so repeat until nothing changes.
    while True:
        in_file = _new_rows(outcome)
        dropped = False
        for result in outcome:
            if result["action"] == ERROR or "relations" not in result["values"]:
                continue
            for kind, reference in result["values"]["relations"]:
                target, several = _resolve_target(result["customer_id"], reference, in_file)
                if several:
                    result["errors"].append(_("relations: several items are called “%(value)s”; use the number")
                                            % {"value": reference})
                elif target is None:
                    result["errors"].append(_("relations: no item “%(value)s” at this customer") % {"value": reference})
                elif target is result or (result["item"] is not None and getattr(target, "pk", None) == result["item"].pk):
                    result["errors"].append(_("relations: an item cannot have a relation with itself"))
            if result["errors"]:
                result["action"] = ERROR
                dropped = True
        if not dropped:
            break
    for result in outcome:
        if result["action"] == ERROR:
            continue
        item = result["item"]
        if item is None:
            result["action"] = NEW
            continue
        before = history.snapshot(item)
        fresh = ConfigurationItem.objects.select_related("customer", "contact", "item_type").get(pk=item.pk)
        _apply(fresh, result["values"], result["contact"])
        after = history.snapshot(fresh)
        result["changes"] = [(label, before.get(label, "") or "–", after.get(label, "") or "–")
                             for label in [*before, *[k for k in after if k not in before]]
                             if before.get(label, "") != after.get(label, "")]
        if "relations" in result["values"]:
            targets = _targets(result, in_file)
            wanted = {(kind, target.pk) for kind, target in targets if isinstance(target, ConfigurationItem)}
            if _relation_set(item) != wanted or any(not isinstance(target, ConfigurationItem) for _kind, target in targets):
                result["changes"].append((str(Relation._meta.verbose_name_plural).capitalize(),
                                          ", ".join(history.relation_texts(item)) or "–",
                                          result["values"]["relations_text"] or "–"))
        result["action"] = UPDATE if result["changes"] else SAME
    return outcome


def _relation_set(item):
    return set(item.relations_out.values_list("kind__key", "target_id"))


def _new_rows(outcome):
    return {(r["customer_id"], r["name"].lower()): r for r in outcome if r["action"] != ERROR and r["item"] is None}


def _targets(result, in_file):
    """[(kind, target)]; the target is an item, or the result of a row of the file that has no item yet."""
    return [(kind, _resolve_target(result["customer_id"], reference, in_file)[0])
            for kind, reference in result["values"]["relations"]]


@transaction.atomic
def run_import(rows, user=None):
    """Imports the rows without errors; returns (added, updated, skipped)."""
    outcome = analyse(rows)
    added = updated = skipped = 0
    source = ItemChange.Source.IMPORT
    in_file = _new_rows(outcome)
    # Found before anything is saved, as a row in this file may change the name that another row points at.
    for result in outcome:
        if result["action"] in (NEW, UPDATE) and "relations" in result["values"]:
            result["targets"] = _targets(result, in_file)
    for result in outcome:
        if result["action"] == ERROR:
            skipped += 1
        if result["action"] not in (NEW, UPDATE):
            continue
        item = result["item"]
        is_new = item is None
        if is_new:
            item = _apply(ConfigurationItem(), result["values"], result["contact"])
            item.save()
            history.record(item, None, user, source)
            added += 1
        else:
            item = ConfigurationItem.objects.select_related("customer", "contact", "item_type").get(pk=item.pk)
            before = history.snapshot(item)
            _apply(item, result["values"], result["contact"])
            item.save()
            history.record(item, before, user, source)
            updated += 1
        result["saved"] = item
    for result in outcome:
        item = result.get("saved")
        if item is None or "targets" not in result:
            continue
        before = history.relation_texts(item)
        wanted = {(kind, (target if isinstance(target, ConfigurationItem) else target["saved"]).pk)
                  for kind, target in result["targets"]}
        for relation in item.relations_out.select_related("kind"):
            if (relation.kind.key, relation.target_id) not in wanted:
                relation.delete()
        existing = _relation_set(item)
        for kind, target_id in wanted - existing:
            Relation.objects.create(source=item, kind=RelationKind.objects.get(key=kind), target_id=target_id)
        history.record_relations(item, before, user, source)
    return added, updated, skipped


# --- writing a file ----------------------------------------------------------------------------------------

def header(props):
    return [key for key, _label in COLUMNS] + [p.key for p in props]


def _safe(value):
    """Text that a spreadsheet would run as a formula stays text."""
    if isinstance(value, str) and value.startswith(FORMULA_START):
        return "'" + value
    return value


def _yes_no(value):
    dutch = translation.get_language() == "nl"
    return ("ja" if dutch else "yes") if value else ("nee" if dutch else "no")


def item_row(item, props):
    values = {
        "number": item.number, "customer": item.customer.number or item.customer.name, "type": str(item.item_type),
        "name": item.name, "status": str(item.status), "manufacturer": item.manufacturer, "model": item.model,
        "serial_nr": item.serial_nr, "asset_tag": item.asset_tag, "location": item.location,
        "contact": item.contact.email if item.contact_id else "", "purchase_date": item.purchase_date,
        "warranty_until": item.warranty_until, "end_of_life": item.end_of_life, "description": item.description,
        "relations": f" {RELATION_SPLIT} ".join(f"{r.kind.key}:{r.target.number}" for r in item.relations_out.all()),
    }
    row = [_safe(values[key]) for key, _label in COLUMNS]
    for prop in props:
        value = (item.properties or {}).get(prop.key)
        row.append(_yes_no(value) if isinstance(value, bool) else _safe(value))
    return row


def example_rows(props):
    """A few made-up items that show how the columns are filled in. They hold no data of real customers."""
    types = list(ItemType.objects.filter(is_active=True)[:2])
    customer = "EXAMPLE-CUSTOMER"
    status = ItemStatus.objects.filter(pk=default_status()).first()
    rows = []
    for i, (name, manufacturer, model, serial, relations) in enumerate([
        ("Example server", "Example brand", "Rack 100", "EXAMPLE-1", ""),
        ("Example application", "Example brand", "Suite 5", "EXAMPLE-2", "runs_on:Example server"),
    ]):
        item_type = types[i % len(types)] if types else None
        values = {"number": "", "customer": customer, "type": str(item_type or ""), "name": name,
                  "status": str(status or ""), "manufacturer": manufacturer, "model": model,
                  "serial_nr": serial, "asset_tag": "", "location": "", "contact": "",
                  "purchase_date": datetime.date(2026, 1, 15), "warranty_until": datetime.date(2029, 1, 15),
                  "end_of_life": None, "description": "", "relations": relations}
        line = [values[key] for key, _label in COLUMNS]
        for prop in props:
            applies = item_type is not None and any(t.pk == item_type.pk for t in prop.item_types.all())
            line.append(_example_value(prop) if applies else "")
        rows.append(line)
    return rows


def _example_value(prop):
    if prop.kind == ItemField.Kind.CHOICE:
        return (prop.options() or [""])[0]
    if prop.kind == ItemField.Kind.NUMBER:
        return 8
    if prop.kind == ItemField.Kind.YES_NO:
        return _yes_no(True)
    return ""


def explanation(props):
    """Second sheet of the Excel file: what each column means and which values are allowed."""
    rows = [[_("Column"), _("Meaning")]]
    rows += [[key, str(label)] for key, label in COLUMNS]
    for prop in props:
        kind = prop.get_kind_display()
        if prop.kind == ItemField.Kind.CHOICE:
            kind += ": " + ", ".join(prop.options())
        types = ", ".join(str(t) for t in prop.item_types.all())
        rows.append([prop.key, f"{prop.name} ({kind}) – {types}"])
    rows.append([])
    rows.append([_("Replace EXAMPLE-CUSTOMER by the number of a customer that uses the CMDB, otherwise the check reports an error.")])
    rows.append([])
    rows.append([_("Item types"), ", ".join(str(t) for t in ItemType.objects.all())])
    rows.append([_("Statuses"), ", ".join(str(status) for status in ItemStatus.objects.all())])
    rows.append([_("Relations"), ", ".join(f"{kind.key} ({kind})" for kind in RelationKind.objects.all())])
    return rows


def write(rows, fmt, props, with_explanation=False):
    """The file contents (bytes) in format "xlsx" or "csv"."""
    head = header(props)
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow(head)
        for row in rows:
            writer.writerow(["" if v is None else (str(v).replace(".", ",") if isinstance(v, float) else v) for v in row])
        return ("﻿" + out.getvalue()).encode("utf-8")
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = str(_("Items"))[:31]
    sheet.append(head)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column, key in enumerate(head, start=1):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = max(12, min(40, len(key) + 4))
        if key in DATE_FIELDS:
            for (cell,) in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
                cell.number_format = "yyyy-mm-dd"
    sheet.freeze_panes = "A2"
    if with_explanation:
        info = book.create_sheet(str(_("Explanation"))[:31])
        for row in explanation(props):
            info.append(row)
        info.column_dimensions["A"].width = 22
        info.column_dimensions["B"].width = 100
        for cell in info[1]:
            cell.font = Font(bold=True)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
