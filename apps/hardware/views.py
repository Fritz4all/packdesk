"""The hardware shop on the website: everything for sale, open to visitors (with prices), filters, and a page
per device. Logged-in customers see their own price (their hardware discount taken off)."""

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.licences.models import Vendor

from . import pricing
from .models import Condition, Device, DeviceType, HardwareSettings, Specification

def _settings():
    settings = HardwareSettings.load()
    if not settings.enabled:
        raise Http404
    return settings


def _for_sale():
    return Device.objects.filter(status=Device.Status.FOR_SALE).select_related("device_type", "brand", "condition")


def _spec_rows(device, specs):
    """[(name, value)] of the device's specifications, in the order of the specifications."""
    values = device.specs or {}
    return [(spec.name, spec.display(values[spec.key])) for spec in specs
            if spec.key in values and values[spec.key] not in (None, "")
            and any(t.pk == device.device_type_id for t in spec.device_types.all())]


def shop(request):
    settings = _settings()
    devices = _for_sale().prefetch_related("photos")
    chosen = {key: request.GET.get(key, "") for key in ("type", "brand", "condition", "q", "sort")}
    if chosen["type"].isdigit():
        devices = devices.filter(device_type_id=chosen["type"])
    if chosen["brand"].isdigit():
        devices = devices.filter(brand_id=chosen["brand"])
    if chosen["condition"].isdigit():
        devices = devices.filter(condition_id=chosen["condition"])
    if chosen["q"].strip():
        words = chosen["q"].split()
        for word in words[:5]:
            devices = devices.filter(Q(model__icontains=word) | Q(brand__name__icontains=word)
                                     | Q(device_type__name__icontains=word) | Q(description__icontains=word)
                                     | Q(number__iexact=word))
    devices = list(devices.order_by("-created_at"))
    customer = pricing.shop_customer(request)
    for device in devices:
        device.shop_price = pricing.price(device, customer, settings)
    if chosen["sort"] in ("price", "-price"):  # the price can come from the markup, so it is sorted here
        sign = -1 if chosen["sort"] == "-price" else 1
        devices.sort(key=lambda d: (d.shop_price is None, sign * d.shop_price["excl"] if d.shop_price else 0))
    page = Paginator(devices, settings.per_page).get_page(request.GET.get("page"))
    specs = [s for s in Specification.objects.prefetch_related("device_types") if s.in_list]
    for device in page:
        device.spec_rows = _spec_rows(device, specs)[:4]
    on_sale = Device.objects.filter(status=Device.Status.FOR_SALE)
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("vat", None)
    return render(request, "hardware/shop.html", {
        "settings": settings, "page": page, "chosen": chosen, "customer": customer,
        "incl_vat": pricing.show_incl_vat(request, settings), "query": query.urlencode(),
        "types": DeviceType.objects.filter(is_active=True, devices__in=on_sale).distinct(),
        "brands": Vendor.objects.filter(devices__in=on_sale).distinct().order_by("name"),
        "conditions": Condition.objects.filter(device__in=on_sale).distinct(),
        "total": len(devices),
    })


def device_detail(request, number):
    settings = _settings()
    device = get_object_or_404(Device.objects.select_related("device_type", "brand", "condition")
                               .prefetch_related("photos"), number=number)
    available = device.status == Device.Status.FOR_SALE
    if device.status in (Device.Status.DRAFT, Device.Status.WRITTEN_OFF):
        raise Http404
    customer = pricing.shop_customer(request)
    specs = Specification.objects.prefetch_related("device_types")
    return render(request, "hardware/device.html", {
        "settings": settings, "device": device, "available": available, "customer": customer,
        "price": pricing.price(device, customer, settings) if available else None,
        "incl_vat": pricing.show_incl_vat(request, settings), "spec_rows": _spec_rows(device, specs),
        "photos": list(device.photos.all()),
    })
