from modeltranslation.translator import TranslationOptions, register

from .models import OrderSettings


@register(OrderSettings)
class OrderSettingsTranslationOptions(TranslationOptions):
    fields = ("intro", "terms_text", "confirmation_text")
