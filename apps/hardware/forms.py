from django import forms
from django.utils.translation import gettext_lazy as _

from . import services
from .models import DeliveryOption

ADDRESS_FIELDS = ["delivery_name", "delivery_contact", "delivery_address", "delivery_postal_code", "delivery_city"]


class CheckoutForm(forms.Form):
    delivery = forms.ModelChoiceField(label=_("Delivery"), queryset=DeliveryOption.objects.none(),
                                      widget=forms.RadioSelect, empty_label=None)
    payment = forms.ModelChoiceField(label=_("Payment method"), queryset=services.PaymentMethod.objects.none(),
                                     widget=forms.RadioSelect, empty_label=None)
    reference = forms.CharField(label=_("Your reference"), max_length=128, required=False,
                                help_text=_("Shown on the invoice."))
    delivery_name = forms.CharField(label=_("Company"), max_length=128, required=False)
    delivery_contact = forms.CharField(label=_("Contact person"), max_length=128, required=False)
    delivery_address = forms.CharField(label=_("Address"), max_length=200, required=False)
    delivery_postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=False)
    delivery_city = forms.CharField(label=_("City"), max_length=100, required=False)
    accept_terms = forms.BooleanField(label=_("I agree to the terms"), required=False)

    def __init__(self, *args, terms="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["delivery"].queryset = services.delivery_options()
        self.fields["payment"].queryset = services.payment_methods()
        self.fields["delivery"].label_from_instance = self._delivery_label
        self.fields["payment"].label_from_instance = self._payment_label
        for field in ("delivery", "payment"):
            first = self.fields[field].queryset.first()
            if first is not None and not self.initial.get(field):
                self.initial[field] = first.pk
        self.terms = terms
        if not terms:
            del self.fields["accept_terms"]

    @staticmethod
    def _delivery_label(option):
        from apps.dashboard.templatetags.humanize_nl import money

        return f"{option.name} (€ {money(option.price)} {_('excl. VAT')})" if option.price else str(option.name)

    @staticmethod
    def _payment_label(method):
        from apps.dashboard.templatetags.humanize_nl import money

        return f"{method.name} (+ € {money(method.extra_costs)})" if method.extra_costs else str(method.name)

    def clean(self):
        cleaned = super().clean()
        option = cleaned.get("delivery")
        if option is not None and option.kind == DeliveryOption.Kind.SHIPPING:
            for name in ("delivery_name", "delivery_address", "delivery_postal_code", "delivery_city"):
                if not (cleaned.get(name) or "").strip():
                    self.add_error(name, _("Needed for shipping."))
        if self.terms and not cleaned.get("accept_terms"):
            self.add_error("accept_terms", _("Please agree to the terms to order."))
        return cleaned

    def address(self):
        return {name: (self.cleaned_data.get(name) or "").strip() for name in ADDRESS_FIELDS}
