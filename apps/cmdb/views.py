import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import RequestDataTooBig
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import formats
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.customers.models import customer_of

from . import discovery, fields
from .models import CmdbCustomer, CmdbSettings

# What a customer sees of an item; the internal description is not for them.
PORTAL_COLUMNS = ["name", "item_type", "status", "serial_nr", "location", "warranty_until"]


def portal_customer(user):
    """The customer whose items this login may see, or None."""
    customer = customer_of(user)
    if customer is None or not CmdbSettings.load().enabled:
        return None
    allowed = CmdbCustomer.objects.filter(customer=customer, enabled=True, portal_access=True).exists()
    return customer if allowed else None


@login_required
def my_items(request):
    customer = portal_customer(request.user)
    if customer is None:
        raise Http404
    hidden, labels = fields.hidden(), fields.labels()
    keys = [key for key in PORTAL_COLUMNS if key not in hidden]
    items = customer.configuration_items.select_related("item_type", "status").order_by("name")[:500]
    rows = [{"number": item.number, "cells": [_portal_value(getattr(item, key)) for key in keys]} for item in items]
    return render(request, "cmdb/my_items.html", {"columns": [labels.get(key, key) for key in keys], "rows": rows})


def _portal_value(value):
    if value is None:
        return ""
    return formats.date_format(value) if hasattr(value, "isoformat") else str(value)


@csrf_exempt
@require_POST
def discovery_report(request):
    """Where a discovery script sends what it found. It identifies itself with its key, not with a login."""
    header = request.headers.get("Authorization", "")
    source = discovery.source_for(header.removeprefix("Bearer ").strip()) if header.startswith("Bearer ") else None
    if source is None:
        return JsonResponse({"error": "unknown key"}, status=401)
    try:
        payload = json.loads(request.body)
    except RequestDataTooBig:
        return JsonResponse({"error": "too large"}, status=413)
    except ValueError:
        return JsonResponse({"error": "not JSON"}, status=400)
    try:
        return JsonResponse(discovery.report(source, payload))
    except discovery.ReportError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
