"""What staff do with requests and orders; used by the admin."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import emails
from .models import Correction, Delivery, PartOrder, PartRequest, PartsSettings, RequestLineChange


def answer(part_request, user, notify=True):
    """After staff saved a request: log the lines, update the status and validity, and email the customer
    once everything has been answered. Returns True when the email was sent."""
    for line in part_request.lines.all():
        RequestLineChange.objects.create(line=line, user=user, status=line.status, price_new=line.price_new,
                                         price_pack=line.price_pack, price_refurbished=line.price_refurbished)
    was = part_request.status
    part_request.update_status()
    if part_request.status != PartRequest.Status.ANSWERED or was == part_request.status:
        return False
    if not part_request.is_valid() or part_request.valid_until is None:
        part_request.valid_until = timezone.localdate() + timedelta(days=PartsSettings.load().quote_valid_days)
        part_request.save(update_fields=["valid_until"])
    if notify:
        emails.request_answered(part_request)
    return notify


def approve(order, user):
    order.status, order.approved_at, order.approved_by = PartOrder.Status.TO_DELIVER, timezone.now(), user
    order.save(update_fields=["status", "approved_at", "approved_by"])


def paid(order):
    """Payment received for an order that waited for it."""
    invoice = getattr(order, "invoice", None)
    if invoice is not None and not invoice.paid_on:
        invoice.paid_on = timezone.localdate()
        invoice.save(update_fields=["paid_on"])
    order.status = PartOrder.Status.TO_DELIVER
    order.save(update_fields=["status"])


def deliver(order, quantities, user):
    """quantities: {order line pk: number delivered now}. Returns True when the order is now complete."""
    with transaction.atomic():
        for line in order.lines.all():
            quantity = quantities.get(line.pk, 0)
            if quantity:
                Delivery.objects.create(line=line, quantity=quantity, user=user)
        complete = order.is_delivered()
        order.being_picked = False
        if complete:
            order.status = PartOrder.Status.DONE
        order.save(update_fields=["status", "being_picked"])
    emails.order_delivered(order, complete)
    return complete


def correct(order, quantities, reason, user):
    """quantities: {order line pk: negative number}. Returns the amount to credit (excl. VAT)."""
    credit = Decimal("0")
    with transaction.atomic():
        for line in order.lines.all():
            quantity = quantities.get(line.pk, 0)
            if quantity:
                Correction.objects.create(line=line, quantity=quantity, reason=reason, user=user)
                credit += -quantity * line.unit_price
        credit = (credit * (100 - order.discount_pct) / 100).quantize(Decimal("0.01"))
        if order.is_delivered() and order.status == PartOrder.Status.TO_DELIVER:
            order.status = PartOrder.Status.DONE
            order.save(update_fields=["status"])
    emails.order_changed(order, user, str(_("corrected")), reason, credit)
    return credit


def cancel(order, reason, user):
    order.status, order.cancelled_at, order.cancel_reason = PartOrder.Status.CANCELLED, timezone.now(), reason
    order.save(update_fields=["status", "cancelled_at", "cancel_reason"])
    emails.order_changed(order, user, str(_("cancelled")), reason, order.net)

