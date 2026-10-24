"""Reading the previous webshop's invoice PDFs (made with iText) so they can be found and shown per customer.

The PDFs are read with `pdftotext -layout`; the old layout has fixed labels:
"Factuurnummer", "Debiteurnummer", "Factuurdatum", a "BTW xx% € …" line and the total on the last
amount line. The original files are never changed.
"""

import os
import re
import subprocess
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

AMOUNT = r"(-?[\d.]+,\d{2})"


def pdf_text(path):
    result = subprocess.run(["pdftotext", "-layout", "-q", path, "-"], capture_output=True, timeout=30)
    return result.stdout.decode("utf-8", errors="replace")


def _amount(text):
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _date(text):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _left(line):
    """Text in the left column, i.e. before a gap of 3+ spaces."""
    return re.split(r"\s{3,}", line.strip())[0].strip() if line.strip() else ""


def parse(text):
    """Fields found in an old invoice; missing fields are left out."""
    lines = text.splitlines()
    data = {}
    for line in lines:
        if m := re.search(r"Factuurnummer\s+(\S+)", line):
            data["number"] = m.group(1)
        if m := re.search(r"Debiteurnummer\s+(\S+)", line):
            data["customer_number"] = m.group(1)
        if m := re.search(r"Factuurdatum\s+(\S+)", line):
            data["issued_on"] = _date(m.group(1))
        if m := re.search(r"BTW\s+([\d.,]+)\s*%\s*€\s*" + AMOUNT, line):
            data["vat_rate"] = _amount(m.group(1).replace(".", ",") if "," not in m.group(1) else m.group(1))
            data["vat"] = _amount(m.group(2))
    totals = [m.group(1) for line in lines if (m := re.search(r"€\s*" + AMOUNT + r"\s*$", line))]
    if totals:
        data["total"] = _amount(totals[-1])
    # Addressee: the left column of the first lines (name, attention, address, postal code + city).
    left = [_left(line) for line in lines[:8]]
    left = [part for part in left if part and not part.startswith(("Onze referentie", "Behandeld door", "Uw "))]
    if left:
        data["customer_name"] = left[0]
    rest = left[1:]
    if rest and rest[0].lower().startswith("t.a.v"):
        data["address_attention"] = rest.pop(0).split(" ", 1)[-1]
    if rest:
        data["address_line1"] = rest.pop(0)
    if rest and (m := re.match(r"(\d{4}\s?[A-Z]{2})\s+(.+)", rest[0])):
        data["address_postal_code"], data["address_city"] = m.group(1), m.group(2)
    if not data.get("issued_on"):
        # Some old invoices have an empty "Factuurdatum"; take the first date anywhere in the text.
        if m := re.search(r"\b(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})\b", text):
            data["issued_on"] = _date(m.group(1))
    if data.get("total") is not None and data.get("vat") is not None:
        data["net"] = data["total"] - data["vat"]
    return data


def to_invoice_fields(data, fallback_date=None):
    """Model fields from parsed data. Without a date in the PDF, the file date is used (when the previous webshop
    wrote the PDF, which is the invoice date)."""
    fields = {k: v for k, v in data.items() if k != "number" and v not in (None, "")}
    fields.setdefault("issued_on", fallback_date or date(1970, 1, 1))
    return fields


def file_date(path):
    return date.fromtimestamp(os.path.getmtime(path))
