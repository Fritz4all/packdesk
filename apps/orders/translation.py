from modeltranslation.translator import TranslationOptions, register

from .models import OrderSettings, PaymentMethod


@register(OrderSettings)
class OrderSettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "terms_text", "confirmation_text")


@register(PaymentMethod)
class PaymentMethodTranslationOptions(TranslationOptions):
    fields = ("name",)
