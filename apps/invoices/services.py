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


def create_for_order(order):
    """Make the invoice of an order, with a new number, and store its PDF."""
    sequence = NumberSequence.objects.get(key="invoice")
    result = check(sequence)
    if result.status == "behind":
        raise InvoiceNumberError(
            _("The invoice counter (%(next)s) is not above the highest existing invoice number (%(highest)s). "
              "Correct it under Number sequences first.") % {"next": sequence.next_number, "highest": result.highest}
        )
    rules = InvoiceSettings.load()
    customer = order.customer
    address = customer.address("invoice")
    with transaction.atomic():
        _n, number = NumberSequence.issue("invoice")
        today = timezone.localdate()
        invoice = Invoice.objects.create(
            number=number, customer=customer, order=order, issued_on=today,
            due_on=today + timedelta(days=rules.payment_term_days), reference=order.reference,
            customer_name=customer.name, customer_number=customer.number, customer_vat=customer.vat_number,
            address_attention=address.attention if address else "", address_line1=address.line1 if address else "",
            address_line2=address.line2 if address else "", address_postal_code=address.postal_code if address else "",
            address_city=address.city if address else "", address_country=str(address.country or "") if address else "",
            email=customer.email_for("invoices"),
            gross=order.gross, discount_pct=order.discount_pct, discount=order.discount, net=order.net,
            vat_rate=order.vat_rate, vat=order.vat, total=order.total,
        )
        for line in order.lines.select_related("pack", "extends"):
            description = line.description
            if line.extends:
                description = _("Extension of licence %(number)s: %(pack)s") % {"number": line.extends.full_number,
                                                                               "pack": line.description}
            InvoiceLine.objects.create(invoice=invoice, code=line.pack.code, description=description,
                                       quantity=line.quantity, unit_price=line.unit_price, amount=line.line_total)
        store_pdf(invoice)
    return invoice


def render_html(invoice):
    rules, site = InvoiceSettings.load(), SiteSettings.load()
    context = {
        "invoice": invoice, "lines": invoice.lines.all(), "site": site, "rules": rules,
        "company_address": site.address_for("invoice"),
        "payment_text": _fmt(rules.payment_text, days=rules.payment_term_days, number=invoice.number, iban=site.iban,
                             due_date=invoice.due_on.strftime("%d-%m-%Y") if invoice.due_on else ""),
        "logo_url": site.logo.path if site.logo else "",
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
