"""Printing services from the previous webshop, kept as an archive: printers and supplies, quotes, contracts and
supplies orders. The previous webshop stopped offering printing services (last quote 2013); its calculation rules
are not known any more, so PackDesk shows these records but does not make new ones."""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Printer(models.Model):
    name = models.CharField(_("name"), max_length=48)
    product_nr = models.CharField(_("article number"), max_length=32, blank=True)
    description = models.CharField(_("description"), max_length=128, blank=True)
    vendor = models.ForeignKey("licences.Vendor", on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name=_("brand"))
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, null=True, blank=True)
    installation_costs = models.DecimalField(_("installation costs"), max_digits=10, decimal_places=2, null=True,
                                             blank=True)
    support_factor = models.DecimalField(_("support factor"), max_digits=6, decimal_places=4, null=True, blank=True)
    color = models.BooleanField(_("colour"), default=False)
    monthly_max_prints = models.PositiveIntegerField(_("maximum prints per month"), null=True, blank=True)
    is_deleted = models.BooleanField(_("removed in the previous webshop"), default=False)
    successor_of = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True,
                                     verbose_name=_("replaces"))
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("printer")
        verbose_name_plural = _("printers")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Consumable(models.Model):
    name = models.CharField(_("name"), max_length=48, blank=True)
    product_nr = models.CharField(_("article number"), max_length=32, blank=True)
    vendor = models.ForeignKey("licences.Vendor", on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name=_("brand"))
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, null=True, blank=True)
    color = models.BooleanField(_("colour"), default=False)
    prints = models.PositiveIntegerField(_("prints"), null=True, blank=True)
    user_replaceable = models.BooleanField(_("replaceable by the user"), default=False)
    printers = models.ManyToManyField(Printer, blank=True, related_name="consumables", verbose_name=_("printers"))
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("supply")
        verbose_name_plural = _("supplies")
        ordering = ["name"]

    def __str__(self):
        return self.name or self.product_nr


class SupportPlan(models.Model):
    abbreviation = models.CharField(_("code"), max_length=8, blank=True)
    description = models.CharField(_("description"), max_length=128, blank=True)
    years = models.PositiveSmallIntegerField(_("duration (years)"), null=True, blank=True)
    storage_factor = models.DecimalField(_("storage factor"), max_digits=6, decimal_places=4, null=True, blank=True)
    lease_factor = models.DecimalField(_("lease factor"), max_digits=9, decimal_places=6, null=True, blank=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("support plan")
        verbose_name_plural = _("support plans")
        ordering = ["position"]

    def __str__(self):
        return f"{self.abbreviation} · {self.years} {_('years')}" if self.years else self.abbreviation


class Prices(models.Model):
    """Monthly prices as the previous webshop calculated them, per printer in a quote or contract."""

    options_price = models.DecimalField(_("options"), max_digits=10, decimal_places=2, null=True, blank=True)
    total_prints = models.PositiveIntegerField(_("prints per month"), null=True, blank=True)
    color_prints = models.PositiveIntegerField(_("colour prints per month"), null=True, blank=True)
    price_ex_hw = models.DecimalField(_("cost price per month excl. hardware"), max_digits=10, decimal_places=2,
                                      null=True, blank=True)
    price_inc_hw = models.DecimalField(_("cost price per month incl. hardware"), max_digits=10, decimal_places=2,
                                       null=True, blank=True)
    customer_price_ex_hw = models.DecimalField(_("price per month excl. hardware"), max_digits=10, decimal_places=2,
                                               null=True, blank=True)
    customer_price_inc_hw = models.DecimalField(_("price per month incl. hardware"), max_digits=10, decimal_places=2,
                                                null=True, blank=True)
    price_print_black = models.DecimalField(_("price per black print"), max_digits=7, decimal_places=4, null=True,
                                            blank=True)
    price_print_color = models.DecimalField(_("price per colour print"), max_digits=7, decimal_places=4, null=True,
                                            blank=True)

    class Meta:
        abstract = True


class PrintQuote(models.Model):
    number = models.CharField(_("number"), max_length=20, db_index=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="print_quotes", verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("made by"))
    reference = models.CharField(_("reference"), max_length=128, blank=True)
    margin_hardware = models.DecimalField(_("margin hardware (%)"), max_digits=5, decimal_places=2, null=True, blank=True)
    margin_supplies = models.DecimalField(_("margin supplies (%)"), max_digits=5, decimal_places=2, null=True, blank=True)
    margin_support = models.DecimalField(_("margin support (%)"), max_digits=5, decimal_places=2, null=True, blank=True)
    margin_prints = models.DecimalField(_("margin prints (%)"), max_digits=5, decimal_places=2, null=True, blank=True)
    deleted = models.BooleanField(_("removed by the customer"), default=False)
    created_at = models.DateTimeField(_("made at"), null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("printing quote")
        verbose_name_plural = _("printing quotes")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PrintQuoteLine(Prices):
    quote = models.ForeignKey(PrintQuote, on_delete=models.CASCADE, related_name="lines")
    printer = models.ForeignKey(Printer, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("printer"))
    support = models.ForeignKey(SupportPlan, on_delete=models.PROTECT, null=True, blank=True,
                                verbose_name=_("support plan"))
    legacy_id = models.CharField(max_length=80, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("printer in quote")
        verbose_name_plural = _("printers in quote")

    def __str__(self):
        return str(self.printer or "–")


class PrintContract(models.Model):
    number = models.CharField(_("contract number"), max_length=20, db_index=True)
    quote = models.ForeignKey(PrintQuote, on_delete=models.SET_NULL, null=True, blank=True, related_name="contracts",
                              verbose_name=_("quote"))
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="print_contracts", verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("made by"))
    company = models.CharField(_("end customer"), max_length=128, blank=True)
    contact = models.CharField(_("contact person"), max_length=100, blank=True)
    phone = models.CharField(_("phone"), max_length=20, blank=True)
    address = models.CharField(_("address"), max_length=300, blank=True)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    end_date = models.DateField(_("end date"), null=True, blank=True)
    preferred_date = models.DateField(_("preferred installation date"), null=True, blank=True)
    includes_hardware = models.BooleanField(_("including hardware"), default=False)
    activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("activated by"))
    activated_at = models.DateTimeField(_("activated at"), null=True, blank=True)
    created_at = models.DateTimeField(_("made at"), null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("printing contract")
        verbose_name_plural = _("printing contracts")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PrintContractLine(Prices):
    contract = models.ForeignKey(PrintContract, on_delete=models.CASCADE, related_name="lines")
    printer = models.ForeignKey(Printer, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("printer"))
    support = models.ForeignKey(SupportPlan, on_delete=models.PROTECT, null=True, blank=True,
                                verbose_name=_("support plan"))
    serial_nr = models.CharField(_("serial number"), max_length=40, blank=True)
    min_items = models.PositiveIntegerField(_("minimum stock"), null=True, blank=True)
    max_items = models.PositiveIntegerField(_("maximum stock"), null=True, blank=True)
    readings = models.TextField(_("meter readings and details"), blank=True)
    created_at = models.DateTimeField(_("made at"), null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("printer in contract")
        verbose_name_plural = _("printers in contract")

    def __str__(self):
        return f"{self.printer or '–'} {self.serial_nr}".strip()


class SuppliesOrder(models.Model):
    number = models.CharField(_("number"), max_length=20, db_index=True)
    contract_line = models.ForeignKey(PrintContractLine, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="supplies_orders", verbose_name=_("printer in contract"))
    contact = models.CharField(_("contact person"), max_length=64, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+", verbose_name=_("sent by"))
    created_at = models.DateTimeField(_("ordered at"), null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("supplies order")
        verbose_name_plural = _("supplies orders")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class SuppliesOrderLine(models.Model):
    order = models.ForeignKey(SuppliesOrder, on_delete=models.CASCADE, related_name="lines")
    consumable = models.ForeignKey(Consumable, on_delete=models.PROTECT, null=True, blank=True,
                                   verbose_name=_("supply"))
    quantity = models.IntegerField(_("quantity"), null=True, blank=True)
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, null=True, blank=True)
    legacy_id = models.CharField(max_length=80, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("ordered supply")
        verbose_name_plural = _("ordered supplies")

    def __str__(self):
        return f"{self.quantity} × {self.consumable}"
