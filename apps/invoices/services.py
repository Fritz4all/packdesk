"""Making, rendering and sending invoices."""

from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.db import transaction
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.numbering.checks import check
from apps.numbering.models import NumberSequence
from apps.siteconfig.language import in_customer_language
from apps.siteconfig.models import SiteSettings

from .models import Invoice, InvoiceEmail, InvoiceLine, InvoiceSettings


class InvoiceNumberError(Exception):
    """The invoice counter is behind the invoices that already exist; correct it first."""


def _fmt(text, **values):
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


def _check_counter():
    sequence = NumberSequence.objects.get(key="invoice")
    result = check(sequence)
    if result.status == "behind":
        raise InvoiceNumberError(
            _("The invoice counter (%(next)s) is not above the highest existing invoice number (%(highest)s). "
              "Correct it under Number sequences first.") % {"next": sequence.next_number, "highest": result.highest}
        )


def _create(customer, source, lines, gross=None, **links):
    """An invoice for `customer` with the totals of `source` (an order) and `lines` as
    (code, description, quantity, unit price, amount); stores its PDF. `gross` overrides the subtotal."""
    _check_counter()
    rules = InvoiceSettings.load()
    address = customer.address("invoice")
    with transaction.atomic():
        _n, number = NumberSequence.issue("invoice")
        today = timezone.localdate()
        invoice = Invoice.objects.create(
            number=number, customer=customer, issued_on=today,
            due_on=today + timedelta(days=rules.payment_term_days), reference=source.reference,
            customer_name=customer.name, customer_number=customer.number, customer_vat=customer.vat_number,
            address_attention=address.attention if address else "", address_line1=address.line1 if address else "",
            address_line2=address.line2 if address else "", address_postal_code=address.postal_code if address else "",
            address_city=address.city if address else "", address_country=str(address.country or "") if address else "",
            email=customer.email_for("invoices"),
            gross=source.gross if gross is None else gross, discount_pct=source.discount_pct, discount=source.discount, net=source.net,
            vat_rate=source.vat_rate, vat=source.vat, total=source.total, **links,
        )
        for code, description, quantity, unit_price, amount in lines:
            InvoiceLine.objects.create(invoice=invoice, code=code, description=description[:300], quantity=quantity,
                                       unit_price=unit_price, amount=amount)
        store_pdf(invoice)
    return invoice


def create_for_order(order):
    """Make the invoice of an order, with a new number, and store its PDF."""
    lines = []
    for line in order.lines.select_related("pack", "extends"):
        description = line.description
        if line.extends:
            description = _("Extension of licence %(number)s: %(pack)s") % {"number": line.extends.full_number,
                                                                           "pack": line.description}
        lines.append((line.pack.code, description, line.quantity, line.unit_price, line.line_total))
    return _create(order.customer, order, lines, order=order)


def create_for_part_order(order):
    """Make the invoice of a spare parts order: the parts, then the extra costs."""
    lines = []
    for line in order.lines.select_related("request_line"):
        part = line.request_line
        description = f"{part.description or part.article_number} ({line.get_packing_display()})"
        lines.append((part.article_number[:32], description, line.quantity, line.unit_price, line.line_total))
    for label, amount in order.costs():
        lines.append(("", str(label), 1, amount, amount))
    if order.vat_rate == 0 and order.delivery_costs:
        lines.append(("", _("VAT reverse-charged: intra-community delivery"), 1, 0, 0))
    # The subtotal includes the extra costs, so that subtotal − discount = total excl. VAT.
    gross = order.gross + sum((amount for _label, amount in order.costs()), 0)
    return _create(order.customer, order, lines, gross=gross, part_order=order)


def invoice_logo_path(rules, site):
    """The logo for invoices: the one set for invoices, otherwise the website's logo."""
    logo = rules.logo or site.logo
    return logo.path if logo else ""


def render_html(invoice):
    rules, site = InvoiceSettings.load(), SiteSettings.load()
    context = {
        "invoice": invoice, "lines": invoice.lines.all(), "site": site, "rules": rules,
        "company_address": site.address_for("invoice"),
        "payment_text": _fmt(rules.payment_text, days=rules.payment_term_days, number=invoice.number, iban=site.iban,
                             due_date=invoice.due_on.strftime("%d-%m-%Y") if invoice.due_on else ""),
        "logo_url": invoice_logo_path(rules, site),
    }
    with translation.override(site.language):
        if rules.custom_template.strip():
            return Template(rules.custom_template).render(Context(context))
        return render_to_string("invoices/invoice_pdf.html", context)


def render_pdf(invoice):
    from weasyprint import HTML

    return HTML(string=render_html(invoice), base_url=str(settings.MEDIA_ROOT)).write_pdf()


def store_pdf(invoice):
    invoice.pdf.save(invoice.filename, ContentFile(render_pdf(invoice)), save=True)


@in_customer_language
def send(invoice, to, by=None):
    rules, site = InvoiceSettings.load(), SiteSettings.load()
    recipients = [e.strip() for e in to.split(",") if e.strip()] if isinstance(to, str) else list(to)
    if not recipients:
        return False
    values = {"number": invoice.number, "company": site.display_name, "name": invoice.customer_name,
              "total": f"€ {invoice.total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}
    subject = _fmt(rules.email_subject or _("Invoice {number}"), **values)
    body = _fmt(rules.email_body or _("Attached is invoice {number}."), **values)
    message = EmailMessage(subject, body, sender(), recipients)
    message.attach(invoice.filename, invoice.pdf_bytes(), "application/pdf")
    message.send()
    InvoiceEmail.objects.create(invoice=invoice, sent_to=", ".join(recipients), sent_by=by)
    return True


def invoice_order(order):
    """Called after an order is placed: make and send the invoice if the settings say so.

    Returns (invoice or None, error message or None); the order itself always stays placed.
    """
    rules = InvoiceSettings.load()
    if not rules.auto_on_order or order.customer.no_pack_invoice:
        return None, None
    try:
        invoice = create_for_order(order)
    except InvoiceNumberError as exc:
        return None, str(exc)
    if rules.send_on_create:
        send(invoice, invoice.email or order.customer.email)
    return invoice, None


def invoice_part_order(order):
    """Like invoice_order, for a spare parts order (also when the customer gets no invoices for service packs)."""
    rules = InvoiceSettings.load()
    if not rules.auto_on_order:
        return None, None
    try:
        invoice = create_for_part_order(order)
    except InvoiceNumberError as exc:
        return None, str(exc)
    if rules.send_on_create:
        send(invoice, invoice.email or order.customer.email)
    return invoice, None
