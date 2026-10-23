"""Blocks on the admin home page. Each block has a permission, so users only see what their role allows.

Add a block by writing a function that returns a context dict and registering it in WIDGETS.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.customers.models import Customer
from apps.licences.models import Licence
from apps.numbering.checks import check
from apps.numbering.models import NumberSequence


@dataclass
class Widget:
    key: str
    title: str
    permission: str | None
    template: str
    build: callable
    wide: bool = False


def stats(request):
    today = timezone.localdate()
    cards = []
    if request.user.has_perm("customers.view_customer"):
        changelist = reverse("admin:customers_customer_changelist")
        cards += [
            {"label": _("Active customers"), "value": Customer.objects.filter(status=Customer.Status.ACTIVE).count(),
             "url": f"{changelist}?status__exact=active", "icon": "storefront"},
            {"label": _("Sign-ups to approve"), "value": Customer.objects.filter(status=Customer.Status.PENDING).count(),
             "url": f"{changelist}?status__exact=pending", "icon": "how_to_reg", "warn": True},
        ]
    if request.user.has_perm("licences.view_licence"):
        changelist = reverse("admin:licences_licence_changelist")
        cards += [
            {"label": _("Licences"), "value": Licence.objects.count(), "url": changelist, "icon": "verified"},
            {"label": _("Not registered yet"), "value": Licence.objects.filter(registered_on__isnull=True).count(),
             "url": f"{changelist}?registered_on__isnull=True", "icon": "pending"},
            {"label": _("Ending within 90 days"),
             "value": Licence.objects.filter(end_date__gte=today, end_date__lte=today + timedelta(days=90)).count(),
             "url": f"{changelist}?end_date__gte={today}&end_date__lte={today + timedelta(days=90)}", "icon": "event_busy",
             "warn": True},
        ]
    if request.user.has_perm("numbering.view_numbersequence"):
        problems = sum(1 for seq in NumberSequence.objects.all() if check(seq).has_problem)
        cards.append({"label": _("Number sequences with problems"), "value": problems,
                      "url": reverse("admin:numbering_numbersequence_changelist"), "icon": "pin", "warn": True})
    return {"cards": cards}


def pending_signups(request):
    rows = Customer.objects.filter(status=Customer.Status.PENDING).order_by("-created_at")[:8]
    return {"rows": [(c.name, c.created_at, reverse("admin:customers_customer_change", args=[c.pk])) for c in rows],
            "empty": _("No sign-ups waiting.")}


def recent_registrations(request):
    rows = Licence.objects.filter(registered_on__isnull=False).select_related("customer").order_by("-registered_on")[:8]
    return {"rows": [(f"{lic.full_number} · {lic.customer.name}", lic.registered_on,
                      reverse("admin:licences_licence_change", args=[lic.pk])) for lic in rows],
            "empty": _("No registrations yet.")}


def ending_licences(request):
    today = timezone.localdate()
    rows = (Licence.objects.filter(end_date__gte=today, end_date__lte=today + timedelta(days=90))
            .select_related("customer").order_by("end_date")[:8])
    return {"rows": [(f"{lic.full_number} · {lic.customer.name}", lic.end_date,
                      reverse("admin:licences_licence_change", args=[lic.pk])) for lic in rows],
            "empty": _("No licences ending soon.")}


def recent_actions(request):
    entries = LogEntry.objects.filter(user=request.user).select_related("content_type").order_by("-action_time")[:8]
    return {"rows": [(f"{e.object_repr} ({e.content_type.name if e.content_type else ''})", e.action_time,
                      e.get_admin_url()) for e in entries],
            "empty": _("Nothing yet.")}


WIDGETS = [
    Widget("stats", _("Totals"), None, "dashboard/widget_stats.html", stats, wide=True),
    Widget("pending_signups", _("Sign-ups to approve"), "customers.view_customer", "dashboard/widget_list.html", pending_signups),
    Widget("recent_registrations", _("Recently registered licences"), "licences.view_licence", "dashboard/widget_list.html",
           recent_registrations),
    Widget("ending_licences", _("Licences ending soon"), "licences.view_licence", "dashboard/widget_list.html", ending_licences),
    Widget("recent_actions", _("My recent changes"), None, "dashboard/widget_list.html", recent_actions),
]
DEFAULT_ORDER = [w.key for w in WIDGETS]


def available(user):
    return {w.key: w for w in WIDGETS if not w.permission or user.is_superuser or user.has_perm(w.permission)}
