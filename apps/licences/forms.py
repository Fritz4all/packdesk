import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import HardwareSystem, Licence, OptionType, Vendor

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class LicenceNumberForm(forms.Form):
    number = forms.CharField(label=_("Licence number"), max_length=40, help_text=_("For example 26A0001ABC-1"))

    def clean_number(self):
        licence = Licence.find(self.cleaned_data["number"])
        if licence is None:
            raise ValidationError(_("No licence with this number was found."))
        if not licence.pack.registration_required:
            raise ValidationError(_("This licence does not need to be registered."))
        if licence.registered_on:
            raise ValidationError(_("This licence has already been registered."))
        self.licence = licence
        return self.cleaned_data["number"]


class EndCustomerForm(forms.Form):
    email = forms.EmailField(label=_("Email address end customer"), help_text=_("The service certificate is sent here."))
    reference = forms.CharField(label=_("Reference"), max_length=128, required=False)
    memo = forms.CharField(label=_("Memo"), required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ResellerForm(forms.Form):
    name = forms.CharField(label=_("Reseller name"), max_length=128)
    address = forms.CharField(label=_("Address"), max_length=200)
    postal_code = forms.CharField(label=_("Postal code"), max_length=20)
    city = forms.CharField(label=_("City"), max_length=100)
    phone = forms.CharField(label=_("Phone"), max_length=40)


class SystemChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name


class DeviceForm(forms.Form):
    """Device details. Shows a list of device types if the pack's hardware class has any, otherwise brands."""

    system = SystemChoiceField(label=_("Brand and type"), queryset=HardwareSystem.objects.none(), required=False)
    vendor = forms.ModelChoiceField(label=_("Brand"), queryset=Vendor.objects.filter(is_real_vendor=True), required=False)
    product_nr = forms.CharField(label=_("Article number"), max_length=64, required=False)
    description = forms.CharField(label=_("Description"), max_length=128)
    serial_nr = forms.CharField(label=_("Serial number"), max_length=64)
    purchase_date = forms.DateField(label=_("Purchase date"), widget=DATE)
    start_date = forms.DateField(label=_("Start date of cover"), widget=DATE)

    def __init__(self, *args, licence, **kwargs):
        super().__init__(*args, **kwargs)
        self.licence = licence
        systems = HardwareSystem.objects.filter(hardware_class=licence.pack.hardware_class, visible=True).select_related("vendor")
        if systems.exists():
            self.fields["system"].queryset = systems
            self.fields["system"].required = True
            self.fields["system"].choices = self._grouped(systems)
            del self.fields["vendor"]
        else:
            del self.fields["system"]
            self.fields["vendor"].required = True
        if licence.pack.period.post_warranty:
            self.fields["purchase_date"].required = False
        else:
            del self.fields["start_date"]

    @staticmethod
    def _grouped(systems):
        groups = {}
        for system in systems:
            groups.setdefault(system.vendor.name, []).append((system.pk, system.name))
        return [("", "---------")] + list(groups.items())

    def clean(self):
        cleaned = super().clean()
        vendor = cleaned["system"].vendor if cleaned.get("system") else cleaned.get("vendor")
        cleaned["vendor_obj"] = vendor
        product_nr = cleaned.get("product_nr", "")
        if vendor and vendor.product_nr_regex and product_nr is not None:
            if not re.fullmatch(vendor.product_nr_regex, product_nr):
                self.add_error("product_nr", _("This article number is not valid. %(help)s") % {"help": vendor.product_nr_help})
        if not self.errors:
            try:
                start, end = self.licence.cover_dates(cleaned.get("purchase_date"), cleaned.get("start_date"))
            except ValidationError as exc:
                for field, errors in exc.message_dict.items():
                    self.add_error(field if field in self.fields else None, errors)
            else:
                cleaned["cover_start"], cleaned["cover_end"] = start, end
        return cleaned


class MonitorForm(forms.Form):
    vendor = forms.ModelChoiceField(label=_("Brand"), queryset=Vendor.objects.all(), required=False)
    product_nr = forms.CharField(label=_("Article number"), max_length=64, required=False)
    description = forms.CharField(label=_("Description"), max_length=128, required=False)
    serial_nr = forms.CharField(label=_("Serial number"), max_length=64, required=False)

    def clean(self):
        cleaned = super().clean()
        filled = any(cleaned.get(f) for f in ("product_nr", "description", "serial_nr"))
        if filled and not cleaned.get("vendor"):
            self.add_error("vendor", _("Choose the brand of the monitor."))
        cleaned["filled"] = filled
        return cleaned


class OptionForm(forms.Form):
    option_type = forms.ModelChoiceField(label=_("Type"), queryset=OptionType.objects.none(), required=False)
    vendor = forms.ModelChoiceField(label=_("Brand"), queryset=Vendor.objects.all(), required=False)
    quantity = forms.IntegerField(label=_("Quantity"), min_value=1, max_value=50, initial=1, required=False)
    product_nr = forms.CharField(label=_("Article number"), max_length=64, required=False)
    description = forms.CharField(label=_("Description"), max_length=128, required=False)

    def __init__(self, *args, option_types=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["option_type"].queryset = option_types if option_types is not None else OptionType.objects.none()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("option_type") and not cleaned.get("description"):
            self.add_error("description", _("Describe the option."))
        return cleaned


class BaseOptionFormSet(forms.BaseFormSet):
    def __init__(self, *args, licence, **kwargs):
        self.licence = licence
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        types = self.licence.pack.category.option_types.filter(is_monitor=False)
        return {"option_types": types}

    def clean(self):
        if any(self.errors):
            return
        internal = external = 0
        for form in self.forms:
            option_type = form.cleaned_data.get("option_type")
            if not option_type:
                continue
            quantity = form.cleaned_data.get("quantity") or 1
            if option_type.internal:
                internal += quantity
            else:
                external += quantity
        pack = self.licence.pack
        if internal > pack.max_internal_options:
            raise ValidationError(_("At most %(n)s internal options are covered.") % {"n": pack.max_internal_options})
        if external > pack.max_external_options:
            raise ValidationError(_("At most %(n)s external options are covered.") % {"n": pack.max_external_options})

    def rows(self):
        out = []
        for form in self.forms:
            data = form.cleaned_data
            if data.get("option_type"):
                out.append({
                    "option_type": data["option_type"].pk,
                    "vendor": data["vendor"].pk if data.get("vendor") else None,
                    "quantity": data.get("quantity") or 1,
                    "product_nr": data.get("product_nr", ""),
                    "description": data.get("description", ""),
                })
        return out


OptionFormSet = forms.formset_factory(OptionForm, formset=BaseOptionFormSet, extra=0)
