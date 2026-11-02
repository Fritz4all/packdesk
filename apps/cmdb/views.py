from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from apps.customers.models import customer_of

from .models import CmdbCustomer, CmdbSettings


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
    items = customer.configuration_items.select_related("item_type").order_by("name")[:500]
    return render(request, "cmdb/my_items.html", {"items": items})
