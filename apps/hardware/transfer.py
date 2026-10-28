"""Import and export of devices as an Excel sheet (.xlsx) or a CSV file.

One row per device; the columns are the fixed fields (COLUMNS) and one column per specification, named after
its code. Devices are recognised by their serial number. Rules when importing:

- Nothing is saved before the user has seen the check (`analyse`) and confirmed it.
- A column that is not in the file leaves that field alone; an empty cell in a column that is there empties
  the field (so export → change in Excel → import works both ways). The stock number is never imported.
- Device types, conditions and statuses are matched by name in any language (statuses also by code);
  unknown ones are an error. An unknown brand is added to the brands.
- A row with an error is skipped; the other rows are imported.
"""

import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.licences.models import Vendor

from .models import Condition, Device, DeviceType, Specification

COLUMNS = [
    ("number", gettext_lazy("Stock number (filled in by PackDesk, not imported)")),
    ("serial_nr", gettext_lazy("Serial number (required, unique)")),
    ("device_type", gettext_lazy("Device type, as under Hardware → Device types (required)")),
    ("brand", gettext_lazy("Brand; a new brand is added")),
    ("model", gettext_lazy("Model (required)")),
    ("condition", gettext_lazy("Condition, as under Hardware → Conditions")),
    ("status", gettext_lazy("Status: Draft, For sale, Reserved, Sold or Written off (empty = Draft)")),
    ("purchase_date", gettext_lazy("Purchase date, e.g. 2026-10-28")),
    ("purchase_price", gettext_lazy("Purchase price excl. VAT")),
    ("supplier", gettext_lazy("Supplier")),
    ("sale_price", gettext_lazy("Selling price excl. VAT (empty = purchase price plus the standard markup)")),
    ("warranty_months", gettext_lazy("Warranty in months (empty = the standard warranty)")),
    ("description", gettext_lazy("Description")),
]
FIELDS = [key for key, _label in COLUMNS if key != "number"]
REQUIRED = {"serial_nr", "device_type", "model"}
MAX_ROWS = 5000

NEW, UPDATE, SAME, ERROR = "new", "update", "same", "error"


class ImportFileError(Exception):
    pass


def languages():
    return [code for code, _name in settings.LANGUAGES]


def specifications():
    return list(Specification.objects.prefetch_related("device_types"))


# --- reading a file ----------------------------------------------------------------------------------------

def read_rows(name, data):
    """The rows of an uploaded file as dicts {column: value}; Excel cells keep their type (number, date)."""
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
    header = [str(h).strip() if h is not None else "" for h in next(rows, [])]
    return _with_header(header, rows)


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
    header = [h.strip() for h in next(rows, [])]
    return _with_header(header, rows)


def _with_header(header, rows):
    if "serial_nr" not in header:
        raise ImportFileError(_("The first row must hold the column names, with at least serial_nr. Download the "
                                "example file to see the columns."))
    result = []
    for values in rows:
        values = list(values or [])
        if not any(v not in (None, "") for v in values):
            continue  # empty row
        result.append({h: (values[i] if i < len(values) else None) for i, h in enumerate(header) if h})
        if len(result) > MAX_ROWS:
            raise ImportFileError(_("At most %(n)s devices per file.") % {"n": MAX_ROWS})
    return result


# --- understanding the values ------------------------------------------------------------------------------

def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = re.sub(r"[€\s]", "", str(value))
    if "," in text and "." in text:  # 1.234,50 or 1,234.50: the last one is the decimal sign
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(_("“%(value)s” is not an amount") % {"value": value}) from exc


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


def _whole(value):
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(_("“%(value)s” is not a whole number") % {"value": value}) from exc
    if number != number.to_integral_value() or number < 0:
        raise ValueError(_("“%(value)s” is not a whole number") % {"value": value})
    return int(number)


def _by_name(model, value, field="name"):
    """An object whose name in any language is `value` (ignoring case)."""
    query = Q()
    for lang in languages():
        query |= Q(**{f"{field}_{lang}__iexact": value})
    return model.objects.filter(query).first()


def _status(value):
    text = _text(value).lower()
    for code, label in Device.Status.choices:
        if text == code:
            return code
        for lang in languages():
            with translation.override(lang):
                if text == str(label).lower():
                    return code
    raise ValueError(_("unknown status “%(value)s”") % {"value": value})


YES = {"1", "yes", "ja", "y", "j", "true", "waar", "x", "wahr"}
NO = {"0", "no", "nee", "n", "false", "onwaar", "nein", "falsch"}


def _spec_value(spec, value):
    if value in (None, ""):
        return None
    if spec.kind == Specification.Kind.NUMBER:
        number = _decimal(value)
        return int(number) if number == number.to_integral_value() else float(number)
    if spec.kind == Specification.Kind.YES_NO:
        text = _text(value).lower()
        if text in YES:
            return True
        if text in NO:
            return False
        raise ValueError(_("“%(value)s” is not yes or no") % {"value": value})
    text = _text(value)
    if spec.kind == Specification.Kind.CHOICE:
        match = next((o for o in spec.options() if o.lower() == text.lower()), None)
        if match is None:
            raise ValueError(_("“%(value)s” is not one of the choices (%(choices)s)")
                             % {"value": value, "choices": ", ".join(spec.options())})
        return match
    return text


def clean_row(row, specs):
    """(values, errors) for one row: the fields present in the file, understood, plus "specs" for the
    specification columns that are present. Lookups that cannot fail later (brand) are kept as text."""
    values, errors = {}, []

    def take(key, convert):
        if key not in row:
            return
        try:
            values[key] = convert(row[key])
        except ValueError as exc:
            errors.append(f"{key}: {exc}")

    for key in ("serial_nr", "model", "supplier", "description"):
        take(key, _text)
    take("purchase_date", _date)
    take("purchase_price", _decimal)
    take("sale_price", _decimal)
    take("warranty_months", _whole)
    if "status" in row:
        values["status"] = None
        if _text(row["status"]):
            take("status", _status)
    if "brand" in row:
        values["brand"] = _text(row["brand"])
    if "device_type" in row:
        name = _text(row["device_type"])
        values["device_type"] = _by_name(DeviceType, name) if name else None
        if name and values["device_type"] is None:
            errors.append(_("device_type: unknown device type “%(value)s”") % {"value": name})
    if "condition" in row:
        name = _text(row["condition"])
        values["condition"] = _by_name(Condition, name) if name else None
        if name and values["condition"] is None:
            errors.append(_("condition: unknown condition “%(value)s”") % {"value": name})
    spec_values = {}
    for spec in specs:
        if spec.key in row:
            try:
                spec_values[spec.key] = _spec_value(spec, row[spec.key])
            except ValueError as exc:
                errors.append(f"{spec.key}: {exc}")
    values["specs"] = spec_values
    for key in REQUIRED:
        if key in row and not _text(row[key]):
            errors.append(_("%(column)s: required") % {"column": key})
    return values, errors


# --- check and import --------------------------------------------------------------------------------------

def _display(value):
    if value is None or value == "":
        return "–"
    if isinstance(value, bool):
        return _("Yes") if value else _("No")
    return str(value)


def _apply(device, values, specs):
    """Put the values on the device; returns [(field, old, new)] for what changes."""
    changes = []
    for key in FIELDS:
        if key not in values:
            continue
        new = values[key]
        if key == "brand":
            old = device.brand.name if device.brand_id else ""
            if (new or "").lower() != old.lower():
                changes.append((key, old, new))
                device.brand = (Vendor.objects.filter(name__iexact=new).first() or Vendor(name=new)) if new else None
            continue
        if key == "status" and new is None:
            new = device.status if device.pk else Device.Status.DRAFT
        if key in ("device_type", "condition"):  # related objects: compare by id (a new device has none yet)
            old_id = getattr(device, f"{key}_id")
            if old_id != (new.pk if new else None):
                changes.append((key, getattr(device, key) if old_id else None, new))
                setattr(device, key, new)
            continue
        old = getattr(device, key)
        if (old or None) != (new or None) and not (old == 0 and new == 0):
            changes.append((key, old, new))
            setattr(device, key, new)
    by_key = {s.key: s for s in specs}
    type_specs = set()
    if device.device_type_id:
        type_specs = {s.key for s in specs if any(t.pk == device.device_type_id for t in s.device_types.all())}
    current = dict(device.specs or {})
    for key, new in values.get("specs", {}).items():
        if new is not None and key not in type_specs:
            continue  # not a property of this type of device: left alone (checked in analyse)
        old = current.get(key)
        if old != new:
            changes.append((key, by_key[key].display(old), by_key[key].display(new)))
            if new is None:
                current.pop(key, None)
            else:
                current[key] = new
    device.specs = current
    return [(field, _display(old), _display(new)) for field, old, new in changes]


def analyse(rows):
    """What the import would do, per row: {line, serial_nr, model, action, errors, changes, device}."""
    specs = specifications()
    existing = {d.serial_nr.lower(): d for d in Device.objects.select_related("brand", "device_type")
                .filter(serial_nr__in=[_text(r.get("serial_nr")) for r in rows])}
    seen, result = set(), []
    for line, row in enumerate(rows, start=2):
        values, errors = clean_row(row, specs)
        serial = values.get("serial_nr", "")
        if serial.lower() in seen:
            errors.append(_("serial_nr: this serial number is already in an earlier row"))
        seen.add(serial.lower())
        device = existing.get(serial.lower())
        if device is None:
            for key in REQUIRED:
                if key not in row:
                    errors.append(_("%(column)s: required for a new device") % {"column": key})
            device = Device()
        changes = []
        if not errors:
            type_ = values.get("device_type") or (device.device_type if device.device_type_id else None)
            type_keys = {s.key for s in specs if type_ and any(t.pk == type_.pk for t in s.device_types.all())}
            for key, value in values["specs"].items():
                if value is not None and key not in type_keys:
                    errors.append(_("%(column)s: not a specification of %(type)s") % {"column": key, "type": type_})
            if type_:
                for spec in specs:
                    if spec.required and spec.key in type_keys and spec.key in values["specs"] \
                            and values["specs"][spec.key] is None:
                        errors.append(_("%(column)s: required for %(type)s") % {"column": spec.key, "type": type_})
        if not errors:
            changes = _apply(device, values, specs)  # on the object only; nothing is saved here
        action = ERROR if errors else (NEW if not device.pk else (UPDATE if changes else SAME))
        result.append({"line": line, "serial_nr": serial or "–", "model": values.get("model") or device.model,
                       "action": action, "errors": errors, "changes": changes, "device": device if device.pk else None})
    return result


@transaction.atomic
def run_import(rows, update_existing=True):
    """Imports the rows without errors; returns (added, updated, skipped)."""
    specs = specifications()
    added = updated = skipped = 0
    for row, outcome in zip(rows, analyse(rows)):
        if outcome["action"] == ERROR or outcome["action"] == SAME or (outcome["device"] and not update_existing):
            skipped += outcome["action"] != SAME
            continue
        values, _errors = clean_row(row, specs)
        device = Device.objects.filter(serial_nr__iexact=values["serial_nr"]).first() or Device()
        is_new = device.pk is None
        _apply(device, values, specs)
        if device.brand is not None and device.brand.pk is None:
            device.brand.save()
        if device.status == Device.Status.SOLD and device.sold_at is None:
            device.sold_at = timezone.now()
        device.save()
        added += is_new
        updated += not is_new
    return added, updated, skipped


# --- writing a file ----------------------------------------------------------------------------------------

def header(specs):
    return [key for key, _label in COLUMNS] + [s.key for s in specs]


def device_row(device, specs):
    values = {
        "number": device.number, "serial_nr": device.serial_nr, "device_type": str(device.device_type),
        "brand": device.brand.name if device.brand_id else "", "model": device.model,
        "condition": str(device.condition) if device.condition_id else "", "status": device.get_status_display(),
        "purchase_date": device.purchase_date, "purchase_price": device.purchase_price, "supplier": device.supplier,
        "sale_price": device.sale_price, "warranty_months": device.warranty_months, "description": device.description,
    }
    row = [values[key] for key, _label in COLUMNS]
    for spec in specs:
        value = (device.specs or {}).get(spec.key)
        row.append(("ja" if translation.get_language() == "nl" else "yes") if value is True
                   else ("nee" if translation.get_language() == "nl" else "no") if value is False else value)
    return row


def example_rows(specs):
    """A few made-up devices that show how the columns are filled in."""
    types = list(DeviceType.objects.all()[:2])
    conditions = list(Condition.objects.all()[:2])
    rows = []
    for i, (brand, model, price) in enumerate([("Dell", "Latitude 5440", "649.00"), ("HP", "EliteDesk 800 G6", "399.00")]):
        type_ = types[i % len(types)] if types else None
        row = {"number": "", "serial_nr": f"EXAMPLE-{i + 1}", "device_type": str(type_ or ""), "brand": brand,
               "model": model, "condition": str(conditions[i % len(conditions)]) if conditions else "",
               "status": str(Device.Status.FOR_SALE.label), "purchase_date": timezone.localdate(),
               "purchase_price": Decimal(price) * Decimal("0.7"), "supplier": "", "sale_price": Decimal(price),
               "warranty_months": 12, "description": ""}
        line = [row[key] for key, _label in COLUMNS]
        for spec in specs:
            applies = type_ is not None and any(t.pk == type_.pk for t in spec.device_types.all())
            line.append(_example_value(spec) if applies else "")
        rows.append(line)
    return rows


def _example_value(spec):
    if spec.kind == Specification.Kind.CHOICE:
        return (spec.options() or [""])[0]
    if spec.kind == Specification.Kind.NUMBER:
        return 8
    if spec.kind == Specification.Kind.YES_NO:
        return "ja" if translation.get_language() == "nl" else "yes"
    return ""


def explanation(specs):
    """Second sheet of the Excel file: what each column means and which values are allowed."""
    rows = [[_("Column"), _("Meaning")]]
    rows += [[key, str(label)] for key, label in COLUMNS]
    for spec in specs:
        kinds = spec.get_kind_display()
        if spec.kind == Specification.Kind.CHOICE:
            kinds += ": " + ", ".join(spec.options())
        types = ", ".join(str(t) for t in spec.device_types.all())
        rows.append([spec.key, f"{spec.name} ({kinds}{', ' + spec.unit if spec.unit else ''}) – {types}"])
    rows.append([])
    rows.append([_("Device types"), ", ".join(str(t) for t in DeviceType.objects.all())])
    rows.append([_("Conditions"), ", ".join(str(c) for c in Condition.objects.all())])
    rows.append([_("Statuses"), ", ".join(str(label) for _code, label in Device.Status.choices)])
    return rows


def write(rows, fmt, specs, with_explanation=False):
    """The file contents (bytes) in format "xlsx" or "csv"."""
    head = header(specs)
    if fmt == "csv":
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow(head)
        for row in rows:
            writer.writerow(["" if v is None else (str(v).replace(".", ",") if isinstance(v, Decimal) else v)
                             for v in row])
        return ("﻿" + out.getvalue()).encode("utf-8")
    from openpyxl import Workbook
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet.title = str(_("Devices"))[:31]
    sheet.append(head)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([float(v) if isinstance(v, Decimal) else v for v in row])
    for column, key in enumerate(head, start=1):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = max(12, min(40, len(key) + 4))
        if key in ("purchase_price", "sale_price"):
            for (cell,) in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
                cell.number_format = "#,##0.00"
        if key == "purchase_date":
            for (cell,) in sheet.iter_rows(min_row=2, min_col=column, max_col=column):
                cell.number_format = "yyyy-mm-dd"
    sheet.freeze_panes = "A2"
    if with_explanation:
        info = book.create_sheet(str(_("Explanation"))[:31])
        for row in explanation(specs):
            info.append(row)
        info.column_dimensions["A"].width = 22
        info.column_dimensions["B"].width = 100
        for cell in info[1]:
            cell.font = Font(bold=True)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
