"""Invoice design: which parts of the invoice are shown, with which wording, and in which colours.

Stored as JSON on InvoiceSettings.design:

    {"elements": {key: {"on": bool, "label": {lang: text}, "value": {lang: text}}},
     "style": {"bar_color": "#rrggbb", "accent_color": "#rrggbb", "logo_height": 18}}

Anything not stored uses the standard: element on, standard wording in the invoice's language, the
website's colours.
"""

import re
from dataclasses import dataclass

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

LOGO_HEIGHT = (8, 40, 18)  # min, max, standard (mm)
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class Element:
    key: str
    name: str  # shown in the design editor
    label: str = ""  # standard wording on the invoice; empty = the element has no wording of its own
    value: str = ""  # standard fixed text next to the label, e.g. "Handled by: Administration"
    on: bool = True


GROUPS = [
    (_("Top of the invoice"), [
        Element("color_bar", _("Coloured bar")),
        Element("logo", _("Logo")),
        Element("customer_details", _("Customer details")),
        Element("invoice_number", _("Invoice number"), _("Invoice number")),
        Element("customer_number", _("Customer number"), _("Customer number")),
        Element("payment_hint", _("Payment hint"), _("Please mention these numbers with your payment")),
    ]),
    (_("Details"), [
        Element("our_reference", _("Our reference"), _("Our reference")),
        Element("handled_by", _("Handled by"), _("Handled by"), pgettext_lazy("department", "Administration")),
        Element("your_order", _("Your order"), _("Your order")),
        Element("customer_vat", _("Your VAT number"), _("Your VAT number")),
        Element("invoice_date", _("Invoice date"), _("Invoice date")),
        Element("due_date", _("Due date"), _("Due date")),
        Element("payment_method", _("Payment method"), _("Payment method"), _("On account")),
    ]),
    (_("Invoice lines"), [
        Element("line_number", _("Line number")),
        Element("article_code", _("Article number"), _("Article no.")),
        Element("product", _("Product"), _("Product")),
        Element("unit_price", _("Price each"), _("Price each")),
        Element("quantity", _("Quantity"), _("Quantity")),
        Element("amount", _("Amount"), _("Amount")),
        Element("discount_line", _("Discount line"), _("Discount")),
    ]),
    (_("Totals and texts"), [
        Element("net_total", _("Net total"), _("Net total")),
        Element("vat_total", _("VAT"), _("VAT")),
        Element("grand_total", _("Total amount"), _("Total amount")),
        Element("notice", _("Notice (Texts tab)")),
        Element("payment_text", _("Payment text (Texts tab)")),
    ]),
    (_("Footer"), [
        Element("footer_text", _("Footer text (Texts tab)")),
        Element("footer_address", _("Company name and address")),
        Element("footer_phone", _("Phone"), _("Phone")),
        Element("footer_email", _("Email"), _("Email")),
        Element("footer_web", _("Website"), _("Web")),
        Element("footer_iban", _("IBAN"), "IBAN"),
        Element("footer_coc", _("CoC number"), _("CoC")),
        Element("footer_vat", _("VAT number"), _("VAT")),
        Element("page_number", _("Page number"), _("page")),
    ]),
]
ELEMENTS = [element for _group, elements in GROUPS for element in elements]


@dataclass
class Shown:
    """One element as the invoice template sees it."""

    on: bool
    label: str
    value: str
    preview: bool

    @property
    def show(self):  # the preview also shows switched-off elements, faded, so they can be clicked
        return self.on or self.preview

    @property
    def cls(self):
        return "" if self.on else "pd-off"


def _text(stored, field, lang, standard):
    return ((stored.get(field) or {}).get(lang) or "").strip() or (str(standard) if standard else "")


def elements(design, lang, preview=False):
    """{key: Shown} in the given language."""
    stored = (design or {}).get("elements") or {}
    with translation.override(lang):
        return {
            el.key: Shown(
                on=bool(stored.get(el.key, {}).get("on", el.on)),
                label=_text(stored.get(el.key, {}), "label", lang, el.label),
                value=_text(stored.get(el.key, {}), "value", lang, el.value),
                preview=preview,
            )
            for el in ELEMENTS
        }


def style(design, site):
    stored = (design or {}).get("style") or {}
    low, high, standard = LOGO_HEIGHT
    try:
        logo_height = min(max(int(stored.get("logo_height", standard)), low), high)
    except (TypeError, ValueError):
        logo_height = standard
    return {
        "bar_color": stored.get("bar_color") if COLOR.match(stored.get("bar_color") or "") else site.primary_color,
        "accent_color": stored.get("accent_color") if COLOR.match(stored.get("accent_color") or "") else site.accent_color,
        "logo_height": logo_height,
    }


def from_form(data, site):
    """The design from the editor's submitted form. Wording equal to the standard is not stored, so a later
    improvement of the standard wording reaches this invoice too; the same goes for the website's colours."""
    languages = [code for code, _name in settings.LANGUAGES]
    result = {}
    for el in ELEMENTS:
        entry = {"on": data.get(f"on_{el.key}") == "1"}
        for field, standard in (("label", el.label), ("value", el.value)):
            if not standard:
                continue
            texts = {}
            for lang in languages:
                text = (data.get(f"{field}_{el.key}_{lang}") or "").strip()[:200]
                with translation.override(lang):
                    if text and text != str(standard):
                        texts[lang] = text
            if texts:
                entry[field] = texts
        result[el.key] = entry
    look = {}
    for name, site_color in (("bar_color", site.primary_color), ("accent_color", site.accent_color)):
        color = (data.get(name) or "").strip()
        if COLOR.match(color) and color.lower() != (site_color or "").lower():
            look[name] = color
    low, high, standard = LOGO_HEIGHT
    try:
        height = min(max(int(data.get("logo_height") or standard), low), high)
    except ValueError:
        height = standard
    if height != standard:
        look["logo_height"] = height
    return {"elements": result, "style": look}


def editor_rows(design, site):
    """Everything the editor page needs per group: element, on/off and the texts per language."""
    stored = (design or {}).get("elements") or {}
    languages = [code for code, _name in settings.LANGUAGES]
    groups = []
    for title, group in GROUPS:
        rows = []
        for el in group:
            saved = stored.get(el.key, {})
            fields = []
            for field, standard in (("label", el.label), ("value", el.value)):
                if not standard:
                    continue
                per_lang = []
                for lang in languages:
                    with translation.override(lang):
                        per_lang.append({"lang": lang, "name": f"{field}_{el.key}_{lang}",
                                         "value": (saved.get(field) or {}).get(lang, ""), "standard": str(standard)})
                fields.append({"field": field, "languages": per_lang})
            rows.append({"key": el.key, "name": el.name, "on": saved.get("on", el.on), "fields": fields})
        groups.append({"title": title, "rows": rows})
    return groups
