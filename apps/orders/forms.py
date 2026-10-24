from django import forms
from django.utils.translation import gettext_lazy as _

from apps.dashboard.templatetags.humanize_nl import money

from apps.licences.models import SupportPack


class PackChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj} – € {money(obj.price)}"


def grouped_pack_choices(queryset):
    groups = {}
    for pack in queryset.select_related("category"):
        groups.setdefault(str(pack.category), []).append((pack.pk, f"{pack} – € {money(pack.price)}"))
    return [("", "---------")] + list(groups.items())


class OrderLineForm(forms.Form):
    pack = PackChoiceField(label=_("Service pack"), queryset=SupportPack.objects.none(), required=False)
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, max_value=1000, initial=1, required=False)
    reference = forms.CharField(label=_("Reference"), max_length=128, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        packs = SupportPack.objects.filter(enabled=True).order_by("category__position", "price")
        self.fields["pack"].queryset = packs
        self.fields["pack"].choices = grouped_pack_choices(packs)


class BaseLineFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        if not self.lines():
            raise forms.ValidationError(_("Choose at least one service pack."))

    def lines(self):
        return [
            {"pack": f.cleaned_data["pack"], "quantity": f.cleaned_data.get("quantity") or 1,
             "reference": f.cleaned_data.get("reference", "")}
            for f in self.forms if f.cleaned_data.get("pack")
        ]


LineFormSet = forms.formset_factory(OrderLineForm, formset=BaseLineFormSet, extra=5, max_num=50)


class OrderDetailsForm(forms.Form):
    reference = forms.CharField(label=_("Your reference"), max_length=128, required=False,
                                help_text=_("Shown on the invoice."))
    send_boxes = forms.BooleanField(label=_("Send physical packs with labels"), required=False)
    delivery_name = forms.CharField(label=_("Company"), max_length=128, required=False)
    delivery_contact = forms.CharField(label=_("Contact person"), max_length=128, required=False)
    delivery_address = forms.CharField(label=_("Address"), max_length=200, required=False)
    delivery_postal_code = forms.CharField(label=_("Postal code"), max_length=20, required=False)
    delivery_city = forms.CharField(label=_("City"), max_length=100, required=False)

    def __init__(self, *args, allow_boxes=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not allow_boxes:
            for name in [n for n in self.fields if n.startswith("delivery_")] + ["send_boxes"]:
                del self.fields[name]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("send_boxes"):
            for name in ("delivery_name", "delivery_address", "delivery_postal_code", "delivery_city"):
                if not cleaned.get(name):
                    self.add_error(name, _("Required when packs are sent."))
        return cleaned

    def delivery(self):
        if not self.cleaned_data.get("send_boxes"):
            return None
        return {k: self.cleaned_data.get(k, "") for k in
                ("delivery_name", "delivery_contact", "delivery_address", "delivery_postal_code", "delivery_city")}


class ExtendForm(forms.Form):
    pack = PackChoiceField(label=_("Extension"), queryset=SupportPack.objects.none(), empty_label=None)
    reference = forms.CharField(label=_("Your reference"), max_length=128, required=False)

    def __init__(self, *args, packs, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pack"].queryset = packs
