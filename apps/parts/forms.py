import re

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.customers.models import Country
from apps.licences.models import Vendor

from .models import PartsSettings, PaymentMethod


class RequestLineForm(forms.Form):
    vendor = forms.ModelChoiceField(label=_("Brand"), queryset=Vendor.objects.none(), required=False)
    article_number = forms.CharField(label=_("Article number"), max_length=64, required=False)
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, initial=1, required=False)
    description = forms.CharField(label=_("Description"), max_length=255, required=False)
    machine_model = forms.CharField(label=_("Device model"), max_length=64, required=False)
    machine_serial = forms.CharField(label=_("Device serial number"), max_length=64, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vendor"].queryset = Vendor.objects.order_by("-at_top", "name")

    def clean_quantity(self):
        quantity, most = self.cleaned_data.get("quantity"), PartsSettings.load().max_quantity
        if quantity and quantity > most:
            raise forms.ValidationError(_("At most %(n)s per line.") % {"n": most})
        return quantity

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("article_number") and not cleaned.get("vendor"):
            self.add_error("vendor", _("Choose the brand."))
        vendor, number = cleaned.get("vendor"), cleaned.get("article_number", "")
        if vendor and number and vendor.product_nr_regex:
            try:
                ok = re.fullmatch(vendor.product_nr_regex, number)
            except re.error:
                ok = True
            if not ok:
                self.add_error("article_number", vendor.product_nr_help or _("This is not a valid article number."))
        return cleaned


class BaseRequestLineFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        if not self.lines():
            raise forms.ValidationError(_("Fill in at least one part."))

    def lines(self):
        return [{**f.cleaned_data, "quantity": f.cleaned_data.get("quantity") or 1}
                for f in self.forms if f.cleaned_data.get("article_number")]


RequestLineFormSet = forms.formset_factory(RequestLineForm, formset=BaseRequestLineFormSet, extra=5, max_num=50)


DELIVERY_FIELDS = ["delivery_name", "delivery_contact", "delivery_address", "delivery_postal_code", "delivery_city",
                   "delivery_country", "delivery_phone"]


class DeliveryForm(forms.Form):
    delivery_name = forms.CharField(label=_("Company"), max_length=200, required=False)
    delivery_contact = forms.CharField(label=_("Contact person"), max_length=200, required=False)
    delivery_address = forms.CharField(label=_("Address"), max_length=200, required=False)
    delivery_postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=False)
    delivery_city = forms.CharField(label=_("City"), max_length=100, required=False)
    delivery_country = forms.ChoiceField(label=_("Country"), required=False)
    delivery_phone = forms.CharField(label=_("Phone"), max_length=40, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delivery_country"].choices = [("", "---------")] + [
            (str(c), str(c)) for c in Country.objects.filter(is_active=True)]

    def require_address(self):
        for name in ("delivery_name", "delivery_address", "delivery_postal_code", "delivery_city", "delivery_country"):
            if not self.cleaned_data.get(name):
                self.add_error(name, _("Required."))

    def delivery(self):
        return {k: self.cleaned_data.get(k, "") for k in DELIVERY_FIELDS}


class RequestForm(DeliveryForm):
    reference = forms.CharField(label=_("Your reference"), max_length=45, required=False)
    urgent = forms.BooleanField(label=_("Urgent"), required=False,
                                help_text=_("We check whether urgent delivery is possible and what it costs."))

    field_order = ["reference", "urgent"]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("urgent"):
            self.require_address()
        return cleaned


class OrderForm(DeliveryForm):
    reference = forms.CharField(label=_("Your reference"), max_length=45, required=False,
                                help_text=_("Shown on the invoice."))
    payment_method = forms.ModelChoiceField(label=_("Payment method"), queryset=PaymentMethod.objects.none(),
                                            empty_label=None, widget=forms.RadioSelect)
    urgent = forms.BooleanField(label=_("Urgent delivery"), required=False)

    field_order = ["reference", "payment_method", "urgent"]

    def __init__(self, *args, urgent_costs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].queryset = PaymentMethod.objects.filter(is_active=True, for_parts=True)
        if urgent_costs is None:
            del self.fields["urgent"]
        else:
            from apps.dashboard.templatetags.humanize_nl import money

            self.fields["urgent"].help_text = _("Extra costs: € %(costs)s") % {"costs": money(urgent_costs)}

    def clean(self):
        cleaned = super().clean()
        self.require_address()
        return cleaned
