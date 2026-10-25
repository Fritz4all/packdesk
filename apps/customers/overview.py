"""The page a customer opens on in the admin: everything about the customer, read-only, with an edit button.

Each part (licences, orders, invoices, ...) is a section: a list of the latest items with a link to the
full, filtered list. Other apps add their own section with `register(...)`.
"""

from django.db.models import F
from django.urls import NoReverseMatch, reverse
from django.utils import formats
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

ROWS_SHOWN = 50

_SECTIONS = []


def register(key, title, model_label, queryset, columns, cells, filter_field="customer", order=100):
    """Add a section. `queryset(customer)` gives the items, `columns` the headers and `cells(item)` the
    values of one row. `filter_field` is the customer field to filter the full list on."""
    _SECTIONS.append(dict(key=key, title=title, model_label=model_label, queryset=queryset, columns=columns,
                          cells=cells, filter_field=filter_field, order=order))
    _SECTIONS.sort(key=lambda s: s["order"])


def _date(value):
    return formats.date_format(value, "SHORT_DATE_FORMAT") if value else "–"


def _money(value):
    return f"€ {formats.number_format(value, 2, force_grouping=True)}" if value is not None else "–"


def sections(request, customer):
    result = []
    for s in _SECTIONS:
        app_label, model_name = s["model_label"].split(".")
        if not request.user.has_perm(f"{app_label}.view_{model_name}"):
            continue
        items = s["queryset"](customer)
        count = items.count()
        rows = []
        for item in items[:ROWS_SHOWN]:
            try:
                url = reverse(f"admin:{app_label}_{model_name}_change", args=[item.pk])
            except NoReverseMatch:
                url = ""
            rows.append({"url": url, "cells": s["cells"](item)})
        try:
            all_url = reverse(f"admin:{app_label}_{model_name}_changelist") + f"?{s['filter_field']}__id__exact={customer.pk}"
        except NoReverseMatch:
            all_url = ""
        result.append({"key": s["key"], "title": s["title"], "columns": s["columns"], "rows": rows, "count": count,
                       "all_url": all_url if count > ROWS_SHOWN else "", "more": count - len(rows)})
    return result


# --- the sections PackDesk itself knows -------------------------------------------------------------


def _contacts(customer):
    return customer.contacts.select_related("user").order_by("-is_primary", "last_name")


def _contact_cells(c):
    if not c.user:
        login = gettext("No login")
    elif not c.user.is_active:
        login = gettext("Not active")
    elif not c.user.has_usable_password():
        login = gettext("Must choose a new password")
    else:
        login = gettext("Active")
    return [c.full_name + (" ★" if c.is_primary else ""), c.function, c.email, c.phone, login]


def _licences(customer):
    return customer.licences.select_related("pack", "system").order_by(F("start_date").desc(nulls_first=True), "-pk")


def _licence_cells(lic):
    return [lic.full_number, str(lic.pack), lic.description or (str(lic.system) if lic.system else ""), lic.serial_nr,
            _date(lic.start_date), _date(lic.end_date), lic.status.label]


def _orders(customer):
    return customer.orders.order_by("-created_at")


def _order_cells(order):
    return [order.number, _date(order.created_at), order.reference, _money(order.total)]


def _invoices(customer):
    return customer.invoices.order_by("-issued_on", "-number")


def _invoice_cells(inv):
    return [inv.number, _date(inv.issued_on), inv.reference, _money(inv.total),
            _date(inv.paid_on) if inv.paid_on else gettext("Not paid")]


def _faults(customer):
    return customer.fault_reports.order_by("-created_at")


def _fault_cells(f):
    return [f.number, _date(f.created_at), f"{f.vendor} {f.device}", f.serial_nr, f.get_status_display()]


register("contacts", _("Contacts"), "customers.contact", _contacts,
         [_("Name"), _("Function"), _("Email"), _("Phone"), _("Login")], _contact_cells, order=10)
register("licences", _("Licences"), "licences.licence", _licences,
         [_("Number"), _("Service pack"), _("Device"), _("Serial number"), _("Start"), _("End"), _("Status")],
         _licence_cells, order=20)
register("orders", _("Orders"), "orders.order", _orders,
         [_("Number"), _("Date"), _("Reference"), _("Total")], _order_cells, order=30)
register("invoices", _("Invoices"), "invoices.invoice", _invoices,
         [_("Number"), _("Date"), _("Reference"), _("Total"), _("Paid")], _invoice_cells, order=40)
register("faults", _("Fault reports"), "faults.faultreport", _faults,
         [_("Number"), _("Date"), _("Device"), _("Serial number"), _("Status")], _fault_cells, order=60)


def _part_requests(customer):
    return customer.part_requests.prefetch_related("lines").order_by("-created_at")


def _part_request_cells(r):
    return [r.number, _date(r.created_at), r.reference, len(r.lines.all()), r.get_status_display()]


def _part_orders(customer):
    return customer.part_orders.order_by("-created_at")


def _part_order_cells(o):
    return [o.number, _date(o.created_at), o.reference, _money(o.total), o.get_status_display()]


register("part_requests", _("Spare parts requests"), "parts.partrequest", _part_requests,
         [_("Number"), _("Date"), _("Reference"), _("Parts"), _("Status")], _part_request_cells, order=50)
register("part_orders", _("Spare parts orders"), "parts.partorder", _part_orders,
         [_("Number"), _("Date"), _("Reference"), _("Total"), _("Status")], _part_order_cells, order=55)


def _telephony_quotes(customer):
    return customer.telephony_quotes.order_by("-created_at")


def _print_quotes(customer):
    return customer.print_quotes.order_by("-created_at")


def _print_contracts(customer):
    return customer.print_contracts.order_by("-created_at")


register("telephony_quotes", _("Telephony quotes"), "telephony.quote", _telephony_quotes,
         [_("Number"), _("Date"), _("Reference"), _("View")],
         lambda q: [f"T{q.pk}", _date(q.created_at), q.reference, q.get_view_display()], order=57)
register("print_quotes", _("Printing quotes"), "printing.printquote", _print_quotes,
         [_("Number"), _("Date"), _("Reference")], lambda q: [q.number, _date(q.created_at), q.reference], order=58)
register("print_contracts", _("Printing contracts"), "printing.printcontract", _print_contracts,
         [_("Number"), _("End customer"), _("Start"), _("End")],
         lambda c: [c.number, c.company, _date(c.start_date), _date(c.end_date)], order=59)
