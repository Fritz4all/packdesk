"""Compare an external database with PackDesk, using the table mappings set in the admin.

Per mapped part the rows of both sides are matched: first on the old ID (stored in PackDesk as
`legacy_id`), then on the part's natural key (customer number, licence number, invoice number,
email address, ...). The result shows rows only in the external database, only in PackDesk, and
matched rows whose mapped values differ. Nothing is ever written to the external database.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.urls import reverse
from django.utils.translation import gettext as _

from apps.numbering.models import NumberSequence

from .connection import ExternalDatabaseError
from .parts import PARTS, PARTS_BY_KEY, archive_numbers


# --- normalising values -------------------------------------------------------------------------


def _text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value).strip()


def _number(value):
    """Numbers as text; digits without leading zeros, so 0001017494 and 1017494 are the same."""
    text = _text(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    return (text.lstrip("0") or "0") if text.isdigit() else text.upper()


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
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _bool(value):
    if isinstance(value, (bytes, str)):
        return _text(value).lower() in ("1", "true", "t", "yes", "\x01")
    return bool(value)


NORMALISE = {
    "text": _text, "email": lambda v: _text(v).lower(), "upper": lambda v: _text(v).upper(),
    "number": _number, "decimal": _decimal, "date": _date, "bool": _bool,
}


def normalise(part, name, value):
    return NORMALISE[part.by_name[name].kind](value) if name in part.by_name else _text(value)


def show(value):
    if value is None or value == "":
        return "—"
    if value is True:
        return _("yes")
    if value is False:
        return _("no")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    return str(value)


def label(part, row):
    text = " · ".join(show(row.get(name)) for name in part.title if row.get(name) not in (None, ""))
    return text or f"#{row.get('_id') or row.get('pk') or '?'}"


def admin_link(part, row):
    pk = row.get(part.admin_pk)
    return reverse(part.admin_url, args=[pk]) if part.admin_url and pk else ""


# --- reading mapped rows ------------------------------------------------------------------------


def mapped_rows(mapping, reader, limit=None):
    """Rows of the external source, renamed to PackDesk field names; `_id` is the old ID."""
    columns = {f.field: f.column for f in mapping.fields.all()}
    sql = mapping.select_sql()
    if limit:
        sql = f"SELECT * FROM ({sql}) packdesk_preview LIMIT {int(limit)}"
    rows = []
    for raw in reader.rows(sql):
        lower = {str(k).lower(): v for k, v in raw.items()}
        if mapping.skip_column and _text(lower.get(mapping.skip_column.lower())) == mapping.skip_value:
            continue
        row = {name: lower.get(column.lower()) for name, column in columns.items()}
        row["_id"] = _text(lower.get(mapping.id_column.lower())) if mapping.id_column else ""
        rows.append(row)
    return rows


def source_columns(mapping, reader):
    """Column names of a mapping's source (for help while mapping)."""
    rows = reader.rows(f"SELECT * FROM ({mapping.select_sql()}) packdesk_columns LIMIT 1")
    if rows:
        return list(rows[0])
    return reader.columns(f"SELECT * FROM ({mapping.select_sql()}) packdesk_columns LIMIT 0")


# --- comparing ----------------------------------------------------------------------------------


@dataclass
class Result:
    part: object
    mapped_fields: list = field(default_factory=list)
    old_count: int = 0
    new_count: int = 0
    matched: int = 0
    only_old: list = field(default_factory=list)
    only_new: list = field(default_factory=list)
    different: list = field(default_factory=list)  # (old, new, [(label, old value, new value)])
    error: str = ""

    def summary(self):
        return {"key": self.part.key, "label": str(self.part.label), "note": str(self.part.note), "old": self.old_count,
                "new": self.new_count, "only_old": len(self.only_old), "only_new": len(self.only_new),
                "different": len(self.different), "same": self.matched - len(self.different), "error": self.error}


def _natural(part, row, mapped):
    names = [n for n in part.natural if n in mapped]
    if not names:
        return None
    key = tuple(normalise(part, n, row.get(n)) for n in names)
    return key if any(k not in ("", None) for k in key) else None


def compare_mapping(mapping, reader):
    part = PARTS_BY_KEY[mapping.part]
    mapped = {f.field for f in mapping.fields.all()}
    result = Result(part, mapped_fields=[f for f in part.fields if f.name in mapped])
    try:
        old_rows = mapped_rows(mapping, reader)
    except ExternalDatabaseError as exc:
        result.error = str(exc)
        return result
    new_rows = list(part.rows())
    result.old_count, result.new_count = len(old_rows), len(new_rows)

    use_id = part.has_legacy_id and bool(mapping.id_column)
    by_legacy = {_text(n.get("legacy_id")): n for n in new_rows if use_id and _text(n.get("legacy_id"))}
    used, pairs, unmatched = set(), [], []
    for old in old_rows:
        new = by_legacy.get(old["_id"]) if use_id and old["_id"] else None
        if new is not None and id(new) not in used:
            used.add(id(new))
            pairs.append((old, new))
        else:
            unmatched.append(old)
    by_natural = {}
    for n in new_rows:
        if id(n) not in used and (key := _natural(part, n, mapped)):
            by_natural.setdefault(key, []).append(n)
    for old in unmatched:
        candidates = by_natural.get(_natural(part, old, mapped) or ())
        if candidates:
            new = candidates.pop(0)
            used.add(id(new))
            pairs.append((old, new))
        else:
            result.only_old.append(old)
    result.only_new = [n for n in new_rows if id(n) not in used]
    result.matched = len(pairs)
    for old, new in pairs:
        diffs = []
        for f in result.mapped_fields:
            a, b = normalise(part, f.name, old.get(f.name)), normalise(part, f.name, new.get(f.name))
            if a != b:
                diffs.append((str(f.label), show(a), show(b)))
        if diffs:
            result.different.append((old, new, diffs))
    return result


@dataclass
class ArchivePart:
    """Pseudo part: invoices of the external database against the PDF files in the archive folder."""

    key: str = "invoice_pdfs"
    label: str = ""
    note: str = ""
    title: tuple = ("number", "file")
    admin_url: str = ""
    admin_pk: str = "pk"


def compare_archive(mapping, reader):
    part = ArchivePart(label=_("Invoice PDFs in archive"),
                       note=_("Invoices in the old database against the PDF files in the archive folder."))
    result = Result(part)
    try:
        old = {_number(r.get("number")): r for r in mapped_rows(mapping, reader) if r.get("number") not in (None, "")}
    except ExternalDatabaseError as exc:
        result.error = str(exc)
        return result
    files = archive_numbers()
    result.old_count, result.new_count = len(old), len(files)
    result.only_old = [row for number, row in old.items() if number not in files]
    result.only_new = [{"number": number, "file": name} for number, name in files.items() if number not in old]
    result.matched = len(set(old) & set(files))
    return result


def compare_all(db, reader):
    """Results for every mapped part, and the parts that have no mapping yet."""
    mappings = {m.part: m for m in db.mappings.filter(enabled=True).prefetch_related("fields")}
    results = [compare_mapping(mappings[p.key], reader) for p in PARTS if p.key in mappings]
    if "invoices" in mappings and "number" in {f.field for f in mappings["invoices"].fields.all()}:
        results.append(compare_archive(mappings["invoices"], reader))
    return results, [p for p in PARTS if p.key not in mappings]


def part_for(key):
    if key == "invoice_pdfs":
        return ArchivePart(label=_("Invoice PDFs in archive"))
    return PARTS_BY_KEY.get(key)


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


def number_tops(db, reader):
    """Highest numbers in the external database against the next number in PackDesk."""
    sequences = {s.key: s for s in NumberSequence.objects.all()}
    rows = []
    for mapping in db.mappings.filter(enabled=True).prefetch_related("fields"):
        part = PARTS_BY_KEY[mapping.part]
        if not part.sequence or part.number_field not in {f.field for f in mapping.fields.all()}:
            continue
        try:
            highest = _highest([_text(r.get(part.number_field)) for r in mapped_rows(mapping, reader)])
        except ExternalDatabaseError:
            highest = None
        seq = sequences.get(part.sequence)
        next_number = seq.preview() if seq else None
        rows.append({
            "label": str(part.label), "old": highest, "next": next_number,
            "ok": _is_above(next_number, highest),
            "url": reverse("admin:numbering_numbersequence_change", args=[seq.pk]) if seq else "",
        })
    return rows


# --- searching ----------------------------------------------------------------------------------


def search(db, reader, q):
    """Where a number, name, serial number or email address occurs: external database, PackDesk, or both."""
    needle = q.strip().lower()
    results = []
    for mapping in db.mappings.filter(enabled=True).prefetch_related("fields"):
        part = PARTS_BY_KEY[mapping.part]
        error = ""
        try:
            old = [r for r in mapped_rows(mapping, reader)
                   if any(needle in _text(v).lower() for k, v in r.items() if k != "_id")]
        except ExternalDatabaseError as exc:
            old, error = [], str(exc)
        names = [f.name for f in part.fields]
        new = [r for r in part.rows() if any(needle in _text(r.get(name)).lower() for name in names)]
        results.append({
            "label": str(part.label), "error": error,
            "old": [label(part, r) for r in old[:50]], "old_total": len(old),
            "new": [(label(part, r), admin_link(part, r)) for r in new[:50]], "new_total": len(new),
        })
    return results
