from django import forms
from django.utils.translation import gettext_lazy as _

from .models import FaultReport, RepairOption


class FaultReportForm(forms.ModelForm):
    lookup = forms.CharField(
        label=_("Licence number or serial number"), max_length=80, required=False,
        help_text=_("Optional. We fill in the device and check whether it is covered."),
    )

    class Meta:
        model = FaultReport
        fields = [
            "vendor", "device", "serial_nr", "operating_system", "description", "repair_option", "reference",
            "reseller_name", "reseller_address", "reseller_postal_code", "reseller_city", "reseller_phone", "reseller_email",
            "location_name", "location_contact", "location_address", "location_postal_code", "location_city",
            "location_country", "location_phone", "location_email",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "operating_system": forms.TextInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["repair_option"].queryset = RepairOption.objects.filter(is_active=True)
        self.fields["repair_option"].required = RepairOption.objects.filter(is_active=True).exists()
        for name in ("reseller_address", "reseller_postal_code", "reseller_city", "reseller_phone"):
            self.fields[name].required = True

    def group(self, *names):
        return [self[n] for n in names]
