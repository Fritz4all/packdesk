"""Registration wizard: licence number → end customer → (reseller) → device → (monitor) → (options) → check → done.

Everything is kept in the session and only saved in the last step.
"""

from datetime import date

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import forms
from .models import HardwareSystem, Licence, LicenceSettings, OptionType, Vendor
from .registration import complete_registration, send_certificate

SESSION_KEY = "registration"
STEPS = [
    ("licence", gettext_lazy("Licence")),
    ("end_customer", gettext_lazy("End customer")),
    ("reseller", gettext_lazy("Reseller")),
    ("device", gettext_lazy("Device")),
    ("monitor", gettext_lazy("Monitor")),
    ("options", gettext_lazy("Options")),
    ("check", gettext_lazy("Check")),
]


def _state(request):
    return request.session.get(SESSION_KEY) or {}


def _save_state(request, state):
    request.session[SESSION_KEY] = state
    request.session.modified = True


def _licence(request):
    state = _state(request)
    licence = Licence.objects.filter(pk=state.get("licence"), registered_on__isnull=True).select_related(
        "pack__category", "pack__period", "pack__service", "pack__hardware_class", "customer__customer_type"
    ).first()
    return licence, state


def _steps_for(licence):
    pack = licence.pack
    skip = set()
    if licence.customer.customer_type and licence.customer.customer_type.is_reseller:
        skip.add("reseller")
    if not pack.requires_monitor:
        skip.add("monitor")
    if not (pack.max_internal_options or pack.max_external_options):
        skip.add("options")
    return [(key, label) for key, label in STEPS if key not in skip]


def _next(licence, current):
    keys = [k for k, _l in _steps_for(licence)]
    return reverse(f"register_{keys[keys.index(current) + 1]}")


def _render(request, template, step, licence, context):
    steps = _steps_for(licence) if licence else STEPS[:1]
    context.update({
        "steps": steps, "current": step, "licence": licence, "rules": LicenceSettings.load(),
        "step_number": [k for k, _l in steps].index(step) + 1,
    })
    return render(request, template, context)


def _guard(request, step):
    licence, state = _licence(request)
    if licence is None:
        messages.info(request, _("Start with your licence number."))
        return None, None, redirect("register_licence")
    keys = [k for k, _l in _steps_for(licence)]
    for previous in keys[1:keys.index(step)]:
        if previous not in state:
            return None, None, redirect(f"register_{previous}")
    return licence, state, None


def licence_step(request):
    form = forms.LicenceNumberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        licence = form.licence
        if licence.pack.category.contact_to_register:
            return render(request, "licences/contact.html", {"licence": licence, "rules": LicenceSettings.load()})
        _save_state(request, {"licence": licence.pk})
        return redirect(_next(licence, "licence"))
    return _render(request, "licences/step.html", "licence", None, {"form": form})


def _simple_step(request, step, form_class, title):
    licence, state, redirect_to = _guard(request, step)
    if redirect_to:
        return redirect_to
    form = form_class(request.POST or None, initial=state.get(step))
    if request.method == "POST" and form.is_valid():
        state[step] = form.cleaned_data
        _save_state(request, state)
        return redirect(_next(licence, step))
    return _render(request, "licences/step.html", step, licence, {"form": form, "title": title})


def end_customer_step(request):
    return _simple_step(request, "end_customer", forms.EndCustomerForm, _("End customer"))


def reseller_step(request):
    return _simple_step(request, "reseller", forms.ResellerForm, _("Reseller"))


def device_step(request):
    licence, state, redirect_to = _guard(request, "device")
    if redirect_to:
        return redirect_to
    initial = dict(state.get("device", {}))
    form = forms.DeviceForm(request.POST or None, licence=licence, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        state["device"] = {
            "system": data["system"].pk if data.get("system") else None,
            "vendor": data["vendor_obj"].pk if data.get("vendor_obj") else None,
            "product_nr": data.get("product_nr", ""),
            "description": data["description"],
            "serial_nr": data["serial_nr"],
            "purchase_date": data["purchase_date"].isoformat() if data.get("purchase_date") else None,
            "start_date": data["start_date"].isoformat() if data.get("start_date") else None,
            "cover_start": data["cover_start"].isoformat(),
            "cover_end": data["cover_end"].isoformat(),
        }
        _save_state(request, state)
        return redirect(_next(licence, "device"))
    return _render(request, "licences/step.html", "device", licence, {"form": form, "title": _("Device")})


def monitor_step(request):
    licence, state, redirect_to = _guard(request, "monitor")
    if redirect_to:
        return redirect_to
    form = forms.MonitorForm(request.POST or None, initial=state.get("monitor_form"))
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        state["monitor"] = {
            "vendor": data["vendor"].pk if data.get("vendor") else None,
            "product_nr": data.get("product_nr", ""), "description": data.get("description", ""),
            "serial_nr": data.get("serial_nr", ""),
        } if data["filled"] else {}
        _save_state(request, state)
        return redirect(_next(licence, "monitor"))
    return _render(request, "licences/step.html", "monitor", licence, {"form": form, "title": _("Monitor")})


def options_step(request):
    licence, state, redirect_to = _guard(request, "options")
    if redirect_to:
        return redirect_to
    rows = min(licence.pack.max_internal_options + licence.pack.max_external_options, 10)
    formset_class = forms.forms.formset_factory(forms.OptionForm, formset=forms.BaseOptionFormSet, extra=rows, max_num=rows)
    formset = formset_class(request.POST or None, licence=licence, prefix="options")
    if request.method == "POST" and formset.is_valid():
        state["options"] = formset.rows()
        _save_state(request, state)
        return redirect(_next(licence, "options"))
    return _render(request, "licences/options.html", "options", licence, {"formset": formset})


def check_step(request):
    licence, state, redirect_to = _guard(request, "check")
    if redirect_to:
        return redirect_to
    if request.method == "POST":
        try:
            licence = complete_registration(licence.pk, state)
        except ValueError:
            messages.error(request, _("This licence has already been registered."))
            return redirect("register_licence")
        send_certificate(licence)
        request.session.pop(SESSION_KEY, None)
        request.session["registered_licence"] = licence.pk
        return redirect("register_done")
    device = state["device"]
    summary = {
        "cover_start": date.fromisoformat(device["cover_start"]),
        "cover_end": date.fromisoformat(device["cover_end"]),
        "purchase_date": date.fromisoformat(device["purchase_date"]) if device.get("purchase_date") else None,
        "system": HardwareSystem.objects.filter(pk=device.get("system")).select_related("vendor").first(),
        "vendor": Vendor.objects.filter(pk=device.get("vendor")).first(),
        "monitor_vendor": Vendor.objects.filter(pk=(state.get("monitor") or {}).get("vendor")).first(),
        "options": [
            {**row, "type": OptionType.objects.filter(pk=row["option_type"]).first(),
             "vendor_obj": Vendor.objects.filter(pk=row.get("vendor")).first()}
            for row in state.get("options", [])
        ],
    }
    return _render(request, "licences/check.html", "check", licence, {"state": state, "summary": summary})


def done(request):
    licence = Licence.objects.filter(pk=request.session.get("registered_licence")).first()
    if licence is None:
        return redirect("register_licence")
    return render(request, "licences/done.html", {"licence": licence, "rules": LicenceSettings.load()})
